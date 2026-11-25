#!/bin/bash
# usage: run_eq.sh <variant rtl dir> [SPS] [seed]   (inside the container)
set -e
V=$1; SPS=${2:-8}; SEED=${3:-1}
H=$(cd "$(dirname "$0")" && pwd); W=$(mktemp -d)
# reference: the RTL at f67a39c (uart-in, before any power change)
for f in ble_tx.v ble_uart.v ble_gauss_lut.v; do
  git -c safe.directory=* -C $H show f67a39c:digital/rtl/$f | sed -E 's/\bble_/o_ble_/g' > $W/o_$f
done
iverilog -g2012 ${EQ_DEFS:-} -P eq_tb.SPS=$SPS -P eq_tb.SEED0=$SEED -o $W/sim $H/eq_tb.v $W/o_*.v $V/ble_tx.v $V/ble_uart.v $V/ble_gauss_lut.v
vvp -n $W/sim | tail -12
rm -rf $W
