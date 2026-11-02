"""The backend stages an agent may revise, mapped onto LibreLane's real step ids.

A branch at stage S reuses everything before S from a saved state and re-runs S
onward. Three stages are open for branching: placement, clock tree, global
routing. Floorplan is fixed. Re-running it reuses nothing, so it costs a whole
flow, and it is the only place die area can change — two CTS branches with very
different settings returned byte-identical die area. The die is therefore fixed
in this lab. What a branch does change is how much of it the standard cells
fill: every buffer that timing repair inserts and every cell it upsizes is cell
area, and that is the area the score counts.

Seven knobs, and each one earned its place by being measured. Every knob listed
here was changed on its own, on picorv32, and moved at least one of the numbers
the search cares about: effective clock period, hold slack, power or cell area.
That is a higher bar than "LibreLane has a variable by that name", and several
plausible knobs did not clear it:

  * GRT_RESIZER_SETUP_SLACK_MARGIN and GRT_RESIZER_HOLD_SLACK_MARGIN belong to
    OpenROAD.ResizerTimingPostGRT, which the Classic flow does not run unless
    RUN_POST_GRT_RESIZER_TIMING is set, and that switch is off by default and
    marked experimental. Setting them changes nothing at all.
  * CTS_SINK_CLUSTERING_SIZE gave bit-identical results at 10 and at 40: on a
    design this sparse the cluster diameter is what limits a cluster, never the
    sink count.

One knob is a switch, not a number, and it matters in a way the others do not.
PL_TIMING_DRIVEN changes what kind of layout comes out. The numbers a search
ranks on are read after global routing, and how far those sit from signoff
depends on the kind: a comparison between two layouts of one kind can be
trusted, a comparison across the switch cannot, until a layout of each kind has
been signed off. kind_of() below names the kind of a node; pd/tree.py corrects
the estimates of a kind from the nodes of that kind that have been signed off.

Names are not a guide to where a knob acts. PL_RESIZER_SETUP_SLACK_MARGIN and
PL_RESIZER_HOLD_SLACK_MARGIN are read by the timing repair that runs after
clock-tree synthesis, so despite the prefix they are CTS-stage knobs.
"""
from __future__ import annotations

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
# this PDK is max_ss_125C_4v50 and sits several ns below typical. Labs 2 and 3
# told students tt is the signoff corner, so the score is read there; the worst
# corner is reported next to it so the gap is visible rather than hidden.
FOM_CORNER = "nom_tt_025C_5v00"
WS_KEY = f"timing__setup__ws__corner:{FOM_CORNER}"
WS_WORST_KEY = "timing__setup__ws"
HOLD_KEY = f"timing__hold__ws__corner:{FOM_CORNER}"
HOLD_WORST_KEY = "timing__hold__ws"
POWER_KEY = "power__total"
# Standard cells only. The plain `design__instance__area` cannot be used: at
# signoff the core has been packed with fill cells and it reads the same for
# every layout. Before fill is inserted the two keys agree.
AREA_KEY = "design__instance__area__stdcell"


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


STAGES: tuple[Stage, ...] = (
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
        },
        note="Redoes placement, clock tree and routing. Moves timing, power and cell area; "
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
            "PL_RESIZER_HOLD_SLACK_MARGIN": Param(
                "float", 0.1, 0.5, 0.1,
                "hold margin the timing repair after CTS aims for (a CTS knob, despite the name)"),
            "PL_RESIZER_SETUP_SLACK_MARGIN": Param(
                "float", 0.0, 0.5, 0.05,
                "setup margin the timing repair after CTS aims for (a CTS knob, despite the name)"),
        },
        note="Keeps the placement. Shapes the clock tree and the timing repair after it.",
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
    seed a GR branch: redoing CTS from it is the same as branching its parent."""
    if stage is None:
        return NAMES
    return NAMES[NAMES.index(stage) + 1:]


# ----------------------------------------------------------------- bounds
def bounds_for(utilisation: float | None = None) -> dict[str, Param]:
    """The legal range of every knob for one design.

    Only one bound depends on the design: the placement-density floor follows
    the utilisation. A target below the utilisation cannot be honoured. This flow
    does not fail on one — a 12% target on a 30%-utilised design was checked and
    ran — so the floor is not there to prevent a crash; it keeps the search out of
    a region where the knob has stopped meaning what its name says.
    """
    out = {k: p for s in STAGES for k, p in s.params.items()}
    if utilisation:
        floor = min(75, int(utilisation * 100) + 5)
        p = out["PL_TARGET_DENSITY_PCT"]
        out["PL_TARGET_DENSITY_PCT"] = Param(p.kind, max(p.lo, floor), p.hi,
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
    """One random setting for `stage`. The staff-provided proposer is built on this.

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
    """One screen of text describing the knobs, for a prompt or the handout."""
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
