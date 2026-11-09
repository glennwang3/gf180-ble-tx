# Agent-driven layout of the BLE modulator

An agentic LibreLane flow for `ble_tx`.
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
Timing is a pass/fail gate and the score is power and standard-cell area:

    score = (P0 / P)^0.1 x (A0 / A)^0.9      1.0 = LibreLane untouched

The die is fixed at 1400 x 300 um (`DIE_AREA` in `designs/ble_tx/config.yaml`), so
area here means standard-cell area: how little of that die the layout uses.

A result scores 0 if any of these fail at signoff: setup slack below 0 ns
against the 125 ns clock, at tt **or** at the worst corner (ss_125C_4v50);
hold slack below 0 at tt; power or die area above 1.05x the baseline; any
DRC, LVS, antenna or routing error. During the search, results whose
post-global-route estimates miss the 8 MHz gate are never candidates.

## Where to configure it

| What | File | Setting |
| --- | --- | --- |
| Clock (8 MHz), SPS, die, fixed flow settings | `designs/ble_tx/config.yaml` | `CLOCK_PERIOD: 125`, `SYNTH_PARAMETERS`, `DIE_AREA`, ... |
| Score weights | `pd/ledger.py` | `WEIGHTS` (timing, power, area); currently `0,0.1,0.9`; or `--weights T,P,A` per run, e.g. `0,0,1` for area only |
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
./venv/bin/python -m pd.stages                    # the nine knobs and their ranges 

# free dry run: fake model, real LibreLane
./venv/bin/python harness/mock_openrouter.py &
./venv/bin/python -m agents.graph --offline --runs 6 --work runs/dry

# a real search
./venv/bin/python -m agents.graph --runs 20 --usd 1.00 --work runs/NAME

./venv/bin/python tools/view_run.py runs/NAME     # runs/NAME/run.html
./venv/bin/python tools/compare_runs.py runs/A runs/B
```

The signed-off layout of the answer is in `runs/NAME/signoff/<node>_final/gds/ble_tx.gds`.
`designs/spm` is LibreLane's small example, for checking the plumbing in a minute.

## How it is set up for ble_tx

- `designs/ble_tx/` added; it reads the RTL from `../rtl`, and an edit there
  invalidates the remembered baseline (`pd/runner.py`, `baseline_key`).
- Timing weight 0, power 0.1, area 0.9; the 8 MHz setup gate added to the signoff
  gate and to the candidate screen (`pd/ledger.py`, `pd/tree.py`).
- The gate and the clock are shown to the agents (`pd/episode.py`) and the
  prompts say that slack beyond 8 MHz earns nothing (`agents/prompts.py`).
- `pd/selftest.py` checks the gate; its other checks run with the gate off,
  as they were written for a design that misses its clock.
- The prompts name the design (ble_tx, fixed 8 MHz clock and die, power and cell
  area as the score) and the max-slew caveat from `designs/ble_tx/config.yaml`.
  The stop agent's prompt states the stopping rule, reading its numbers from
  `agents/policy.py`.
