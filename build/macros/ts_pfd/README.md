# TS_PFD: three-state PFD with frequency detection

`TS_PFD.gds` (cell `TS_PFD`, 80.4 × 32.7 µm) implements Fig. 4 of Centurelli et al., "Robust three-state PFD
architecture with enhanced frequency acquisition capabilities". It is built from the team's TSPC flip-flop and gate
layouts (in the container, `/foss/designs/Tri_State_Phase_Detector`). The originals stay unchanged; these are
DRC-clean, net-labelled copies:

| File | Cell | Changes against the original |
|---|---|---|
| `SR_FlipFlop_fixed.gds` | `SR_FlipFlop` | DRC fixes, net labels (`cells/fix_ff.py`) |
| `R_FlipFlop_fixed.gds` | `R_FlipFlop` | DRC fixes, net labels (`cells/fix_R.py`) |
| `2_Input_And_Inv_Input_fixed.gds` | `2_Input_And_Inv_Input` | DRC fixes, net labels (`cells/fix_and.py`) |
| `2_Input_And_fixed.gds` | `2_Input_And` | DRC fixes, net labels (`cells/fix_and2.py`) |
| `2_Input_Or_fixed.gds` | `2_Input_Or` | DRC fixes, net labels (`cells/fix_or.py`) |

`cells/ref_*.spice` are the cells' LVS references, and `ref_pfd.spice` is the `TS_PFD` reference. `../../pfd/build_pfd.py`
places and routes `TS_PFD`.

Ports, on M5 at the cell's south edge: `R` (reference, REF_1M), `V` (feedback, FB_1M), `UPB` (active-low UP to the
charge pump), `DN`, `3v3`, `vss`; the reference subckt also has an `UP` pin, which the top level leaves unconnected. In `E03.gds` the cells carry the `E03_`
prefix.

Checks: DRC 0 and LVS match uniquely for every cell and for `TS_PFD`; the results are in `../../pfd/verification/`.
Post-PEX tests are in `../../pfd/sim/`: the PFD alone (`pfdsim.py`), PFD + charge pump (`cpsim.py`), and the lock-state
reset race (`race.py`).
