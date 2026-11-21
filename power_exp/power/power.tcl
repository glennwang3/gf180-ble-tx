# FINAL=<final dir> [VCD=<vcd>] sta -exit power.tcl   (tt_025C_3v30, nom SPEF)
set lib /foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__[expr {[info exists ::env(PVT)] ? $::env(PVT) : "tt_025C_3v30"}].lib
set blk $::env(FINAL)
read_liberty $lib
read_verilog $blk/nl/ble_tx_uart.nl.v
link_design ble_tx_uart
read_sdc $blk/sdc/ble_tx_uart.sdc
read_spef $blk/spef/nom/ble_tx_uart.nom.spef
set_propagated_clock [all_clocks]
if {[info exists ::env(VCD)]} {
  read_vcd -scope pw_tb/dut $::env(VCD)
  report_activity_annotation
}
report_power -digits 6
