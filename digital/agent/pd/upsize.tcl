# Upsize the drivers of nets that broke the slew or capacitance limit at signoff,
# then legalize the placement again. Run by pd/runner.py between signoff passes.
#
# env: LIB      a Liberty file of the cell library (for function and drive sizes)
#      IN_ODB   the post-global-route database to change
#      OUT_DIR  where the changed views are written
#      PINS     "pin ratio pin ratio ...": violating pins from the signoff checks,
#               each with its value over the limit (1.18 = 18% over)
#      DONE     drivers an earlier pass already upsized (may be empty)
#      BUFFER   the buffer cell to insert where upsizing is not enough
#
# A driver goes to the smallest size of its own cell family with at least twice its
# drive, or four times when the pin was more than 15% over; if the family has no
# size that large, to its largest. A driver that is already at its largest size, or
# that an earlier pass upsized and whose net still fails, gets a buffer instead: one
# BUFFER cell placed at the driver, which then drives only the stub to it while the
# buffer drives the net. Clock nets are only ever upsized: a buffer there would move
# the clock tree's timing. Only drivers and the new buffers change, never the loads.
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

# Driver instance -> worst ratio among the violating pins on its net, and the net.
array set worst {}
array set driven {}
foreach {pin ratio} $::env(PINS) {
    if {[catch {set p [get_pins $pin]}] || $p == ""} { continue }
    set net [get_nets -of_objects $p]
    if {$net == ""} { continue }
    foreach d [get_pins -of_objects $net -filter "direction == output"] {
        set inst [get_property [get_cells -of_objects $d] full_name]
        if {![info exists worst($inst)] || $ratio > $worst($inst)} { set worst($inst) $ratio }
        set driven($inst) [get_property $net full_name]
    }
}

# One BUFFER cell after a driver, built with odb calls. (OpenROAD's insert_buffer
# segfaults in dbBlock::makeNewName on these databases.) The driver keeps only the
# stub to the buffer; the buffer drives the original net; its supply pins join the
# driver's supply nets. Names carry the pass (OUT_DIR) so later passes do not clash.
set fixbuf_n 0
proc odb_buffer {inst_name net_name bufcell x y} {
    global fixbuf_n
    set block [ord::get_db_block]
    set net [$block findNet $net_name]
    set inst [$block findInst $inst_name]
    set master [[ord::get_db] findMaster $bufcell]
    if {$net == "NULL" || $inst == "NULL" || $master == "NULL"} { error "$inst_name/$net_name/$bufcell not found" }
    set drv ""
    foreach it [$net getITerms] {
        if {[[$it getInst] getName] == $inst_name && [$it isOutputSignal]} { set drv $it }
    }
    if {$drv == ""} { error "no output of $inst_name on $net_name" }
    set tag [file tail $::env(OUT_DIR)]
    while 1 {
        incr fixbuf_n
        set name "fixbuf_${tag}_$fixbuf_n"
        if {[$block findInst $name] == "NULL" && [$block findNet "${name}_in"] == "NULL"
            && [$block findNet "${name}_out"] == "NULL"} { break }
    }
    # Two or more loads: split. The farther half of the loads (from the driver) moves
    # behind the buffer, placed at their centroid; the driver keeps the nearer half
    # and the buffer input. This cuts the driver's load for slew and capacitance.
    set dloc [[$drv getInst] getLocation]
    set loads {}
    foreach it [$net getITerms] {
        if {$it == $drv || [$it isOutputSignal]} { continue }
        set l [[$it getInst] getLocation]
        set d [expr {abs([lindex $l 0] - [lindex $dloc 0]) + abs([lindex $l 1] - [lindex $dloc 1])}]
        lappend loads [list $d $it $l]
    }
    if {[llength $loads] >= 2} {
        set loads [lsort -real -decreasing -index 0 $loads]
        set far [lrange $loads 0 [expr {[llength $loads] / 2 - 1}]]
        set nn [odb::dbNet_create $block "${name}_out"]
        set b [odb::dbInst_create $block $master $name]
        set sx 0; set sy 0
        foreach f $far {
            set it [lindex $f 1]
            $it disconnect
            $it connect $nn
            set sx [expr {$sx + [lindex [lindex $f 2] 0]}]
            set sy [expr {$sy + [lindex [lindex $f 2] 1]}]
        }
        foreach it [$b getITerms] {
            set mt [$it getMTerm]
            set st [$mt getSigType]
            if {$st == "POWER" || $st == "GROUND"} {
                foreach pit [$inst getITerms] {
                    if {[[$pit getMTerm] getSigType] == $st && [$pit getNet] != "NULL"} {
                        $it connect [$pit getNet]; break
                    }
                }
            } elseif {[$mt getIoType] == "INPUT"} {
                $it connect $net
            } else {
                $it connect $nn
            }
        }
        set n [llength $far]
        $b setLocation [expr {$sx / $n}] [expr {$sy / $n}]
        $b setPlacementStatus PLACED
        return "split [llength $far]/[llength $loads]"
    }
    set nn [odb::dbNet_create $block "${name}_in"]
    set b [odb::dbInst_create $block $master $name]
    $drv disconnect
    $drv connect $nn
    foreach it [$b getITerms] {
        set mt [$it getMTerm]
        set st [$mt getSigType]
        if {$st == "POWER" || $st == "GROUND"} {
            foreach pit [$inst getITerms] {
                if {[[$pit getMTerm] getSigType] == $st && [$pit getNet] != "NULL"} {
                    $it connect [$pit getNet]; break
                }
            }
        } elseif {[$mt getIoType] == "INPUT"} {
            $it connect $nn
        } else {
            $it connect $net
        }
    }
    set dbu [$block getDbUnitsPerMicron]
    $b setLocation [expr {int($x * $dbu)}] [expr {int($y * $dbu)}]
    $b setPlacementStatus PLACED
    return "after driver"
}

