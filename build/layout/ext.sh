#!/bin/bash
# ext.sh <gds> <cell> <outdir>: magic (gf180mcuE) flat LVS extraction -> <outdir>/<cell>.spice
gds=$(readlink -f $1); cell=$2; out=$3
mkdir -p $out; cd $out
printf 'crashbackups stop\ntech load {/foss/designs/pll_integration_repo/build/tech/gf180mcuE.tech}\nscalegrid 1 10\ndrc off\n' > magicrc_e
cat > ext.tcl <<TCL
gds read $gds
load $cell
select top cell
extract all
ext2spice lvs
ext2spice -o ${cell}.spice
quit -noprompt
TCL
magic -dnull -noconsole -rcfile magicrc_e ext.tcl > magic.log 2>&1
grep -c "^X" ${cell}.spice
