# ble_tx_uart power experiments at 3.3 V (branch power-exp, 2026-11-19)

Worktree `~/eda/designs/gf180-ble-tx-power` (branch `power-exp` from `uart-in` f67a39c).
Nothing pushed; the main checkout is untouched. One local commit per variant:

| commit | |
|---|---|
| 417c054 | V0: agent flow at the 3.3 V corners + this harness |
| 86e2cd9 | V1: idle clock gate (sequencer + output regs) |
| abf67fe | V2: symbol-rate clock gate for the sequencer |
| be0a732 | V3: shared write gate in front of the 39 PDU byte gates, UART sh/nbit and addr gates |

`digital/rtl` on the branch tip is V3. Each variant's RTL is also in `vN/rtl`.

## Verdict

At 3.3 V, the clock gating cuts beacon-average power about 4x: 552 uW for V0
down to 132 uW for V3, at one packet per 100 ms. Idle power is almost all of the
average, and V3 cuts idle from 0.55 to 0.13 mW. V1 gets most of the idle saving
(about half), and V3 gets most of the rest. V2 only helps while transmitting
(-0.15 mW during TX), which is about 0.3% of the time for a beacon.

Two physical-design problems are independent of the gating:

1. **The 270 x 300 um die does not fit the design at 3.3 V.** V0 is 96% full
   after 3.3 V repair. V1-V3 fail detailed placement there. All numbers below
   are at 300 x 300 um.
2. **The 3 ns max-slew limit does not close at ss_125C_3v00** for any variant,
   on any die up to 350 um, with any repair setting I tried (details below).
   Setup slack is large everywhere (>= 61 ns), so this is a slew-limit (library
   range/reliability) issue, not a timing failure.

## Method

- Flow: the repo's agent flow (`digital/agent/pd`, `runner.baseline`): LibreLane
  Classic to global routing, then signoff. It uses the `designs/ble_tx_uart` config
  unchanged except for the following:
  - `STA_CORNERS` / `LIB` / `DEFAULT_CORNER`: tt_025C_3v30 (nominal),
    ss_125C_3v00 and ff_n40C_3v60, each with nom/min/max RC, and `VDD_PIN_VOLTAGE` 3.3.
    `pd/stages.py`, `runner.py` and `activity.py` use the 3.3 V libs too.
  - `DIE_WIDTH_UM` 300 (height still 300, 125 ns clock, same other settings).
  - Signoff upsizing passes off (`PD_FIX_PASSES=0`). Upsizing does not converge
    at ss_3v00, it only moves violations upstream and inflates area and power
    (330 um: 607 upsizes, 774 violations left, 1.14 mW). The buffer-insertion
    part of those passes also segfaults OpenROAD here, so it is disabled
    (`PD_NO_FIX_BUFFER`).
  - `PL_RESIZER_HOLD_SLACK_MARGIN` 0.5 ns for V0-V2. Without it V1 missed hold
    by 0.17 ns and V2 by 0.10 ns at ff. V3 congested in global routing with the
    margin, so V3 is the run without it, where hold was already met (+0.02 ns).
- Equivalence: `equiv/eq_tb.v` runs the f67a39c RTL and the variant side by side.
  It drives random ble_tx traffic (writes, starts, start-while-busy, resets mid-packet)
  and random UART traffic (frames, framing errors, glitches, resets), and compares
  every output, including ble_tx `busy`, on every clock. Result: 0 mismatches for
  V1-V3 at SPS 2, 8 and 16, about 150k cycles each. A mutant without `busy_q` is caught.
- Tests: `make test SPS=8` passes for V1, V2 and V3 (model 5, rtl 2, edge 7, uart 9,
  chain 5), and for the original. `make gl-test TOP=ble_tx_uart SPS=8` (Yosys
  netlist) and the same 9 UART tests on each **post-layout** netlist (unit delay)
  pass for V0-V3.
- Power: OpenSTA (the LibreLane build) at tt_025C_3v30 on the final netlist + nom SPEF.
  The VCDs come from an Icarus gate-level sim of that same netlist
  (`power/pw_tb.v`, PDK functional cell models). The sim loads a 37-byte-payload
  PDU (39 bytes) over uart_rx at 1 Mbaud, sets the channel, then starts the packet.
  `read_vcd -scope pw_tb/dut`: 6834/6834 pins annotated (0 unannotated) in every run.
  - (a) default activity: no VCD, the same as LibreLane's vectorless numbers.
  - (b) TX: from the start byte to the last code, 389.1 us.
  - (c) idle: 400 us after the packet, uart_rx high.
  - load: write command + 39 bytes + channel command, with frame gaps, 458 us.
  - P_avg = (P_tx t_tx + P_load t_load + P_idle (T - t_tx - t_load)) / T.

## Results (300 x 300 um, tt 3.3 V power)

