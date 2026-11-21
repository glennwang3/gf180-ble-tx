# hierarchical area breakdown: RTL=<dir> yosys -c synth_stat.tcl
yosys -import
set lib /foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
read_liberty -lib $lib
set r $::env(RTL)
read_verilog -defer $r/ble_gauss_lut.v $r/ble_tx.v $r/ble_uart.v
hierarchy -check -top ble_tx_uart -chparam SPS 8
synth -top ble_tx_uart
dfflibmap -liberty $lib
abc -liberty $lib
opt_clean -purge
tee -o $::env(OUT) stat -liberty $lib
