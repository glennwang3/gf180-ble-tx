# Pre-layout static timing analysis of the Yosys netlist with OpenSTA.
# Run from this folder in the IIC-OSIC-TOOLS container, after synthesis:
#   cd ../synth && SPS=8 yosys -c synth.tcl && cd ../sta && SPS=8 sta -exit sta.tcl
# No parasitics: wires are ideal, so treat small slacks with suspicion.
# Written for OpenSTA 3.x (IIC-OSIC-TOOLS), which reports per corner with -scenes.
set sps [expr {[info exists ::env(SPS)] ? $::env(SPS) : 8}]
if {![info exists ::env(CLOCK_PERIOD)]} { set ::env(CLOCK_PERIOD) [expr {1000.0 / $sps}] }
set lib_dir $::env(PDK_ROOT)/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib
set corners {ss_125C_4v50 tt_025C_5v00 ff_n40C_5v50}

define_corners {*}$corners
foreach c $corners {
  read_liberty -corner $c $lib_dir/gf180mcu_fd_sc_mcu7t5v0__$c.lib
}
read_verilog ../synth/ble_tx_sps${sps}.syn.v
link_design ble_tx
read_sdc ble_tx.sdc

file mkdir reports
set rpt reports/sta_sps${sps}.rpt
set fh [open $rpt w]
puts $fh "ble_tx pre-layout STA, SPS=$sps, clock period $::env(CLOCK_PERIOD) ns"
close $fh

foreach c $corners {
  puts "== $c"
  report_checks -path_delay max -scenes $c -format slack_only -digits 3
  report_checks -path_delay min -scenes $c -format slack_only -digits 3
  set fh [open $rpt a]; puts $fh "== $c"; close $fh
  report_checks -path_delay max -scenes $c -format slack_only -digits 3 >> $rpt
  report_checks -path_delay min -scenes $c -format slack_only -digits 3 >> $rpt
}

report_checks -path_delay max -scenes ss_125C_4v50 -fields {slew cap fanout} -digits 3 >> $rpt
report_checks -path_delay min -scenes ff_n40C_5v50 -fields {slew cap fanout} -digits 3 >> $rpt
report_tns >> $rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators >> $rpt
puts "full report: [file normalize $rpt]"
