#!/bin/bash
# usage (container): power_exp/tune/run_v.sh <variant> <width> <tag> [more harden.py args]
# The 3.3 V recipe (see SUMMARY.md) at one width; signoff fix passes upsize, then
# buffer (odb_buffer in pd/upsize.tcl) unless BUF=0. Log: logs/<variant>_<tag>_w<width>.log
cd "$(dirname "$0")/../.."
V=$1; W=$2; T=$3; shift 3
if [ "${BUF:-1}" = 1 ]; then export PD_NO_FIX_BUFFER=; fi
EX="gf180mcu_fd_sc_mcu7t5v0__dly* gf180mcu_fd_sc_mcu7t5v0__buf_1 gf180mcu_fd_sc_mcu7t5v0__nor4_1 gf180mcu_fd_sc_mcu7t5v0__nor3_1${EXTRA_EX:+ $EXTRA_EX}"
python3 power_exp/harden.py power_exp/$V --width $W --grt-repair --tag ${T}_w$W \
  --set "EXTRA_EXCLUDED_CELLS=$EX" --set PL_RESIZER_HOLD_SLACK_MARGIN=0.25 \
  --set PL_MAX_DISPLACEMENT_Y=300 --set 'SETUP_VIOLATION_CORNERS=*' \
  --set 'HOLD_VIOLATION_CORNERS=*' "$@" > power_exp/logs/${V}_${T}_w$W.log 2>&1
