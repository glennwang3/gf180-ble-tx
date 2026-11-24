#!/bin/bash
# usage: run_dbg_eq.sh <rtl dir> [SPS] [seed] [MID] [SHARE]   (inside the container)
set -e
V=$1; SPS=${2:-8}; SEED=${3:-1}; MID=${4:-0}; SHARE=${5:-1}
H=$(cd "$(dirname "$0")" && pwd); W=$(mktemp -d)
# reference: the first dbg_tx RTL (764c940)
for f in ble_tx.v ble_uart.v ble_gauss_lut.v; do
  git -c safe.directory=* -C $H show 764c940:digital/rtl/$f | sed -E 's/\bble_/o_ble_/g' > $W/o_$f
done
iverilog -g2012 ${EQ_DEFS:-} -P dbg_eq_tb.SPS=$SPS -P dbg_eq_tb.SEED0=$SEED -P dbg_eq_tb.MID=$MID -P dbg_eq_tb.SHARE=$SHARE \
  -o $W/sim $H/dbg_eq_tb.v $W/o_*.v $V/ble_tx.v $V/ble_uart.v $V/ble_gauss_lut.v
vvp -n $W/sim | tail -12
rm -rf $W
