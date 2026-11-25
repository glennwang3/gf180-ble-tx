# Probe: slew violations per corner on a post-GR odb, before and after repair_design.
set L /foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__
define_corners tt ss ff
read_liberty -corner tt ${L}tt_025C_3v30.lib
read_liberty -corner ss ${L}ss_125C_3v00.lib
read_liberty -corner ff ${L}ff_n40C_3v60.lib
read_db $::env(ODB)
read_sdc $::env(SDC)
set_wire_rc -signal -layer Metal2
set_wire_rc -clock -layer Metal4
set_propagated_clock [all_clocks]
estimate_parasitics -placement
proc cnt {tag} {
  foreach c {tt ss ff} {
    report_check_types -max_slew -violators -corner $c > /tmp/v_$c.rpt
    puts "$tag $c slew VIOL: [exec sh -c "grep -c VIOLATED /tmp/v_$c.rpt || true"]"
  }
}
cnt before
if {[info exists ::env(REPAIR)]} {
  repair_design -slew_margin 26 -cap_margin 20
  cnt after
  exec sh -c "head -30 /tmp/v_ss.rpt" >@ stdout
}
