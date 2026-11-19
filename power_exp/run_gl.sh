#!/bin/bash
# usage (container): run_gl.sh v3 [run dir name, default run]
# 1) make gl-test TOP=ble_tx_uart SPS=8 (Yosys netlist of the variant's RTL)
# 2) the same cocotb test on the variant's post-layout netlist (unit delay)
set -e
V=$1; RUN=${2:-run}
R=$(cd "$(dirname "$0")/.." && pwd)
T=/tmp/pg_$V
rm -rf $T; mkdir -p $T
tar -C $R --exclude=./power_exp --exclude=.git --exclude='*/sim_build*' -cf - . | tar -C $T -xf -
cp $R/power_exp/$V/rtl/*.v $T/digital/rtl/
cd $T
echo "=== synth gl-test"
make gl-test TOP=ble_tx_uart SPS=8
grep -c icgtp digital/synth/ble_tx_uart_sps8.syn.v | sed 's/^/ICG instances in Yosys netlist: /'
echo "=== post-layout netlist gl-test"
cp $R/power_exp/$V/$RUN/baseline_signoff_final/nl/ble_tx_uart.nl.v digital/synth/ble_tx_uart_sps8.syn.v
cd digital/test && GL=1 SPS=8 python3 test_ble_tx_uart.py
