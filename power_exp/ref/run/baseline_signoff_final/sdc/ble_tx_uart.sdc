###############################################################################
# Created by write_sdc
###############################################################################
current_design ble_tx_uart
###############################################################################
# Timing Constraints
###############################################################################
create_clock -name clk -period 125.0000 [get_ports {clk}]
set_clock_transition 0.1500 [get_clocks {clk}]
set_clock_uncertainty 0.2500 clk
set_propagated_clock [get_clocks {clk}]
set_input_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {rst_n}]
set_input_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {uart_rx}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {air_bit}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {code_valid}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {fine_code[0]}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {fine_code[1]}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {fine_code[2]}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {fine_code[3]}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {fine_code[4]}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {fine_code[5]}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {fine_code[6]}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {fine_code[7]}]
set_output_delay 12.0000 -clock [get_clocks {clk}] -add_delay [get_ports {sym_strobe}]
###############################################################################
# Environment
###############################################################################
set_load -pin_load 0.0729 [get_ports {air_bit}]
set_load -pin_load 0.0729 [get_ports {code_valid}]
set_load -pin_load 0.0729 [get_ports {sym_strobe}]
set_load -pin_load 0.0729 [get_ports {fine_code[7]}]
set_load -pin_load 0.0729 [get_ports {fine_code[6]}]
set_load -pin_load 0.0729 [get_ports {fine_code[5]}]
set_load -pin_load 0.0729 [get_ports {fine_code[4]}]
set_load -pin_load 0.0729 [get_ports {fine_code[3]}]
set_load -pin_load 0.0729 [get_ports {fine_code[2]}]
set_load -pin_load 0.0729 [get_ports {fine_code[1]}]
set_load -pin_load 0.0729 [get_ports {fine_code[0]}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_4 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {clk}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {rst_n}]
set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__inv_1 -pin {ZN} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uart_rx}]
###############################################################################
# Design Rules
###############################################################################
set_max_transition 3.0000 [current_design]
set_max_capacitance 0.2000 [current_design]
set_max_fanout 8.0000 [current_design]
