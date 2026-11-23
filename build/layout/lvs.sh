#!/bin/bash
# lvs.sh <gds> <cell> <ref.spice> <outdir> [rc]  -> magic extraction (+ optional RC PEX) and netgen LVS
PDK_ROOT=${PDK_ROOT:-/foss/pdks}; PDK=${PDK:-gf180mcuD}
gds=$(readlink -f $1); cell=$2; ref=$(readlink -f $3); out=$4; rc=$5
mkdir -p $out; cd $out
cat > extract.tcl <<TCL
gds read $gds
load $cell
select top cell
extract all
ext2spice lvs
ext2spice -o ${cell}_lvs.spice
TCL
if [ -n "$rc" ]; then cat >> extract.tcl <<TCL
flatten ${cell}_FLAT
load ${cell}_FLAT
select top cell
extract do resistance
extract all
ext2sim labels on
ext2sim
extresist tolerance 1
extresist all
ext2spice lvs
ext2spice cthresh 0.01
ext2spice extresist on
ext2spice -o ${cell}_rcpex.spice
TCL
fi
if [ -n "$rc" ]; then cat >> extract.tcl <<TCL
TCL
fi
echo "quit -noprompt" >> extract.tcl
if [ -n "$TECH" ]; then
  printf 'crashbackups stop
tech load {%s}
scalegrid 1 10
drc off
' "$TECH" > magicrc_e
  RC=magicrc_e
else
  RC=$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc
fi
magic -dnull -noconsole -rcfile $RC extract.tcl > magic.log 2>&1
netgen -batch lvs "${cell}_lvs.spice $cell" "$ref $cell" $PDK_ROOT/$PDK/libs.tech/netgen/${PDK}_setup.tcl lvs.report > netgen.log 2>&1
grep -E "Final result|Circuits match|do not match|Netlists match|mismatch" lvs.report | tail -5
