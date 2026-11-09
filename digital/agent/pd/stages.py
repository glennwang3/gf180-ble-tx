"""The backend stages an agent may revise, mapped onto LibreLane's real step ids.

A branch at stage S reuses everything before S from a saved state and re-runs S
onward. Four stages are open for branching: floorplan, placement, clock tree,
global routing. Floorplan is the only place die area can change — two CTS
branches with very different settings returned byte-identical die area — and
re-running it redoes every stage after synthesis, so it costs a whole flow less
synthesis (about two minutes for ble_tx). The block has to fit a 300 um tall slot
of the chip, so the floorplan knob is the die's width; the height stays at what
the design's config.yaml gives. A floorplan branch can start from any result and
keeps that result's settings for every later stage: find good settings on a wide
die, then squeeze it. The later stages change how much of the die the standard
cells fill: every buffer that timing repair inserts and every cell it upsizes is
cell area. Both areas are scored (pd/ledger.py).

The narrowest die is set by the placement-density limit: a target density may not
sit below the starting utilisation plus 5 points, and that floor stops at the
density knob's top of 80 (bounds_for). Utilisation at a width is predicted from the
baseline's own floorplan (FloorplanFacts below), and DIE_WIDTH_UM may go down to
the width where the floor reaches 80. A floorplan branch raises the density on its
path to the floor for its width if it sits below it, so the density on every path
stays legal without the agent having to know.

Ten knobs, and each one earned its place by being measured. Every knob listed
here was changed on its own and moved at least one of the numbers the search cares
about: effective clock period, hold slack, power, die area or cell area. Five were
measured on picorv32 and five on ble_tx. That is a higher bar than "LibreLane has a
variable by that name", and several plausible knobs did not clear it, or cleared it
on picorv32 and then had nothing to do on ble_tx:

  * MAX_FANOUT_CONSTRAINT and DESIGN_REPAIR_MAX_SLEW_PCT were measured on ble_tx,
    one at a time from the baseline's placement state. The repair after placement
    adds 824 buffers, about 40% of the final area. Taken through signoff, a fanout
    limit of 6, 8 and 10 instead of 4 cut cell area 14%, 19% and 22% (96,512 to
    75,640 um2) with no slew violation at tt and no more capacitance violations than
    the baseline; 12 and 16 saved about 1% more and failed (2 and 3 capacitance
    violations at tt, 16 also 17 slew), so the range stops at 10. A slew margin of 10
    or 0 instead of 30 cut area 0.4%. DESIGN_REPAIR_MAX_CAP_PCT gave bit-identical
    results at 0 and at 40, so it is not a knob. The repair only works at the tt
    corner: the 1284 max-slew violations at ss_125C_4v50 did not move in any case, and
    at signoff the all-corner slew count grows with the fanout limit (30 at 4, 480 at 10).
    Loosening the repair is what saves area, but the baseline already has 30 slew
    and one capacitance violation at the slow corner (max_ss_125C_4v50), nearly all
    of them added by detailed routing after the repair has run. ledger.electrical_problems
    therefore allows none, at the typical or the slow corner. A slew margin of 50 took
    the slow-corner slew count from 30 to 2 at a fanout of 4 (area +3.4%); at a fanout of
    8 it left 85 and cleared the capacitance violation, which is on the clock tree's
    root buffer. Neither clock-tree cluster diameter tried (120, 400) cleared it, and
    neither did a repair after routing (RUN_POST_GRT_DESIGN_REPAIR) or a repair
    at the slow corner (PNR_CORNERS): both left the layout unchanged at fanout 4. What
    did clear it is a shorter clock wire and buffer spacing (CTS_CLK_MAX_WIRE_LENGTH 150,
    CTS_DISTANCE_BETWEEN_BUFFERS 100), now set in config.yaml. With those, margin 50
    leaves 2 slow-corner slew violations at fanouts 4, 5 and 6 (area +3%, -3%, -10%),
    all of them one net (an oai33_1 driving one load), and no capacitance violation.
    Two later changes moved all of this. The repair had been inserting the delay
    cell dlyb_1 as its buffer (35 um2, against 13 for buf_1 at the same drive), so
    config.yaml now excludes delay cells: the baseline fell to 78,972 um2 at the same
    power. And signoff now upsizes the drivers of whatever slew or capacitance
    violations detailed routing leaves (pd/runner.py). From the new baseline's
    placement at margin 30, fanout 4, 6 and 8 signed off with no violation at any
    corner (79,328, 74,180 and 73,379 um2; 12, 17 and 39 drivers upsized); fanout 10
    kept 22 at max_ss after three passes, and fanout 6 at margin 0 kept 3.

  * GRT_RESIZER_SETUP_SLACK_MARGIN and GRT_RESIZER_HOLD_SLACK_MARGIN belong to
    OpenROAD.ResizerTimingPostGRT, which the Classic flow does not run unless
    RUN_POST_GRT_RESIZER_TIMING is set, and that switch is off by default and
    marked experimental. Setting them changes nothing at all.
  * CTS_SINK_CLUSTERING_SIZE gave bit-identical results at 10 and at 40: on a
    design this sparse the cluster diameter is what limits a cluster, never the
    sink count.
  * PL_RESIZER_SETUP_SLACK_MARGIN and PL_RESIZER_HOLD_SLACK_MARGIN, the margins of
    the timing repair after clock-tree synthesis (a CTS step, despite the prefix),
    were knobs and are not any more. On ble_tx setup slack is about 105 ns against
    the 125 ns clock, so a setup margin has nothing to repair, and hold slack is
    0.5-0.6 ns at tt without any margin. The one search branch that raised them
    (hold 0.12, setup 0.05) came back with 2.5% more cell area and 8% more power.
    Both stay at LibreLane's defaults.

One knob is a switch, not a number, and it matters in a way the others do not.
PL_TIMING_DRIVEN changes what kind of layout comes out. The numbers a search
ranks on are read after global routing, and how far those sit from signoff
depends on the kind: a comparison between two layouts of one kind can be
trusted, a comparison across the switch cannot, until a layout of each kind has
been signed off. kind_of() below names the kind of a node; pd/tree.py corrects
the estimates of a kind from the nodes of that kind that have been signed off.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

# ----------------------------------------------------------------- the stop line
# In-loop evaluation ends here, after global routing. Detailed routing and
# signoff are half of a full flow, so results are ranked on post-global-route
# estimates and only the few put forward at the end are routed for real.
#
# How far to trust those estimates is something to measure, not assume. On
# picorv32 they separate a good placement from a bad one reliably and do not
# reliably order the good ones — AgenticPD reports a rank correlation of
# 0.83-0.93 with signoff for its flow; this one falls short of that. They are
# also biased on the two constraints, hold slack and power, and not in the same
# direction. Every signoff a run performs puts the two numbers side by side in
# its report.
IN_LOOP_STOP = "OpenROAD.STAMidPNR-3"
SIGNOFF_START = "OpenROAD.DetailedRouting"

# ----------------------------------------------------------------- the score
# LibreLane's bare `timing__setup__ws` is the worst of all nine corners, which on
# this PDK is max_ss_125C_4v50 and sits several ns below typical. The score is
# read at tt, the signoff corner; the worst
# corner is reported next to it so the gap is visible rather than hidden.
FOM_CORNER = "nom_tt_025C_5v00"
# The slowest corner. In-loop estimates report it as nom_ss; signoff also has it with
# maximum interconnect parasitics, which is where most of its violations are counted.
SLOW_CORNER = "nom_ss_125C_4v50"
SLOW_CORNER_MAX = "max_ss_125C_4v50"
WS_KEY = f"timing__setup__ws__corner:{FOM_CORNER}"
WS_WORST_KEY = "timing__setup__ws"
HOLD_KEY = f"timing__hold__ws__corner:{FOM_CORNER}"
HOLD_WORST_KEY = "timing__hold__ws"
POWER_KEY = "power__total"
# Standard cells only. The plain `design__instance__area` cannot be used: at
# signoff the core has been packed with fill cells and it reads the same for
# every layout. Before fill is inserted the two keys agree.
AREA_KEY = "design__instance__area__stdcell"
DIE_KEY = "design__die__area"


def setup_ws(metrics: dict) -> float | None:
    """Worst setup slack at the scoring corner, in ns."""
    v = metrics.get(WS_KEY, metrics.get(WS_WORST_KEY))
    return None if v is None else float(v)


def hold_ws(metrics: dict) -> float | None:
    """Worst hold slack at the scoring corner, in ns. Negative is a broken chip."""
    v = metrics.get(HOLD_KEY)
    return None if v is None else float(v)


def effective_clock_period(metrics: dict, clock_ns: float) -> float | None:
    """What the design could actually be clocked at, in ns. Lower is better."""
    ws = setup_ws(metrics)
    return None if ws is None else clock_ns - ws


# ----------------------------------------------------------------- the knobs
@dataclass(frozen=True)
class Param:
    kind: str            # "int", "float" or "bool"
    lo: float = 0
    hi: float = 1
    default: object = None
    what: str = ""

    def clamp(self, v):
        if self.kind == "bool":
            return bool(v)
        v = min(max(float(v), self.lo), self.hi)
        return int(round(v)) if self.kind == "int" else round(v, 4)

    def contains(self, v) -> bool:
        if self.kind == "bool":
            return isinstance(v, bool)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if self.kind == "int" and not float(v).is_integer():
            return False
        return self.lo <= v <= self.hi

    def sample(self, rng: random.Random):
        if self.kind == "bool":
            return rng.random() < 0.5
        if self.kind == "int":
            return rng.randint(int(self.lo), int(self.hi))
        return round(rng.uniform(self.lo, self.hi), 4)

    def describe(self) -> str:
        if self.kind == "bool":
            return f"true/false (when not set: {str(self.default).lower()})"
        default = "the flow's own choice" if self.default is None else self.default
        return f"{self.lo:g} .. {self.hi:g} (when not set: {default})"


@dataclass(frozen=True)
class Stage:
    name: str
    title: str
    first_step: str                 # LibreLane step id a branch resumes at
    log_steps: tuple[str, ...]      # step ids whose logs describe this stage
    params: dict[str, Param]
    note: str = ""


WIDTH = "DIE_WIDTH_UM"
DENSITY = "PL_TARGET_DENSITY_PCT"

STAGES: tuple[Stage, ...] = (
    Stage(
        name="FP", title="floorplan",
        first_step="OpenROAD.Floorplan",
        log_steps=("OpenROAD.Floorplan", "OpenROAD.TapEndcapInsertion", "OpenROAD.GeneratePDN"),
        params={
            # Not a LibreLane variable: the runner turns it into DIE_AREA, with the
            # height from config.yaml (to_librelane). The range is per design and
            # follows the density limit, see bounds_for.
            WIDTH: Param(
                "int", 100, 1400, None,
                "die width in um at the config's fixed height; narrower means less die "
                "area and a fuller core, so more routing congestion and slow-corner "
                "violations; the density on this path is raised to its floor for the width"),
        },
        note="Redoes the floorplan and every stage after it, keeping this result's settings "
             "for those stages. The only stage that changes die area.",
    ),
    Stage(
        name="PL", title="placement",
        first_step="OpenROAD.GlobalPlacement",
        log_steps=("OpenROAD.GlobalPlacement", "OpenROAD.RepairDesignPostGPL",
                   "OpenROAD.DetailedPlacement"),
        params={
            "PL_TIMING_DRIVEN": Param(
                "bool", default=False,
                what="let placement see timing; off by default in LibreLane"),
            "PL_TARGET_DENSITY_PCT": Param(
                "int", 30, 80, None,
                "how tightly cells are packed, in percent"),
            "PL_WIRE_LENGTH_COEF": Param(
                "float", 0.05, 0.50, 0.25,
                "global placement wirelength weight"),
            # The repair after placement (RepairDesignPostGPL) buffers every net that
            # breaks these limits, and on ble_tx it adds about 40% of the final cell
            # area. Both are set in designs/ble_tx/config.yaml; a branch overrides them.
            "MAX_FANOUT_CONSTRAINT": Param(
                "int", 4, 10, 4,
                "most cells one net may drive before the repair after placement buffers it; "
                "higher means fewer buffers and less area, and more slow-corner slew violations "
                "for signoff to fix; at margin 30, 4 to 8 signed off clean and 10 did not"),
            "DESIGN_REPAIR_MAX_SLEW_PCT": Param(
                "float", 0.0, 30.0, 30.0,
                "margin below the slew limit the repair after placement aims for, in percent; "
                "higher means more buffers and fewer slow-corner slew violations; with delay "
                "cells excluded the repair crashed at 50 (fanout 5 and 6), so 30 is the top"),
        },
        note="Redoes placement, repair, clock tree and routing. Moves timing, power and cell "
             "area, mostly through the buffers the repair after placement inserts; "
             "its switch changes the kind of layout.",
    ),
    Stage(
        name="CTS", title="clock tree synthesis",
        first_step="OpenROAD.CTS",
        log_steps=("OpenROAD.CTS", "OpenROAD.ResizerTimingPostCTS"),
        params={
            "CTS_SINK_CLUSTERING_MAX_DIAMETER": Param(
                "int", 50, 400, None,
                "largest span of a leaf cluster of flip-flops, in um"),
            # Set to 150 and 100 in config.yaml, which cleared the clock root's
            # capacitance violation on the 1400 um die. On a die narrowed to 300-340 um
            # the clock-gated design's root buffer carried 0.25 pF against 0.2 at those
            # values, and 80 and 60 cleared it; the clean 300 um run of this netlist
            # used 80 and 60 too.
            "CTS_CLK_MAX_WIRE_LENGTH": Param(
                "int", 50, 300, None,
                "longest clock wire before CTS adds a buffer, in um; shorter means more "
                "clock buffers and less load on each, which a full core can need"),
            "CTS_DISTANCE_BETWEEN_BUFFERS": Param(
                "int", 40, 200, None,
                "spacing of the buffers CTS puts on long clock wires, in um"),
        },
        note="Keeps the placement. Shapes the clock tree: how far its wires run and how "
             "closely its buffers sit.",
    ),
    Stage(
        name="GR", title="global routing",
        first_step="OpenROAD.GlobalRouting",
        log_steps=("OpenROAD.GlobalRouting", "OpenROAD.RepairAntennas"),
        params={
            # Read by every step that calls the global router, routability-driven
            # placement included. Set at a GR branch it only reaches the router
            # and what follows it, because nothing earlier is re-run.
            "GRT_ADJUSTMENT": Param(
                "float", 0.10, 0.60, 0.30,
                "fraction of routing capacity withheld from the global router"),
        },
        note="Keeps placement and clock tree. The cheapest branch, and the one with least leverage.",
    ),
)

BY_NAME = {s.name: s for s in STAGES}
NAMES = tuple(s.name for s in STAGES)
ALLOWED_KEYS = frozenset(k for s in STAGES for k in s.params)
SWITCHES = tuple(k for s in STAGES for k, p in s.params.items() if p.kind == "bool")


def kind_of(params: dict) -> str:
    """The kind of layout a configuration makes: where each switch stands.

    Estimates made after global routing compare fairly between two layouts of
    one kind. Across kinds they need not: the estimate can be optimistic for
    one and nearly right for the other. So a kind is the unit an estimate is
    corrected in, from the nodes of that kind that have been signed off."""
    where = {k: p.default for s in STAGES for k, p in s.params.items() if p.kind == "bool"}
    where.update({k: bool(v) for k, v in params.items() if k in where})
    return ", ".join(f"{k} {'on' if where[k] else 'off'}" for k in SWITCHES) or "the only kind"


def step_dir_name(step_id: str) -> str:
    """'OpenROAD.GlobalRouting' -> 'openroad-globalrouting' (a run-dir suffix)."""
    return step_id.lower().replace(".", "-")


def downstream(stage: str) -> tuple[str, ...]:
    """Stages a branch at `stage` re-runs: that stage and everything after it."""
    return NAMES[NAMES.index(stage):]


def after(stage: str | None) -> tuple[str, ...]:
    """Stages strictly after `stage`. A node made by branching at CTS can only
    seed a GR branch: redoing CTS from it is the same as branching its parent.
    The floorplan is the exception, offered from every node (pd/tree.py)."""
    if stage is None:
        return NAMES
    return NAMES[NAMES.index(stage) + 1:]


# ----------------------------------------------------------------- the die
@dataclass(frozen=True)
class FloorplanFacts:
    """The baseline's floorplan, read just before placement: enough to predict the
    starting utilisation of the same netlist on a die of another width.

    The core sits inside fixed margins and its height does not change with the
    width. Tap cells are placed at a fixed pitch, so they fill a fixed share of
    the core; everything else that is placed before placement (the synthesised
    netlist, endcaps, ties) is the same area whatever the width."""
    die_w: float
    die_h: float
    core_w: float
    core_h: float
    cells: float            # area placed before placement, tap cells not counted
    tap_share: float        # tap-cell area over core area

    @classmethod
    def from_metrics(cls, m: dict) -> "FloorplanFacts | None":
        try:
            dx0, dy0, dx1, dy1 = (float(v) for v in str(m["design__die__bbox"]).split())
            cx0, cy0, cx1, cy1 = (float(v) for v in str(m["design__core__bbox"]).split())
            core = (cx1 - cx0) * (cy1 - cy0)
            taps = float(m.get("design__instance__area__class:tap_cell") or 0.0)
            placed = float(m["design__instance__utilization"]) * core
        except (KeyError, TypeError, ValueError):
            return None
        return cls(dx1 - dx0, dy1 - dy0, cx1 - cx0, cy1 - cy0, placed - taps, taps / core)

    def core_area(self, width: float) -> float:
        return (width - (self.die_w - self.core_w)) * self.core_h

    def utilisation(self, width: float) -> float:
        """Starting utilisation of the baseline netlist on a die `width` um wide."""
        core = self.core_area(width)
        return 1.0 if core <= 0 else self.cells / core + self.tap_share

    def narrowest(self) -> int:
        """The narrowest whole-um width whose density floor is still below its cap:
        starting utilisation + 5 points at most 75."""
        u = DENSITY_FLOOR_CAP / 100 - DENSITY_FLOOR_STEP / 100
        core = self.cells / (u - self.tap_share)
        return math.ceil(core / self.core_h + (self.die_w - self.core_w))


# The density limit: a target may not sit below the starting utilisation plus
# DENSITY_FLOOR_STEP points, and that floor stops at DENSITY_FLOOR_CAP. The cap is
# the density knob's own top, 80: a die is legal as long as some density within the
# knob's range can still honour it. (It was 75, which kept ble_tx at 319 um or wider.)
DENSITY_FLOOR_STEP = 5
DENSITY_FLOOR_CAP = 80


def density_floor(utilisation: float) -> int:
    return min(DENSITY_FLOOR_CAP, int(utilisation * 100) + DENSITY_FLOOR_STEP)


def to_librelane(params: dict, die_height: float | None) -> dict:
    """The settings as LibreLane reads them: DIE_WIDTH_UM becomes DIE_AREA."""
    out = dict(params)
    w = out.pop(WIDTH, None)
    if w is not None and die_height:
        out["DIE_AREA"] = f"0 0 {w:g} {die_height:g}"
    return out


# ----------------------------------------------------------------- bounds
def bounds_for(utilisation: float | None = None, facts: FloorplanFacts | None = None,
               width: float | None = None) -> dict[str, Param]:
    """The legal range of every knob for one design.

    Two bounds depend on the design. The placement-density floor follows the
    utilisation. A target below the utilisation cannot be honoured. This flow
    does not fail on one — a 12% target on a 30%-utilised design was checked and
    ran — so the floor is not there to prevent a crash; it keeps the search out of
    a region where the knob has stopped meaning what its name says. With `facts`
    the utilisation is the predicted starting one on a die `width` um wide (the
    baseline's width if None), and the die width runs from the narrowest width the
    density floor allows to the baseline's.
    """
    out = {k: p for s in STAGES for k, p in s.params.items()}
    if facts is not None:
        utilisation = facts.utilisation(width or facts.die_w)
        p = out[WIDTH]
        out[WIDTH] = Param(p.kind, facts.narrowest(), round(facts.die_w), p.default, p.what)
    if utilisation:
        p = out[DENSITY]
        out[DENSITY] = Param(p.kind, max(p.lo, density_floor(utilisation)), p.hi,
                             p.default, p.what)
    return out


def validate(params: dict, bounds: dict[str, Param] | None = None) -> list[str]:
    """Reasons `params` is not acceptable. An empty list means it is fine."""
    bounds = bounds or bounds_for()
    problems = []
    for k, v in params.items():
        if k not in bounds:
            problems.append(f"{k} is not a tunable key")
        elif not bounds[k].contains(v):
            problems.append(f"{k}={v!r} is outside {bounds[k].describe()}")
    return problems


def coerce(params: dict, bounds: dict[str, Param] | None = None) -> dict:
    """Repair the type slips a model makes in JSON — 17.0 for an integer knob,
    "true" for a switch — without ever moving a value. Out-of-range values are
    left alone so that validate() can report them."""
    bounds = bounds or bounds_for()
    out = {}
    for k, v in params.items():
        p = bounds.get(k)
        if p is None:
            out[k] = v
        elif p.kind == "bool" and isinstance(v, str) and v.strip().lower() in ("true", "false"):
            out[k] = v.strip().lower() == "true"
        elif p.kind == "int" and isinstance(v, float) and v.is_integer():
            out[k] = int(v)
        elif p.kind in ("int", "float") and isinstance(v, str):
            try:
                f = float(v)
                out[k] = int(f) if p.kind == "int" and f.is_integer() else f
            except ValueError:
                out[k] = v
        else:
            out[k] = v
    return out


def blend(ancestor_params: dict, proposal: dict, stage: str) -> dict:
    """Keep the ancestor's settings for reused stages; take the proposal for re-run ones.

    Keys that belong to an inherited stage are ignored rather than applied: that
    stage is not being re-run, so pretending to change it would mislabel the node.
    """
    out = dict(ancestor_params)
    active = set(downstream(stage))
    for s in STAGES:
        if s.name in active:
            for k in s.params:
                if k in proposal:
                    out[k] = proposal[k]
    return out


UNSET_CHANCE = 0.25      # how often a random setting leaves a "tool decides" knob alone


def sample(stage: str, rng: random.Random, bounds: dict[str, Param] | None = None) -> dict:
    """One random setting for `stage`. The proposer in agents/policy.py is built on this.

    A knob whose default is None is one the flow settles for itself when nobody
    sets it — from the design's config, or by a method of the tool's own. "Not
    set" is then a value in its own right, which no number in the range need
    reproduce, so a quarter of the time such a knob is left out."""
    bounds = bounds or bounds_for()
    out = {}
    for k in BY_NAME[stage].params:
        p = bounds[k]
        if p.kind != "bool" and p.default is None and rng.random() < UNSET_CHANCE:
            continue
        out[k] = p.sample(rng)
    return out


def cheat_sheet(bounds: dict[str, Param] | None = None, only: str | None = None) -> str:
    """One screen of text describing the knobs, for a prompt."""
    bounds = bounds or bounds_for()
    lines = []
    for s in STAGES:
        if only and s.name != only:
            continue
        lines.append(f"{s.name} - {s.title}. {s.note}")
        for k in s.params:
            lines.append(f"  {k}: {bounds[k].describe()} - {bounds[k].what}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(cheat_sheet(bounds_for(0.34)))
    print()
    print("branch at CTS re-runs", downstream("CTS"), "| a CTS node can seed", after("CTS"))
    rng = random.Random(1)
    for s in NAMES:
        p = sample(s, rng, bounds_for(0.34))
        print(f"  sample {s}: {p}  valid={not validate(p, bounds_for(0.34))}")
    print("  reject:", validate({"PL_TARGET_DENSITY_PCT": 20, "ERROR_ON_MAGIC_DRC": False},
                                bounds_for(0.34)))
