#!/bin/bash
# full-chip transmit at TT and FF (PLL_TSPFD_C1 loop + transistor-level RF/PA windows), at most 3 ngspice in total
cd /foss/designs/pll_compact/sim/tx_tt
LN=/foss/designs/pll_compact/layout/pex_loop_ts_c1/LOOP_PART_rcpex_ff_lin.spice
COMMON="UIC=1 FBSHARP=1000 REFTR=0.3n TMAX=0.5n TSTEP=0.5n RSHUNT=1e15 LOOPNET=$LN"
jobs=(
  "env $COMMON CORNER=ff-40 VCO=1.239492e9,1.85,1.020075e9 RVCO=2990 python3 tx_loop_tt.py loop_ff_c1 512 500 0.632 1.2 vtune_curve_ff.txt stim/full.pwl"
  "env CORNER=ff-40 TAIL=1.514 VDDVCO=1.8127 python3 deck_tt.py dataff_c0 pwl:stim/c0.pwl 3350 lite"
  "env CORNER=ff-40 TAIL=1.514 VDDVCO=1.8127 python3 deck_tt.py dataff_c1 pwl:stim/c1.pwl 3350 lite"
  "env $COMMON CORNER=tt27 python3 tx_loop_tt.py loop_tt_c1l 512 500 1.435 1.2 vtune_curve_tt.txt stim/full.pwl"
  "env CORNER=ff-40 TAIL=1.514 VDDVCO=1.8127 python3 deck_tt.py dataff_c2 pwl:stim/c2.pwl 3250 lite"
)
for j in "${jobs[@]}"; do
  while [ "$(pgrep -x ngspice | wc -l)" -ge 3 ]; do sleep 15; done
  echo "$(date +%T) start: $j"
  $j >> queue_full.out 2>&1 &
  sleep 30
done
wait
echo "$(date +%T) all done"
