#!/bin/bash
# usage (container): top.sh <variant> <run> <win>  -> top instances by power for that window
set -e
V=$(cd "$1" && pwd); RUN=$2; w=$3; H=$(cd "$(dirname "$0")" && pwd)
FINAL=$V/$RUN/baseline_signoff_final; NL=$FINAL/nl/ble_tx_uart.nl.v
C=/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog
W=/tmp/top_$(basename $V)_$w; mkdir -p $W
iverilog -g2012 -DFUNCTIONAL -DUNIT_DELAY=#1 -DWIN_${w^^} -DVCD_OUT=\"$W/a.vcd\" -o $W/sim $H/pw_tb.v $C/primitives.v $C/gf180mcu_fd_sc_mcu7t5v0.v $NL
(cd $W && vvp -n sim) >/dev/null
sed 's/^report_power -digits 6$/report_power -digits 6\nreport_power -highest_power_instances 60 -digits 6/' $H/power.tcl > $W/p.tcl
FINAL=$FINAL VCD=$W/a.vcd /foss/tools/openroad-librelane/bin/sta -exit $W/p.tcl
rm -rf $W
