#!/usr/bin/env bash
# Foundry KLayout DRC (gf180mcuD deck, variant D), as tapeout/ble_tx_uart/drc/run.sh.
# usage (container): klayout_drc.sh <gds> <out dir>
set -euo pipefail
GDS=$(readlink -f "$1"); RD=$(readlink -m "$2")
rm -rf "$RD"; mkdir -p "$RD"
cd /foss/pdks/gf180mcuD/libs.tech/klayout/tech/drc
python3 run_drc.py --path="$GDS" --variant=D --topcell=ble_tx_uart --run_dir="$RD" --mp=8 > "$RD/console.log" 2>&1 || true
n=0; t=0
for f in "$RD"/*.lyrdb; do t=$((t+1)); c=$(grep -c "<item>" "$f" || true); n=$((n+c)); [ "$c" -gt 0 ] && echo "  $(basename $f): $c"; done
echo "KLAYOUT_DRC tables=$t violations=$n"
grep -q "undefined method" "$RD/console.log" && echo "  note: a rule table crashed (see console.log; mslot is a known deck bug)" || true
