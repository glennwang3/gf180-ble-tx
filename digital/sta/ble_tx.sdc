# Timing constraints for ble_tx, shared by pre-layout STA (sta.tcl).
# Clock period in ns; override with CLOCK_PERIOD (125 = 8 MHz for SPS=8).
set clk_period [expr {[info exists ::env(CLOCK_PERIOD)] ? $::env(CLOCK_PERIOD) : 125.0}]
set io_frac    0.3   ;# share of the period spent outside the block on each I/O

create_clock -name clk -period $clk_period [get_ports clk]

# Pre-layout: ideal clock, so budget skew, jitter and wire delay as uncertainty.
set_clock_uncertainty -setup 1.0  [get_clocks clk]
set_clock_uncertainty -hold  0.25 [get_clocks clk]
set_clock_transition 0.5 [get_clocks clk]

set inputs [list rst_n wr_en wr_addr wr_data channel start]
set_input_delay  [expr {$io_frac * $clk_period}] -clock clk [get_ports $inputs]
set_output_delay [expr {$io_frac * $clk_period}] -clock clk [all_outputs]

set_driving_cell -lib_cell gf180mcu_fd_sc_mcu7t5v0__buf_2 -pin Z [get_ports $inputs]
set_load 0.05 [all_outputs]

# Same design-rule limits LibreLane signs off against
set_max_transition 3.0 [current_design]
set_max_fanout 16 [current_design]
