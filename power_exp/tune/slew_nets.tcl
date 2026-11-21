# Violating driver pins at a corner, with net name, fanout and driver cell.
set corner $::env(CORNER); set rc $::env(RC); set blk $::env(FINAL)
read_liberty /foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__${corner}.lib
read_verilog $blk/nl/ble_tx_uart.nl.v
link_design ble_tx_uart
read_sdc $blk/sdc/ble_tx_uart.sdc
read_spef $blk/spef/$rc/ble_tx_uart.$rc.spef
set_propagated_clock [all_clocks]
foreach p [get_pins -hierarchical *] {
  if {[get_property $p direction] != "output"} continue
  set s [get_property $p slew_max]
  if {$s == "" || $s <= 3.0} continue
  set n [get_nets -of_objects $p]
  set fo [llength [get_pins -of_objects $n -filter "direction == input"]]
  set c [get_property [get_cells -of_objects $p] ref_name]
  puts [format "DRV %6.2f fo=%3d %-40s %-30s %s" $s $fo [get_property $p full_name] [string map {gf180mcu_fd_sc_mcu7t5v0__ ""} $c] [get_property $n full_name]]
}
