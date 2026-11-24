#!/bin/bash
# usage (container): resign_many.sh <variant> <out prefix> <run> [<run> ...]
# signoff again from each run's stored END state, with hold and buffer fixes
cd "$(dirname "$0")/../.."
V=$1; P=$2; shift 2
for r in "$@"; do
  PD_FIX_HOLD=1 PD_NO_FIX_BUFFER= python3 power_exp/tune/resign.py power_exp/$V $r ${P}_$r > power_exp/logs/${V}_${P}_$r.log 2>&1 &
done
wait
