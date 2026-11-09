# Upsize the drivers of nets that broke the slew or capacitance limit at signoff,
# then legalize the placement again. Run by pd/runner.py between signoff passes.
#
# env: LIB      a Liberty file of the cell library (for function and drive sizes)
#      IN_ODB   the post-global-route database to change
#      OUT_DIR  where the changed views are written
#      PINS     "pin ratio pin ratio ...": violating pins from the signoff checks,
#               each with its value over the limit (1.18 = 18% over)
#
# A driver goes to the smallest size of its own cell family with at least twice its
# drive, or four times when the pin was more than 15% over; if the family has no
# size that large, to its largest. Only drivers are changed, never the loads.
read_liberty $::env(LIB)
read_db $::env(IN_ODB)

proc size_of {name} {
    if {[regexp {^(.*)_([0-9]+)$} $name -> family n]} { return [list $family $n] }
    return {}
}

proc stronger {ref ratio} {
    set parts [size_of $ref]
    if {$parts == {}} { return "" }
    lassign $parts family n
    set want [expr {$ratio > 1.15 ? $n * 4 : $n * 2}]
    set pick ""; set pick_n 0; set top ""; set top_n $n
    foreach c [get_lib_cells ${family}_*] {
        set name [get_property $c name]
        set p [size_of $name]
        if {$p == {} || [lindex $p 0] != $family} { continue }
        set m [lindex $p 1]
        if {$m >= $want && ($pick == "" || $m < $pick_n)} { set pick $name; set pick_n $m }
        if {$m > $top_n} { set top $name; set top_n $m }
    }
    return [expr {$pick != "" ? $pick : $top}]
}

# Driver instance -> worst ratio among the violating pins on its net.
array set worst {}
foreach {pin ratio} $::env(PINS) {
    if {[catch {set p [get_pins $pin]}] || $p == ""} { continue }
    set net [get_nets -of_objects $p]
    if {$net == ""} { continue }
    foreach d [get_pins -of_objects $net -filter "direction == output"] {
        set inst [get_property [get_cells -of_objects $d] full_name]
        if {![info exists worst($inst)] || $ratio > $worst($inst)} { set worst($inst) $ratio }
    }
}

set changed 0
foreach inst [array names worst] {
    set ref [get_property [get_cells $inst] ref_name]
    set to [stronger $ref $worst($inst)]
    if {$to == "" || $to == $ref} { puts "UPSIZE: $inst $ref has no larger size"; continue }
    replace_cell [get_cells $inst] [get_lib_cells $to]
    puts "UPSIZE: $inst $ref $to"
    incr changed
}
if {$changed == 0} { exit 3 }

detailed_placement
check_placement
set d $::env(OUT_DIR)
write_db $d/upsized.odb
write_def $d/upsized.def
write_verilog $d/upsized.nl.v
write_verilog -include_pwr_gnd $d/upsized.pnl.v
