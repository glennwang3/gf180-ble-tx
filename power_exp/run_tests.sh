#!/bin/bash
# usage (in the container): power_exp/run_tests.sh v1 [make target args...]
# Copies the worktree (without power_exp) to /tmp/pt_<v>, puts power_exp/<v>/rtl in
# digital/rtl and runs make test SPS=8 there.
set -e
V=$1; shift
R=$(cd "$(dirname "$0")/.." && pwd)
T=/tmp/pt_$V
rm -rf $T; mkdir -p $T
tar -C $R --exclude=./power_exp --exclude=.git --exclude='*/sim_build*' -cf - . | tar -C $T -xf -
cp $R/power_exp/$V/rtl/*.v $T/digital/rtl/
cd $T && make ${@:-test SPS=8}
