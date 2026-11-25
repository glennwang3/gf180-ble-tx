# Usage: FINAL=<..._final dir> CORNER=ss_125C_3v00 RC=max sta -exit sta_corner.tcl
set corner $::env(CORNER)
set rc [expr {[info exists ::env(RC)] ? $::env(RC) : "nom"}]
set libdir /foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib
set blk $::env(FINAL)
puts "=== CORNER ${rc}_$corner ==="
read_liberty $libdir/gf180mcu_fd_sc_mcu7t5v0__${corner}.lib
read_verilog $blk/nl/ble_tx_uart.nl.v
link_design ble_tx_uart
read_sdc $blk/sdc/ble_tx_uart.sdc
read_spef $blk/spef/$rc/ble_tx_uart.$rc.spef
set_propagated_clock [all_clocks]
puts "--- POWER ---"
report_power -digits 6
puts "--- SETUP ---"
report_checks -path_delay max -fields {slew cap fanout} -digits 3
puts "--- HOLD ---"
report_checks -path_delay min -fields {slew cap fanout} -digits 3
report_worst_slack -max -digits 3
report_worst_slack -min -digits 3
report_tns -digits 3
puts "--- DRV ---"
report_check_types -max_slew -max_capacitance -max_fanout -violators
puts "--- END ---"
