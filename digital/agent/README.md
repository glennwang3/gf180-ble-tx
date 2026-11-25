# Agent-driven layout of the BLE modulator

An agentic LibreLane flow for `ble_tx` and for `ble_tx_uart`, the block with its
UART front end (`--design designs/ble_tx_uart`; its answer is in
`../../tapeout/ble_tx_uart`).
Four language-model agents tune the backend flow (placement, clock tree, global
routing) and the best result is taken through detailed routing, DRC and LVS to a
GDS:

- the **navigator** picks where the next flow run goes: branch a stage of an
  earlier result, or evaluate one through signoff;
- the **stage agent** picks the settings of that one stage;
- the **stop agent** says when to stop (recorded; the stopping rule decides by default);
- the **diagnostician** explains a failed run.

## What it optimizes

The modulator runs at a fixed 8 MHz, so a faster layout is worth nothing.
Timing is a pass/fail gate and the score is power, die area and standard-cell area:

    score = (P0 / P)^0.1 x (D0 / D)^0.6 x (A0 / A)^0.3      1.0 = LibreLane untouched

The whole Bluetooth chip has a 1400 x 300 um tapeout slot, and this block should
take as little of it as it can. The baseline's die is `DIE_AREA` in the design's
`config.yaml` (247 x 300 um for ble_tx). The search keeps the 300 um height and narrows the
die with the floorplan stage's `DIE_WIDTH_UM`. The narrowest width allowed is
where the placement-density floor (starting utilisation + 5 points) reaches its
cap of 80 (`DENSITY_FLOOR_CAP`); `pd/stages.py` predicts that width from the baseline's floorplan. An
FP branch can start from any result and keeps its settings for the later stages.

### How power is measured

Power (`P` above) comes from simulated switching activity, not from OpenSTA's
vectorless default (`pd/activity.py`). Each result's own gate-level netlist is
simulated with `designs/ble_tx/power_tb.v`, which sends one advertising packet
(`power_pdu.hex`) at 8 MHz and dumps a VCD while the packet is on air; that VCD
is loaded at the tt corner:

