#!/bin/bash
# PA runs with the off-chip harmonic filter; starts only after queue_full.sh launched all its jobs (keeps <= 3 ngspice)
cd /foss/designs/pll_compact/sim/tx_tt
until [ "$(grep -c start queue_full.log)" -ge 5 ]; do sleep 30; done
for j in "env LPF=1 CORNER=tt27 TAIL=1.686 VDDVCO=2.3389 python3 deck_tt.py pa_tt_lpf 1.2 300" \
         "env LPF=1 CORNER=ff-40 TAIL=1.514 VDDVCO=1.8127 python3 deck_tt.py pa_ff_lpf 1.2 300"; do
  while [ "$(pgrep -x ngspice | wc -l)" -ge 3 ]; do sleep 15; done
  echo "$(date +%T) start: $j"; $j >> queue_lpf.out 2>&1; sleep 5
done
echo "$(date +%T) all done"
