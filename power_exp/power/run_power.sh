#!/bin/bash
# usage (container): run_power.sh <variant dir> [run dir name, default run]
#   -> <variant>/power_<run>/{default,load,tx,idle}.txt
set -e
V=$(cd "$1" && pwd); H=$(cd "$(dirname "$0")" && pwd)
RUN=${2:-run}
FINAL=$V/$RUN/baseline_signoff_final
NL=$FINAL/nl/ble_tx_uart.nl.v
O=$V/power_$RUN${PW_SUFFIX:-}; mkdir -p $O
C=/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog
STA=/foss/tools/openroad-librelane/bin/sta
FINAL=$FINAL $STA -exit $H/power.tcl > $O/default.txt 2>&1
for w in load tx idle; do
  W=/tmp/pw_$(basename $V)_${RUN}${PW_SUFFIX:-}_$w; mkdir -p $W
  iverilog -g2012 ${PW_DEFS:-} -DFUNCTIONAL -DUNIT_DELAY=#1 -DWIN_${w^^} -DVCD_OUT=\"$W/a.vcd\" -o $W/sim \
    $H/pw_tb.v $C/primitives.v $C/gf180mcu_fd_sc_mcu7t5v0.v $NL
  (cd $W && vvp -n sim) > $O/sim_$w.txt 2>&1
  FINAL=$FINAL VCD=$W/a.vcd $STA -exit $H/power.tcl > $O/$w.txt 2>&1
  rm -rf $W
done
grep -H "WINDOW_NS" $O/sim_*.txt; grep -H "^Total" $O/*.txt
