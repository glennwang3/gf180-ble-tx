#!/bin/bash
# usage (container): gl_final.sh <variant> <final dir (relative to the variant)>
# Gate-level tests of a post-layout netlist (unit delay): the UART tests, the
# debug UART test (all 80 offsets) and the clock-stop tests.
set -e
V=$1; F=$2
R=$(cd "$(dirname "$0")/../.." && pwd)
NL=$R/power_exp/$V/$F/nl/ble_tx_uart.nl.v
T=/tmp/glf_$V; rm -rf $T; mkdir -p $T
tar -C $R --exclude=./power_exp --exclude=.git --exclude='*/sim_build*' -cf - . | tar -C $T -xf -
cp $R/power_exp/$V/rtl/*.v $T/digital/rtl/
cp $NL $T/digital/synth/ble_tx_uart_sps8.syn.v
cd $T/digital/test
echo "=== UART tests, post-layout"; GL=1 SPS=8 python3 test_ble_tx_uart.py
echo "=== dbg_tx test, post-layout"; GL=1 NETLIST=$NL python3 test_ble_dbg_tx.py
echo "=== clock-stop tests, post-layout"; cd $R/power_exp/tune && NETLIST=$NL python3 test_clock_stop.py
echo "GL_FINAL_DONE"