| | V0 | V1 | V2 | V3 |
|---|---|---|---|---|
| run | `run_w300_plresizerh0.5_f0` | same | same | `run_w300_f0` |
| DRC (Magic / route) / LVS / antenna / XOR | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| std-cell area um2 (util) | 70,587 (87.4%) | 69,436 (86.0%) | 71,076 (88.0%) | 71,853 (89.0%) |
| cells (incl. tap/endcap) | 2,849 | 2,850 | 2,845 | 2,793 |
| ICGs / flops / clock buffers | 39 / 425 / 198 | 40 / 426 / 181 | 41 / 426 / 188 | 44 / 426 / 188 |
| setup WS tt / ss / ff ns | 105.3 / 86.5 / 109.2 | 105.6 / 87.0 / 108.6 | 98.0 / 72.5 / 108.5 | 92.7 / 61.7 / 106.2 |
| hold WS tt / ss / ff ns | 1.08 / 2.40 / 0.51 | 0.75 / 1.85 / 0.29 | 1.12 / 2.51 / 0.50 | 0.27 / 0.89 / 0.02 |
| max-slew viol. tt / ss / ff (worst RC) | 81 / 595 / 0 | 18 / 574 / 0 | 114 / 834 / 0 | 358 / 1022 / 27 |
| max-cap viol. tt / ss / ff | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 4 / 5 / 4 |
| (a) default activity mW | 0.813 | 0.573 | 0.699 | 0.580 |
| (b) TX mW | 0.674 | 0.662 | 0.521 | **0.366** |
| (c) idle mW | 0.551 | 0.301 | 0.313 | **0.131** |
| UART load mW | 0.574 | 0.324 | 0.336 | 0.159 |
| average, 1 packet / 100 ms | 551.6 uW | 302.0 uW | 314.3 uW | **132.0 uW** |
| average, 1 packet / 20 ms | 553.9 uW | 308.1 uW | 318.0 uW | **136.1 uW** |

Today's reference is 0.764 mW: the 5 V-hardened tapeout layout, (a) at
tt_025C_3v30. V0 hardened for 3.3 V reads 0.813 mW, because the 3.3 V repair
adds about 7,000 um2 of buffers.

Where the power goes, V0 -> V3:
- idle: clock 0.337 -> 0.082, flops 0.210 -> 0.045 mW
- TX: clock 0.337 -> 0.113, flops 0.223 -> 0.103 mW (logic rises 0.115 -> 0.150 mW)

What is left in V3's idle power is the clock root and tree to the free-running
flops (UART synchronizer, rx state/counter, gap, command flags, busy_q) and the
5 top-level ICG clock pins.

How the averages break down: at 100 ms a packet takes 0.39% of the time and its
UART load 0.46%, so the average is about the idle power. The load adds at most
0.6 uW. For idle as low as possible, the next step would be gating the UART's
free-running part, for example running rx only at the bit rate or waking on a
falling edge.

### Notes per variant

- **V1**: halves idle (0.55 -> 0.30 mW). TX is unchanged, as expected. Default (a)
  drops to 0.57 mW because the vectorless analysis assumes the gates are mostly off.
- **V2**: TX -0.14 mW against V1. Idle is +0.01 mW: one more ICG clock pin, plus
  layout noise. Its tt/ss slew counts are higher than V1's. That is placement noise
  of this die (the same fanout nets), not the gate.
- **V3**: the big step. With the outer write gate, the 39 byte-gate clock pins and
  their small trees see no clock outside write cycles, during TX and idle.
  Its layout is the worst one electrically: 358 tt slew and 4-5 cap violations,
  all on data nets (`_1810_`, `fanoutN`), none on clock nets, plus the smallest hold
  margin (+0.02 ns ff). Its hold-margin rerun hit routing congestion at 300 um,
  so V3 needs either 310+ um or one more placement try before it is a clean layout.
  The power numbers are not sensitive to this.

## Tried and discarded

| run | result |
|---|---|
| V0 270 um, as configured (`v0/run`) | completes, DRC/LVS clean, 96% util, 813 slew viol. at max_ss; power (a) 0.834 / TX 0.685 / idle 0.558 mW |
| V1-V3 270 um (`vN/run_w270_dplfail`) | detailed placement fails (CTS / post-GPL repair): die full |
| V0 + RUN_POST_GRT_DESIGN_REPAIR, 270/290/300/310 um | DPL failure or GRT congestion in the repair after GRT |
| V0 310/330/350 um, 5 upsize passes | completes; 767/774/110 slew viol. left, area +6-21%, power up to 1.14 mW |

To close slew at ss_125C_3v00, these seem to be the options: a slew limit
characterized for 3.0 V (the 3 ns limit is the PDK's default for the 5 V
corners), a bigger die with a repair loop that converges, or treating ss at
3.0 V as a non-signoff corner if the supply is regulated.

## Files

- `harden.py` hardens one variant (`--width`, `--fix-passes`, `--set K=V`,
  `--grt-repair`). Runs go to `vN/run*` (not committed, about 50-200 MB each).
- `power/run_power.sh vN <run>` writes `vN/power_<run>/{default,tx,idle,load}.txt`
  and the sim logs with the window times.
- `run_tests.sh vN` and `run_gl.sh vN <run>` run the repo tests and the GL tests in
  container scratch copies.
- `equiv/run_eq.sh <rtl dir> [SPS]` runs the port-equivalence bench against f67a39c.
- `collect.py` writes `results.json` (every corner, every number above).
- `logs/` has the harden, test, GL and power logs.
