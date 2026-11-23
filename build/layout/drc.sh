#!/bin/bash
# drc.sh <gds> <topcell> <outdir>   -> runs the GF180MCU KLayout DRC (variant E: 6LM, 9K top, MIM-B)
gds=$1; top=$2; out=$3
mkdir -p $out
python3 $PDK_ROOT/$PDK/libs.tech/klayout/tech/drc/run_drc.py --path=$gds --variant=E --topcell=$top \
    --run_dir=$out --thr=4 --run_mode=deep > $out/drc.log 2>&1
python3 /foss/designs/Diff_VCO_Second_Layout/vco_xor_layout/lyrdb_summary.py $out/*_main.lyrdb
