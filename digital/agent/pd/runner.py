"""The one place that touches LibreLane.

    baseline(...)   run the flow untouched, end to end (remembered per design)
    fork(...)       resume from a saved state, re-run one stage onward, stop after GR
    signoff(...)    take one candidate from its post-GR state through DRC and LVS

Each run leaves a full LibreLane run directory behind — 1.2 GB for picorv32. This
module keeps only what a later branch needs and deletes the rest: for every
branch point, a self-contained snapshot of the state file plus the design files
it points to (about 45 MB each for picorv32), and a short digest of each stage's
log for the stage agent to read.

Plain Python, no agent framework, so the loop above can be rebuilt on something
else without touching this file.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import stages as S

# The runner sets its own tool PATH rather than trusting the caller's. Two
# reasons, both met in practice:
#   * a non-interactive shell on this image does not have /foss/tools/bin at all,
#     and the flow dies looking for verilator;
#   * LibreLane shells out to a bare `sta`, and the image ships two builds. The
#     generic OpenSTA 3.1.0 renamed write_timing_model's -corner flag to -scene,
#     so signoff fails with a Tcl error pointing at a line in a file that does not
#     contain the call. The build matching LibreLane 3.0.2 has to come first.
TOOL_DIRS = (
    "/foss/tools/openroad-librelane/bin",
    "/foss/tools/bin",
    "/foss/tools/klayout",
    "/foss/tools/sak",
)

END = "END"     # snapshot key for a run's final state: where signoff resumes

# Durations here are read from the monotonic clock, not the wall clock. A course
# VM lives on a laptop, and a laptop that dozes off suspends the VM: the wall
# clock then jumps forward on waking and a three-minute step is reported as
# twenty. That happened repeatedly while this lab was being measured.

# What a node carries around. Enough to rank it, constrain it, and describe it.
HEADLINE = (
    S.WS_KEY, S.WS_WORST_KEY, S.HOLD_KEY, S.HOLD_WORST_KEY,
    f"timing__setup__tns__corner:{S.FOM_CORNER}",
    "design__die__area", "design__instance__area", S.AREA_KEY,
    "design__instance__utilization",
    "design__instance__count", "design__instance__count__class:timing_repair_buffer",
    "design__instance__count__class:clock_buffer",
    S.POWER_KEY, "global_route__wirelength", "route__wirelength",
    f"clock__skew__worst_setup__corner:{S.FOM_CORNER}",
    "magic__drc_error__count", "design__lvs_error__count",
    "antenna__violating__nets", "route__drc_errors",
)

# What a stage's log is boiled down to before an agent reads it. The tools print
# far more than fits in a prompt and most of it is the same every run: the cell
# census after every step, the settings echoed back, every iteration of every
# solver. What is kept is what differs between two runs and says why.
_DROP = re.compile(
    r"^(Reading |Writing |Setting |Linking |Using |Updating metrics|%OL_|Placement Analysis"
    r"|Cell type report|\+ detailed_placement|\+ configure_cts|\[InitialPlace\]|\t"
    r"|total displacement|average displacement|original HPWL|delta HPWL"
    r"|\[INFO\] (Setting|Using|Legalizing|Configuring|Performing|Looking|Running|Repairing)"
    r"|\[INFO ORD|\[INFO ODB-0403|\[WARNING STA-1140|\s*-{5,}\s*$|\s*$)"
    r"|^\s+(Endcap|Tap|Tie|Clock buffer|Clock inverter|Timing Repair|Inverter|Sequential|Multi-Input"
    r"|Buffer|Fill|Antenna|Total)\b.*\d\s*$"
    r"|^\s+(Level \d+|Direction:|Sinks per sub-region|Sub-region size|(gf180mcu_\w+__)?\w+:?\s*\d*\s*$)"
    r"|^(Cells used|Dummys used|\s*VDD|\s*VSS)"
    r"|\[INFO GPL-00(0[1-9]|1[0-8]|2[0-2]|2[4-9]|3[0-8]|51)\]"
    r"|\[INFO GPL-10(02|03|11|12|14)\] (Placed|Available|Original|Total|Final)"
    r"|\[INFO CTS-0(007|008|020|024|025|026|027|028|030|034|049|050|051|052|097|201|205)\]"
    r"|\[INFO DPL-00(20|21|22|23)\]|\[INFO RSZ-0100\]"
    r"|/tmp/|/foss/")
_LONG_FLOAT = re.compile(r"(\d+\.\d{4})\d{3,}")
_CELL_PREFIX = "gf180mcu_fd_sc_mcu7t5v0__"
_ROW = re.compile(r"^\s*(\d+\*?|final)\s*\|")       # one line of an iteration table

# The repair steps load every timing corner the PDK defines and work on the
# worst one. On gf180mcuD that is the slow corner (ss, 125 C, 4.5 V), where this
# design misses by several ns. So the WNS their logs print is not the tt-corner
# slack the score is read from, and the two must not be compared.
_CORNER_NOTE = "WNS and TNS in this step are at the slowest corner, not at tt"
_REPAIR_STEPS = ("OpenROAD.ResizerTimingPostCTS", "OpenROAD.ResizerTimingPostGRT")


@dataclass
class RunResult:
    ok: bool
    seconds: float
    metrics: dict = field(default_factory=dict)        # headline numbers, post-GR
    signoff_metrics: dict = field(default_factory=dict)  # only for full/signoff runs
    stage_states: dict = field(default_factory=dict)   # stage or END -> snapshot json
    digests: dict = field(default_factory=dict)        # stage -> short log excerpt
    stage_seconds: dict = field(default_factory=dict)  # where the time went, by stage
    error: str = ""
    log_tail: str = ""                                 # what the diagnostician reads
    freed_bytes: int = 0
    from_cache: bool = False                           # a remembered baseline, not a fresh run
    shared: bool = False                               # snapshots live in the cache: never delete


# ------------------------------------------------------------------ plumbing
def _ensure_path() -> None:
    have = os.environ.get("PATH", "").split(":")
    want = [d for d in TOOL_DIRS if os.path.isdir(d)]
    if have[:len(want)] != want:
        rest = [d for d in have if d and d not in want]
        os.environ["PATH"] = ":".join(want + rest)
    # /foss/tools/bin/yosys is a wrapper that execs $TOOLS/yosys/bin/yosys, so a
    # shell that lost the image's environment fails with exit code 127.
    os.environ.setdefault("TOOLS", "/foss/tools")
    os.environ.setdefault("PDK_ROOT", "/foss/pdks")
    os.environ.setdefault("PDK", "gf180mcuD")


@contextlib.contextmanager
def _console_to(path: Path):
    """Send everything the flow prints — LibreLane's own narration and every
    tool it launches — to a file instead of the terminal. Works at the file
    descriptor level because the tools are child processes."""
    if os.environ.get("LLM_PD_VERBOSE"):
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout.flush(); sys.stderr.flush()
    saved = os.dup(1), os.dup(2)
    with open(path, "ab") as f:
        os.dup2(f.fileno(), 1); os.dup2(f.fileno(), 2)
        try:
            yield
        finally:
            sys.stdout.flush(); sys.stderr.flush()
            os.dup2(saved[0], 1); os.dup2(saved[1], 2)
            os.close(saved[0]); os.close(saved[1])


def _flow(design_dir: Path, overrides: dict | None):
    _ensure_path()
    from librelane.flows import Flow
    strings = [f"{k}={v}" for k, v in (overrides or {}).items()]
    return Flow.factory.get("Classic")(
        str(design_dir / "config.yaml"),
        design_dir=str(design_dir),
        pdk="gf180mcuD", pdk_root="/foss/pdks",
        scl="gf180mcu_fd_sc_mcu7t5v0",
        config_override_strings=strings,
    )


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _pick(metrics) -> dict:
    m = metrics or {}
    return {k: _num(m[k]) for k in HEADLINE if m.get(k) is not None}


def _step_dirs(run_dir: Path) -> list[Path]:
    dirs = [d for d in run_dir.iterdir() if d.is_dir() and re.match(r"^\d+-", d.name)]
    return sorted(dirs, key=lambda d: int(d.name.split("-", 1)[0]))


def _find(step_dirs: list[Path], step_id: str) -> int | None:
    want = S.step_dir_name(step_id)
    for i, d in enumerate(step_dirs):
        if d.name.split("-", 1)[1] == want:
            return i
    return None


def _snapshot(state_json: Path, dest: Path) -> str:
    """Make a branch point survive the deletion of its run directory.

    A LibreLane state file is a set of paths into the run directory. Copy every
    file it points to next to a rewritten copy of the state, so the snapshot can
    be loaded on its own.
    """
    dest.mkdir(parents=True, exist_ok=True)
    data = json.loads(state_json.read_text())

    def relocate(x, tag):
        if isinstance(x, str) and os.path.isfile(x):
            target = dest / f"{tag}__{os.path.basename(x)}"
            if not target.exists():
                shutil.copy2(x, target)
            return str(target)
        if isinstance(x, dict):
            return {k: relocate(v, f"{tag}_{k}") for k, v in x.items()}
        if isinstance(x, list):
            return [relocate(v, f"{tag}_{i}") for i, v in enumerate(x)]
        return x

    out = {k: (v if k == "metrics" else relocate(v, k)) for k, v in data.items()}
    path = dest / "state.json"
    path.write_text(json.dumps(out))
    return str(path)


def _boil(text: str, keep: int = 26) -> list[str]:
    """One step's log, reduced to the lines worth reading."""
    out: list[str] = []
    row_run = 0                                  # length of the current run of table rows
    for raw in text.splitlines():
        if _DROP.search(raw):
            continue
        line = _LONG_FLOAT.sub(r"\1", raw.rstrip().replace(_CELL_PREFIX, ""))[:150]
        if _ROW.match(line):                     # keep a table's first row and its last
            row_run += 1
            if row_run > 2:
                out[-1] = line
                continue
        else:
            row_run = 0
        if out and out[-1] == line:
            continue
        out.append(line)
    if len(out) > keep:
        out = out[:keep // 2] + ["  ..."] + out[-(keep - keep // 2 - 1):]
    return out


def _digest(step_dirs: list[Path], stage: S.Stage, limit: int = 2600) -> str:
    """How a stage went, for the stage agent: its steps' logs with the
    boilerplate removed and the iteration tables cut to first and last row."""
    chunks = []
    for step_id in stage.log_steps:
        i = _find(step_dirs, step_id)
        if i is None:
            continue
        log = step_dirs[i] / f"{S.step_dir_name(step_id)}.log"
        if not log.exists():
            continue
        lines = _boil(log.read_text(errors="replace"))
        if lines:
            head = f"--- {step_id} ---"
            if step_id in _REPAIR_STEPS:
                head = f"--- {step_id} ({_CORNER_NOTE}) ---"
            chunks.append(head + "\n" + "\n".join(lines))
    text = "\n".join(chunks)
    return text if len(text) <= limit else text[:limit].rsplit("\n", 1)[0] + "\n  ..."


def _error_tail(run_dir: Path, limit: int = 2600) -> str:
    """What a person would look at after a failure: LibreLane's own error
    summary, then the end of the log of the step that died. Machine paths are
    shortened; nothing else is filtered, because the useful line is rarely the
    one that says ERROR."""
    parts = []
    err = run_dir / "error.log"
    if err.exists() and err.stat().st_size:
        parts.append("--- error.log ---\n" + "\n".join(
            err.read_text(errors="replace").splitlines()[-25:]))
    steps = _step_dirs(run_dir) if run_dir.exists() else []
    if steps:
        logs = sorted(steps[-1].glob("*.log"), key=lambda p: p.stat().st_size, reverse=True)
        if logs:
            lines = [l.rstrip()[:160] for l in logs[0].read_text(errors="replace").splitlines()
                     if l.strip() and not l.startswith(("Writing ", "Reading "))]
            parts.append(f"--- end of {steps[-1].name}/{logs[0].name} ---\n" + "\n".join(lines[-30:]))
    text = "\n".join(parts)
    text = re.sub(r"(/tmp|/headless|/home)/\S*?/(\d+-[a-z0-9-]+)", r".../\2", text)
    return text[-limit:]


def _collect(run_dir: Path, store: Path, branch_stage: str | None, state) -> tuple[dict, dict]:
    """Snapshots for every branch point this run created, and a digest per stage run."""
    steps = _step_dirs(run_dir)
    states, digests = {}, {}
    for name in S.after(branch_stage):
        st = S.BY_NAME[name]
        i = _find(steps, st.first_step)
        if i is not None and i > 0:
            snap = steps[i - 1] / "state_out.json"
            if snap.exists():
                states[name] = _snapshot(snap, store / name)
    ran = S.NAMES if branch_stage is None else S.downstream(branch_stage)
    for name in ran:
        d = _digest(steps, S.BY_NAME[name])
        if d:
            digests[name] = d
    return states, digests


def _stage_seconds(run_dir: Path) -> dict:
    """Where a run's time went, from the runtime LibreLane records per step.

    Steps are grouped by the stage they belong to; what comes before placement
    is "before_PL" (synthesis and floorplan) and what comes after the in-loop
    stop is "signoff" (detailed routing, extraction, DRC, LVS).
    """
    steps = _step_dirs(run_dir) if run_dir.exists() else []
    starts = [(i, st.name) for st in S.STAGES
              if (i := _find(steps, st.first_step)) is not None]
    stop = _find(steps, S.IN_LOOP_STOP)
    out: dict[str, float] = {}
    for i, d in enumerate(steps):
        f = d / "runtime.txt"
        try:
            h, m, sec = f.read_text().split()[0].split(":")
            t = int(h) * 3600 + int(m) * 60 + float(sec)
        except (OSError, ValueError, IndexError):
            continue
        if stop is not None and i > stop:
            bucket = "signoff"
        else:
            earlier = [name for j, name in starts if j <= i]
            bucket = earlier[-1] if earlier else "before_PL"
        out[bucket] = round(out.get(bucket, 0.0) + t, 1)
    return out


def _prune(run_dir: Path) -> int:
    size = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
    shutil.rmtree(run_dir, ignore_errors=True)
    return size


def drop_snapshots(store: str | Path) -> int:
    """Delete a node's snapshots. Called by the tree when it prunes."""
    store = Path(store)
    return _prune(store) if store.exists() else 0


# ------------------------------------------------------------------ the three runs
def baseline(design_dir: str | Path, run_dir: str | Path, store: str | Path,
             keep_run_dir: bool = False, overrides: dict | None = None) -> RunResult:
    """The untouched flow, end to end, signoff included: LibreLane as shipped on
    the design's config. It is where every search starts and what every score
    is a ratio to.

    `overrides` exists for tools/calibrate_clock.py, which runs the same design
    at several clock targets. A search never passes any."""
    design_dir, run_dir, store = Path(design_dir), Path(run_dir), Path(store)
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        with _console_to(run_dir.parent / f"{run_dir.name}.console.log"):
            state = _flow(design_dir, overrides).start(_force_run_dir=str(run_dir))
    except Exception as e:
        return RunResult(False, time.monotonic() - t0, error=f"{type(e).__name__}: {e}"[:600],
                         log_tail=_error_tail(run_dir))
    seconds = time.monotonic() - t0

    # The root is compared with nodes that stop after global routing, so it is
    # ranked on the same post-GR numbers, not on its signoff numbers.
    steps = _step_dirs(run_dir)
    in_loop = _pick(state.metrics)
    i = _find(steps, S.IN_LOOP_STOP)
    if i is not None and (steps[i] / "state_out.json").exists():
        in_loop = _pick(json.loads((steps[i] / "state_out.json").read_text()).get("metrics"))

    states, digests = _collect(run_dir, store, None, state)
    spent = _stage_seconds(run_dir)
    freed = 0 if keep_run_dir else _prune(run_dir)
    return RunResult(True, seconds, in_loop, _pick(state.metrics), states, digests,
                     stage_seconds=spent, freed_bytes=freed)


# ------------------------------------------------------------------ the baseline, remembered
# The flow is deterministic: the same design through the same tools gave
# bit-identical metrics on five runs out of five, signoff included. So the
# untouched flow only needs to be run once per design. Its result and its three
# branch points are kept under ~/.cache/llm_pd and every later episode starts
# from them. It is still charged as a flow run — the budget is about what a
# search costs, not about what happened to be on disk.
#
#   LLM_PD_CACHE=/some/dir   put the cache somewhere else
#   LLM_PD_NO_CACHE=1        always run the baseline again
CACHE_FORMAT = 1


def cache_root() -> Path | None:
    if os.environ.get("LLM_PD_NO_CACHE"):
        return None
    return Path(os.environ.get("LLM_PD_CACHE") or "~/.cache/llm_pd").expanduser()


def baseline_key(design_dir: str | Path, overrides: dict | None = None) -> str:
    """A fingerprint of everything the untouched flow's result depends on: the
    design's own files, the LibreLane version, and the parts of this lab that
    decide what is read out of a run."""
    import hashlib
    from importlib import metadata
    design_dir = Path(design_dir)
    h = hashlib.sha256()
    try:
        version = metadata.version("librelane")
    except metadata.PackageNotFoundError:
        version = "unknown"
    h.update(repr((CACHE_FORMAT, version, S.IN_LOOP_STOP, HEADLINE,
                   [(s.name, s.first_step, s.log_steps) for s in S.STAGES],
                   sorted((overrides or {}).items()))).encode())
    for f in sorted(q for q in design_dir.rglob("*") if q.is_file() and "runs" not in q.parts):
        h.update(str(f.relative_to(design_dir)).encode() + b"\0" + f.read_bytes())
    # Files the config points to outside its own folder, such as the BLE RTL in
    # digital/rtl: an edit there must not be answered with a stale baseline.
    cfg = design_dir / "config.yaml"
    for ref in sorted(set(re.findall(r"dir::([^\s,\]\"']+)", cfg.read_text()))) if cfg.exists() else []:
        f = (design_dir / ref).resolve()
        if f.is_file() and design_dir.resolve() not in f.parents:
            h.update(ref.encode() + b"\0" + f.read_bytes())
    return h.hexdigest()[:16]


def _claim(lock: Path) -> bool:
    """Take the right to build one cache entry. False if another live process
    holds it; a claim left behind by a process that died is taken over."""
    for _ in range(2):
        try:
            lock.parent.mkdir(parents=True, exist_ok=True)
            os.mkdir(lock)
            (lock / "pid").write_text(str(os.getpid()))
            return True
        except FileExistsError:
            try:
                os.kill(int((lock / "pid").read_text()), 0)
                return False                      # its owner is alive
            except (OSError, ValueError):
                shutil.rmtree(lock, ignore_errors=True)
    return False


def baseline_cached(design_dir: str | Path, run_dir: str | Path, store: str | Path,
                    overrides: dict | None = None) -> RunResult:
    """baseline(), run once per design and remembered after that."""
    design_dir = Path(design_dir)
    root = cache_root()
    if root is None:
        return baseline(design_dir, run_dir, store, overrides=overrides)
    home = root / "baseline" / f"{design_dir.name}-{baseline_key(design_dir, overrides)}"
    record = home / "result.json"
    if record.exists():
        try:
            d = json.loads(record.read_text())
            if d["stage_states"] and all(os.path.exists(p) for p in d["stage_states"].values()):
                return RunResult(True, d["seconds"], d["metrics"], d["signoff_metrics"],
                                 d["stage_states"], d["digests"],
                                 stage_seconds=d.get("stage_seconds", {}),
                                 from_cache=True, shared=True)
        except (ValueError, KeyError, TypeError):
            pass                                  # unreadable entry: build it again

    lock = home.parent / (home.name + ".building")
    if not _claim(lock):
        # Another run is building this entry right now. Neither wait for it nor
        # write into the same place: run privately, exactly as without a cache.
        return baseline(design_dir, run_dir, store, overrides=overrides)
    try:
        shutil.rmtree(home, ignore_errors=True)
        res = baseline(design_dir, run_dir, home, overrides=overrides)
        if res.ok and res.stage_states:
            record.write_text(json.dumps({
                "design": design_dir.name, "seconds": res.seconds, "metrics": res.metrics,
                "signoff_metrics": res.signoff_metrics, "stage_states": res.stage_states,
                "digests": res.digests, "stage_seconds": res.stage_seconds}, indent=1))
            res.shared = True
        else:
            shutil.rmtree(home, ignore_errors=True)
        return res
    finally:
        shutil.rmtree(lock, ignore_errors=True)


def fork(design_dir: str | Path, ancestor_state: str, stage: str, params: dict,
         run_dir: str | Path, store: str | Path,
         bounds: dict | None = None) -> RunResult:
    """Resume at `stage` from `ancestor_state` and stop after global routing.

    `params` is the full blended configuration. Anything outside the tunable set
    or outside its range is refused here, before any compute is spent.
    """
    bad = S.validate(params, bounds)
    if bad:
        return RunResult(False, 0.0, error="rejected before running: " + "; ".join(bad))
    if stage not in S.BY_NAME:
        return RunResult(False, 0.0, error=f"rejected before running: unknown stage {stage!r}")
    if not ancestor_state or not Path(ancestor_state).exists():
        return RunResult(False, 0.0,
                         error="rejected before running: that branch point is no longer stored")

    design_dir, run_dir, store = Path(design_dir), Path(run_dir), Path(store)
    run_dir.mkdir(parents=True, exist_ok=True)
    _ensure_path()
    from librelane.state import State

    t0 = time.monotonic()
    try:
        initial = State.loads(Path(ancestor_state).read_text())
        with _console_to(run_dir.parent / f"{run_dir.name}.console.log"):
            state = _flow(design_dir, params).start(
                with_initial_state=initial, _force_run_dir=str(run_dir),
                frm=S.BY_NAME[stage].first_step, to=S.IN_LOOP_STOP,
            )
    except Exception as e:
        res = RunResult(False, time.monotonic() - t0, error=f"{type(e).__name__}: {e}"[:600],
                        log_tail=_error_tail(run_dir))
        res.freed_bytes = _prune(run_dir)
        return res
    seconds = time.monotonic() - t0

    steps = _step_dirs(run_dir)
    states, digests = _collect(run_dir, store, stage, state)
    i = _find(steps, S.IN_LOOP_STOP)
    if i is not None and (steps[i] / "state_out.json").exists():
        states[END] = _snapshot(steps[i] / "state_out.json", store / END)
    spent = _stage_seconds(run_dir)
    return RunResult(True, seconds, _pick(state.metrics), {}, states, digests,
                     stage_seconds=spent, freed_bytes=_prune(run_dir))


def signoff(design_dir: str | Path, end_state: str, params: dict,
            run_dir: str | Path, keep: str = "final") -> RunResult:
    """Detailed routing, Magic DRC and Netgen LVS, from a candidate's post-GR state.

    `keep` says what survives: "final" keeps only LibreLane's final/ directory
    (the GDS, DEF, netlists and reports — the deliverables) next to the run
    directory as <name>_final; "all" keeps the whole 1.2 GB; "none" keeps nothing.
    """
    design_dir, run_dir = Path(design_dir), Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    _ensure_path()
    from librelane.state import State
    t0 = time.monotonic()
    try:
        initial = State.loads(Path(end_state).read_text())
        with _console_to(run_dir.parent / f"{run_dir.name}.console.log"):
            state = _flow(design_dir, params).start(
                with_initial_state=initial, _force_run_dir=str(run_dir),
                frm=S.SIGNOFF_START,
            )
    except Exception as e:
        res = RunResult(False, time.monotonic() - t0, error=f"{type(e).__name__}: {e}"[:600],
                        log_tail=_error_tail(run_dir))
        res.freed_bytes = _prune(run_dir)
        return res
    seconds = time.monotonic() - t0
    sm = _pick(state.metrics)
    spent = _stage_seconds(run_dir)
    freed = 0
    if keep != "all":
        final = run_dir / "final"
        if keep == "final" and final.is_dir():
            dest = run_dir.parent / f"{run_dir.name}_final"
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(str(final), str(dest))
        freed = _prune(run_dir)
    return RunResult(True, seconds, sm, sm, stage_seconds=spent, freed_bytes=freed)


def ecp(metrics: dict, clock_period_ns: float) -> float | None:
    """Effective clock period at the scoring corner. See pd.stages.FOM_CORNER."""
    return S.effective_clock_period(metrics, clock_period_ns)