- after global routing (every branch, and the baseline's ranking figures): OpenROAD
  on the state's database, wires estimated from placement;
- at signoff: OpenSTA with the extracted SPEF.

It adds about 2 s per result. The vectorless figure is kept as
`power__vectorless__total`, and the split as `power__activity__{clock,sequential,
combinational}`. Why: the vectorless guess propagates default toggle rates around
the CRC, whitening, counter and state-machine loops, and swings with netlist
structure. Two layouts of nearly the same netlist were reported at 1.43 and 4.46 mW
and measured from a packet at 1.18 and 1.22 mW. If the measurement fails the run
fails, so a search never compares the two kinds of figure. A design without
`power_tb.v` (such as `designs/spm`) keeps the vectorless figure.

The packet window leaves out idle time; extend `power_tb.v` to score that too.

A result scores 0 if any of these fail at signoff: setup slack below 0 ns
against the 125 ns clock, at tt **or** at the worst corner (ss_125C_4v50 at 5 V; ss_125C_3v00 for the 3.3 V
`ble_tx_uart`, whose config also fails a run on setup or hold at any corner);
hold slack below 0 at tt; power or die area above 1.05x the baseline; any
max-slew or max-capacitance violation at tt or the slow corners, or any
max-fanout violation (signoff's fix passes upsize and buffer drivers for the first
two, up to `FIX_PASSES` times (`PD_FIX_PASSES`, default 5), but not for fanout;
with `PD_FIX_HOLD=1` they also add hold delay cells); any DRC, LVS, antenna or
routing error. During the search, results whose
post-global-route estimates miss the 8 MHz gate are never candidates.

## Where to configure it

| What | File | Setting |
| --- | --- | --- |
| Clock (8 MHz), SPS, die, fixed flow settings | `designs/ble_tx/config.yaml` | `CLOCK_PERIOD: 125`, `SYNTH_PARAMETERS`, `DIE_AREA`, ... |
| Score weights | `pd/ledger.py` | `WEIGHTS` (timing, power, die, area); currently `0,0.1,0.6,0.3`; or `--weights T,P,D,A` per run, e.g. `0,0,1,0` for die area only (three numbers are T,P,A with die area unscored) |
| Die-width range, density floor | `pd/stages.py` | `DIE_WIDTH_UM`, `DENSITY_FLOOR_STEP`, `DENSITY_FLOOR_CAP` |
| The 8 MHz pass/fail gate | `pd/ledger.py` | `SETUP_FLOOR_NS` (ns of setup slack, tt and worst corner) |
| Power / die-area limit at signoff | `pd/ledger.py` | `TOLERANCE` |
| Model for each agent | `agents/policy.py` | `ROLE_MODEL` (or `--model navigator=ID`) |
| Candidate thresholds on estimates | `agents/policy.py` | `HOLD_FLOOR_NS`, `POWER_CEILING` |
| When the search stops | `agents/policy.py` | `STOP_POLICY`, `PATIENCE`, `MIN_GAIN`, `SPARE_RUNS` |
| Which knobs, and their ranges | `pd/stages.py` | `STAGES` |
| What each agent is told | `agents/prompts.py` | `NAVIGATOR`, `STAGE_AGENT`, `STOP_AGENT`, `DIAGNOSTICIAN` |
| What each agent sees | `agents/views.py` | `navigator_view`, `stage_view`, `stop_view`, `failure_view` |
| Budgets | command line | `--runs` (flow runs), `--usd` (model spend) |

`HOLD_FLOOR_NS` and `POWER_CEILING` were calibrated on picorv32, not on ble_tx;
retune them from `estimate_vs_signoff` in `report.json` after the first runs.
Keep `CLOCK_PERIOD` in step with `../librelane/config.yaml`.

## Setup (IIC-OSIC-TOOLS container)

```bash
cd /foss/designs/gf180-ble-tx/digital/agent
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
# OpenRouter key, outside the repo (the space keeps it out of shell history):
mkdir -p ~/.config/openrouter
 printf '%s' 'PASTE-YOUR-KEY-HERE' > ~/.config/openrouter/key
chmod 600 ~/.config/openrouter/key
./venv/bin/python -m pd.selftest --env      # ends with "all checks passed"
```

## Commands

```bash
./venv/bin/python -m pd.baseline                  # untouched flow, remembered afterwards
# the signed-off ble_tx_uart layout (tapeout/ble_tx_uart), 3.3 V, 330 x 300 um
PD_FIX_HOLD=1 PD_FIX_PASSES=8 ./venv/bin/python -m pd.baseline --design designs/ble_tx_uart
./venv/bin/python -m pd.stages                    # the 12 knobs (FP 1, PL 5, CTS 5, GR 1) and their ranges

# free dry run: fake model, real LibreLane
./venv/bin/python harness/mock_openrouter.py &
./venv/bin/python -m agents.graph --offline --runs 6 --work runs/dry

# a real search
./venv/bin/python -m agents.graph --runs 20 --usd 1.00 --work runs/NAME
# the same for the block with its UART front end (add --design to pd.baseline too)
./venv/bin/python -m agents.graph --design designs/ble_tx_uart --runs 20 --usd 1.50 --work runs/NAME

./venv/bin/python tools/view_run.py runs/NAME     # runs/NAME/run.html
./venv/bin/python tools/compare_runs.py runs/A runs/B
```

The signed-off layout of the answer is in `runs/NAME/signoff/<node>_final/gds/<design>.gds`.
`designs/spm` is LibreLane's small example, for checking the plumbing in a minute.

## How it is set up for ble_tx

- `designs/ble_tx/` added; it reads the RTL from `../rtl`, and an edit there
  invalidates the remembered baseline (`pd/runner.py`, `baseline_key`).
- Timing weight 0, power 0.1, die area 0.6, cell area 0.3 (`WEIGHTS`); the 8 MHz setup gate added to the signoff
  gate and to the candidate screen (`pd/ledger.py`, `pd/tree.py`).
- The gate and the clock are shown to the agents (`pd/episode.py`) and the
  prompts say that slack beyond 8 MHz earns nothing (`agents/prompts.py`).
- `pd/selftest.py` checks the gate; its other checks run with the gate off,
  as they were written for a design that misses its clock.
- The prompts name the design (ble_tx, fixed 8 MHz clock, die width searched,
  score from objective) and the max-slew caveat from `designs/ble_tx/config.yaml`.
  A design folder can replace the design-specific parts with `about.txt` and
  `navigator_notes.txt` (`agents/prompts.py`, `for_design`), as
  `designs/ble_tx_uart` does.
  The stop agent's prompt states the stopping rule, reading its numbers from
  `agents/policy.py`.
