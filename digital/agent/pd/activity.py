"""Power from simulated switching activity instead of OpenSTA's vectorless guess.

Without activity, OpenSTA propagates default toggle rates from the inputs through
the logic, feedback loops included. On ble_tx (CRC, whitening, bit counter and state
machine are all loops) that guess swings with netlist structure: two layouts of
nearly the same netlist were reported at 1.43 and 4.46 mW, and measured from a
simulated packet at 1.18 and 1.22 mW. The clock network's share is right either
way; the flops' and logic's shares are not. A search ranking layouts by a few
percent cannot use that, so a design that provides a testbench is scored here:

  1. simulate the layout's own gate-level netlist (Icarus, the PDK's functional
     cell models) with designs/<name>/power_tb.v, which dumps a VCD of the block
     over the window that matters (for ble_tx: one advertising packet on air);
  2. load that activity and report power at the scoring corner (tt):
       after global routing  OpenROAD on the state's database, wires estimated
                             from placement (the PDK's DATA/CLOCK wire RC layers);
       at signoff            OpenSTA with the extracted parasitics (SPEF).

The result replaces power__total; the vectorless figure is kept as
power__vectorless__total, and the split as power__activity__{clock,sequential,
combinational}. A design without power_tb.v keeps the vectorless figure.

The testbench names its top module power_tb and the block's instance dut, and
reads two defines: VCD_OUT (where to write) and STIM_DIR (the design folder, for
stimulus files). Each input port of the netlist is passed as HAS_PORT_<name>, so
one testbench serves netlists with and without optional ports.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

PDK = Path(os.environ.get("PDK_ROOT", "/foss/pdks")) / "gf180mcuD"
SCL = "gf180mcu_fd_sc_mcu7t5v0"
CELL_MODELS = (PDK / f"libs.ref/{SCL}/verilog/primitives.v",
               PDK / f"libs.ref/{SCL}/verilog/{SCL}.v")
LIB_TT = PDK / f"libs.ref/{SCL}/lib/{SCL}__tt_025C_3v30.lib"   # power-exp: 3.3 V
DATA_WIRE_LAYER, CLOCK_WIRE_LAYER = "Metal2", "Metal4"    # the PDK's LibreLane config
IVERILOG_DIR = "/foss/tools/iverilog/bin"
OPENROAD = "/foss/tools/openroad-librelane/bin/openroad"
STA = "/foss/tools/openroad-librelane/bin/sta"
TB_NAME = "power_tb.v"
SCOPE = "power_tb/dut"

GROUPS = ("Sequential", "Combinational", "Clock", "Total")


def has_testbench(design_dir: str | Path) -> bool:
    return (Path(design_dir) / TB_NAME).is_file()


def _input_ports(netlist: Path) -> list[str]:
    text = netlist.read_text()
    return sorted(set(re.findall(r"^\s*input\s+(?:wire\s+)?(?:\[[^\]]*\]\s*)?(\w+)\s*;", text, re.M)))


def simulate(design_dir: str | Path, netlist: str | Path, work: str | Path) -> Path:
    """Run the design's power testbench on `netlist`; return the VCD it wrote."""
    # Absolute paths: vvp runs inside `work`, and the run directories are relative.
    design_dir, netlist, work = Path(design_dir).resolve(), Path(netlist).resolve(), Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    vcd, vvp = work / "activity.vcd", work / "activity.vvp"
    env = dict(os.environ, PATH=f"{IVERILOG_DIR}:{os.environ.get('PATH', '')}")
    defines = ["-DFUNCTIONAL", "-DUNIT_DELAY=#1", f'-DVCD_OUT="{vcd}"',
               f'-DSTIM_DIR="{design_dir.resolve()}"']
    defines += [f"-DHAS_PORT_{p}" for p in _input_ports(netlist)]
    cmd = ["iverilog", "-g2012", *defines, "-o", str(vvp), str(design_dir / TB_NAME),
           *map(str, CELL_MODELS), str(netlist)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise RuntimeError(f"power testbench did not compile: {r.stderr[-800:]}")
    r = subprocess.run(["vvp", "-n", str(vvp)], capture_output=True, text=True, env=env, cwd=work)
    if r.returncode or not vcd.exists():
        raise RuntimeError(f"power testbench failed: {(r.stdout + r.stderr)[-800:]}")
    vvp.unlink(missing_ok=True)
    return vcd


def _parse(out: str) -> dict:
    got = {}
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] in GROUPS and len(parts) >= 5:
            try:
                got[parts[0]] = float(parts[4])
            except ValueError:
                pass
    if "Total" not in got:
        raise RuntimeError(f"no power report in the tool output: {out[-800:]}")
    return {"power__total": got["Total"],
            "power__activity__clock": got.get("Clock"),
            "power__activity__sequential": got.get("Sequential"),
            "power__activity__combinational": got.get("Combinational")}


def _run_tcl(tool: str, script: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False) as f:
        f.write(script)
    try:
        args = [tool, "-exit", "-no_init", f.name] if tool == OPENROAD else [tool, "-exit", f.name]
        r = subprocess.run(args, capture_output=True, text=True)
        return r.stdout + r.stderr
    finally:
        os.unlink(f.name)


def power_post_gr(odb: str | Path, sdc: str | Path, vcd: str | Path) -> dict:
    """Power at tt from a post-global-route database, wires estimated from placement."""
    return _parse(_run_tcl(OPENROAD, f"""
read_liberty {LIB_TT}
read_db {odb}
read_sdc {sdc}
set_wire_rc -signal -layer {DATA_WIRE_LAYER}
set_wire_rc -clock -layer {CLOCK_WIRE_LAYER}
set_propagated_clock [all_clocks]
estimate_parasitics -placement
read_vcd -scope {SCOPE} {vcd}
report_power -digits 6
"""))


def power_signoff(netlist: str | Path, sdc: str | Path, spef: str | Path, vcd: str | Path) -> dict:
    """Power at tt from the routed netlist and its extracted parasitics."""
    return _parse(_run_tcl(STA, f"""
read_liberty {LIB_TT}
read_verilog {netlist}
link_design {Path(netlist).name.split('.')[0]}
read_sdc {sdc}
read_spef {spef}
set_propagated_clock [all_clocks]
read_vcd -scope {SCOPE} {vcd}
report_power -digits 6
"""))


def _nom_spef(spef) -> str | None:
    if isinstance(spef, (str, Path)):
        return str(spef)
    if isinstance(spef, dict):
        for k, v in spef.items():
            if "nom" in k and v:
                return str(v)
        return next((str(v) for v in spef.values() if v), None)
    return None


def measure(design_dir: str | Path, state: dict, work: str | Path, metrics: dict) -> dict:
    """The power keys to merge into `metrics` for one LibreLane state (a parsed state
    file): from the extracted parasitics if the state has them, else post-GR.
    Returns {} for a design without a power testbench. Raises on a tool failure."""
    if not has_testbench(design_dir):
        return {}
    netlist = state.get("nl")
    if not netlist:
        raise RuntimeError("the state has no netlist to simulate")
    vcd = simulate(design_dir, netlist, work)
    try:
        spef = _nom_spef(state.get("spef"))
        if spef and Path(spef).exists():
            got = power_signoff(netlist, state["sdc"], spef, vcd)
        else:
            got = power_post_gr(state["odb"], state["sdc"], vcd)
    finally:
        vcd.unlink(missing_ok=True)
    got["power__vectorless__total"] = metrics.get("power__total")
    got["power__source"] = "simulated activity"
    return got