set done [expr {[info exists ::env(DONE)] ? $::env(DONE) : ""}]
set block [ord::get_db_block]
set changed 0
foreach inst [array names worst] {
    set ref [get_property [get_cells $inst] ref_name]
    # clock-tree cells by name (CTS names them clkbuf_*, delaybuf_*, clkload*) or
    # gating cells; a data buffer the repair happened to build from a clkbuf cell
    # (fanoutN) is a data buffer.
    set clock [expr {[regexp {__icg} $ref] || [regexp {^(clkbuf_|delaybuf_|clkload)} $inst]}]
    set to [stronger $ref $worst($inst)]
    set top [expr {$to == "" || $to == $ref}]
    if {!$clock && ($top || [lsearch -exact $done $inst] >= 0) && [info exists ::env(BUFFER)]} {
        set loc [[$block findInst $inst] getLocation]
        set dbu [$block getDbUnitsPerMicron]
        set x [expr {[lindex $loc 0] / double($dbu)}]
        set y [expr {[lindex $loc 1] / double($dbu)}]
        if {![catch {odb_buffer $inst $driven($inst) $::env(BUFFER) $x $y} e]} {
            puts "BUFFER: $inst $driven($inst) $::env(BUFFER) $e"
            incr changed
            continue
        }
        puts "UPSIZE: $inst could not be buffered: $e"
    }
    if {$top} { puts "UPSIZE: $inst $ref has no larger size"; continue }
    replace_cell [get_cells $inst] [get_lib_cells $to]
    puts "UPSIZE: $inst $ref $to"
    incr changed
}
# Hold (PD_FIX_HOLD in pd/runner.py): a delay cell in front of each failing endpoint
# pin, placed at its flop; only that pin's path gets slower.
proc odb_hold_delay {pin cell} {
    global fixbuf_n
    set block [ord::get_db_block]
    set k [string last "/" $pin]
    set iname [string range $pin 0 [expr {$k - 1}]]
    set mname [string range $pin [expr {$k + 1}] end]
    set inst [$block findInst $iname]
    if {$inst == "NULL"} { error "no instance $iname" }
    set it [$inst findITerm $mname]
    if {$it == "NULL"} { error "no pin $pin" }
    set net [$it getNet]
    if {$net == "NULL"} { error "$pin unconnected" }
    set master [[ord::get_db] findMaster $cell]
    set tag [file tail $::env(OUT_DIR)]
    while 1 {
        incr fixbuf_n
        set name "fixhold_${tag}_$fixbuf_n"
        if {[$block findInst $name] == "NULL" && [$block findNet "${name}_out"] == "NULL"} { break }
    }
    set nn [odb::dbNet_create $block "${name}_out"]
    set d [odb::dbInst_create $block $master $name]
    $it disconnect
    $it connect $nn
    foreach dt [$d getITerms] {
        set mt [$dt getMTerm]
        set st [$mt getSigType]
        if {$st == "POWER" || $st == "GROUND"} {
            foreach pit [$inst getITerms] {
                if {[[$pit getMTerm] getSigType] == $st && [$pit getNet] != "NULL"} {
                    $dt connect [$pit getNet]; break
                }
            }
        } elseif {[$mt getIoType] == "INPUT"} {
            $dt connect $net
        } else {
            $dt connect $nn
        }
    }
    set loc [$inst getLocation]
    $d setLocation [lindex $loc 0] [lindex $loc 1]
    $d setPlacementStatus PLACED
}
if {[info exists ::env(HOLD_PINS)]} {
    foreach pin $::env(HOLD_PINS) {
        if {[catch {odb_hold_delay $pin $::env(HOLD_DELAY)} e]} {
            puts "HOLD: $pin could not be delayed: $e"
        } else {
            puts "HOLD: $pin $::env(HOLD_DELAY)"
            incr changed
        }
    }
}

if {$changed == 0} { exit 3 }

detailed_placement
check_placement
set d $::env(OUT_DIR)
write_db $d/upsized.odb
write_def $d/upsized.def
write_verilog $d/upsized.nl.v
write_verilog -include_pwr_gnd $d/upsized.pnl.v
