#!/bin/bash
# usage (container): volt.sh <variant> <run> <PVT>  -> idle/tx power at another library voltage
set -e
V=$(cd "$1" && pwd); RUN=$2; PVT=$3; H=$(cd "$(dirname "$0")" && pwd)
FINAL=$V/$RUN/baseline_signoff_final; NL=$FINAL/nl/ble_tx_uart.nl.v
C=/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog
for w in tx idle load; do
  W=/tmp/volt_$(basename $V)_$w; mkdir -p $W
  iverilog -g2012 -DFUNCTIONAL -DUNIT_DELAY=#1 -DWIN_${w^^} -DVCD_OUT=\"$W/a.vcd\" -o $W/sim $H/pw_tb.v $C/primitives.v $C/gf180mcu_fd_sc_mcu7t5v0.v $NL
  (cd $W && vvp -n sim) >/dev/null
  echo "$w $(PVT=$PVT FINAL=$FINAL VCD=$W/a.vcd /foss/tools/openroad-librelane/bin/sta -exit $H/power.tcl | grep ^Total)"
  rm -rf $W
done
