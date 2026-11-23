#!/bin/bash
# conv_iter.sh SIZES : rebuild RF_CONV_PA with N widths SIZES, DRC, LVS, RC extract, replay test
cd /foss/designs/pll_compact/layout
export PDK_ROOT=/foss/pdks PDK=gf180mcuD TECH=/foss/designs/pll_integration_repo/build/tech/gf180mcuE.tech
CONV_SIZES=$1 python3 build_conv.py > build.log 2>&1 || { tail -2 build.log; exit 1; }
grep bbox build.log
bash drc.sh RF_CONV_PA.gds RF_CONV_PA drc_conv | tail -1
rm -rf pex_conv; python3 lvs_cell.py RF_CONV_PA.gds RF_CONV_PA RF_CONV_PA.spice pex_conv | tail -1
bash lvs.sh pex_conv/RF_CONV_PA_flat.gds RF_CONV_PA RF_CONV_PA.spice pex_conv rc > /dev/null 2>&1
cd /foss/designs/pll_compact/sim/conv_dbg && python3 run.py 2>&1 | grep -E '^(sch|pex) '
