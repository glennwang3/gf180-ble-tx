# Violating driver pins (slew > 3 ns, or cap over the pin's max) at one corner.
set corner $::env(CORNER); set rc $::env(RC); set blk $::env(FINAL)
read_liberty /foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__${corner}.lib
read_verilog $blk/nl/ble_tx_uart.nl.v
link_design ble_tx_uart
read_sdc $blk/sdc/ble_tx_uart.sdc
read_spef $blk/spef/$rc/ble_tx_uart.$rc.spef
set_propagated_clock [all_clocks]
report_check_types -max_slew -max_capacitance -violators
