#setenv BREAK_NAME allocator_unit/arb_N_X/state_reg[1] :QN
#setenv BREAK_TIME_BEFORE 1000
#setenv BREAK_TIME_AFTER 1000
#setenv FAULT_VALUE 0
#setenv FAULT_LENGTH 10

# Load Env vars
global env; 
set RESULTFOLDER $env(RESULTFOLDER)
set PROPERTYPATH $env(PROPERTYPATH) 
set STARTID $env(STARTID)
set RESULTFILE $env(RESULTFILE)
set SCENARIOFILE $env(SCENARIOFILE)
set ROUTERFOLDER $env(ROUTERFOLDER)
if {[info exists env(DEBUG)]} {
    set DEBUG $env(DEBUG)
} else {
    set DEBUG "false"
}


puts $ROUTERFOLDER
puts $PROPERTYPATH
puts $RESULTFOLDER/work
puts $STARTID


# define library work


vlib work
file rename work $RESULTFOLDER/work
puts "work folder exists: [file exists $RESULTFOLDER/work]"
vmap work $RESULTFOLDER/work
#prevent race condition between instances!


#map it to the folder of this process


# Include files and compile them

vlog "/cad/dk/c/v4.11/verilog/c18a6/c18_CORELIB.v"	
vlog "$ROUTERFOLDER/gate_level_netlist.v"	
vcom -O5 "TB_Package_32_bit_credit_based.vhd"
vcom -O5 "Router_credit_based_tb.vhd"
 


# Start the simulation
vsim -novopt -t 1ns -Gsent_file=$RESULTFOLDER/sent.txt -Grecv_file=$RESULTFOLDER/received.txt -Gscenario_file=$SCENARIOFILE work.tb_router

set concatdresultfile [open $RESULTFILE "w"]
fconfigure $concatdresultfile -translation binary



global env; 
puts $PROPERTYPATH
set fp [open $PROPERTYPATH  r]


fconfigure $fp -buffering line
gets $fp data
set i $STARTID
while {$data != ""} {
    puts "starting experiment #$i"
    #split line
    set params [regexp -all -inline {\S+} $data]
    #prepare next line
    
    #set params
    set name [lindex $params 4]
    set tmpfirst [string first "U" $name]

    # If it starts with U
    if {$tmpfirst != 0} {
        append name " "
    }
    append name [lindex $params 5] 
    set time_before  [lindex $params 0] 
    set time_after [lindex $params 1] 
    set val [lindex $params 2] 
    set fault_length [lindex $params 3] 
    #add wave -position insertpoint {sim/:tb_router:R_5:\\$name}

    puts "Breaking the circuit: Name: '$name' Time: $time_before ns Value: $val Length of fault: $fault_length ns"
    source $ROUTERFOLDER/record_modules.tcl
    
    # Run the simulation
    run $time_before ns
    # for reference: force -drive {sim/:tb_router:R_5:\FIFO_N/FIFO_MEM_2_reg[0] :D} St1 0 -cancel 1
    # force -freeze sim/:tb_router:R_5:\\$name St0 start_after ns -cancel clock_cycle_length ns
    puts "Ran for $time_before. Breaking now!"
    if {$name == "nofault :nofault"} {
         puts "parameter is nofault, will not break anything."
    } else {
        force -freeze "sim/:tb_router:R_5:$name" St$val 0ns -cancel $fault_length ns
    }
    puts "Broke the circuit!"
    run $time_after ns
    #reset simulation
    restart
    #handle results
    puts $concatdresultfile "-----"
    puts $concatdresultfile "$i"
    puts $concatdresultfile $data
    puts $concatdresultfile "!modules:"
    # exclude date of the file, only keep the hash.
    foreach file [glob -nocomplain "$RESULTFOLDER/*.vcd"] {
        set filename [file tail [file rootname $file]]
        puts $concatdresultfile "$filename:[exec tail --lines=+3 $file | sha1sum | cut -d " " -f1]"
    }
    puts $concatdresultfile "!sent:"
    set sentfile [open "$RESULTFOLDER/sent.txt"]
    fconfigure $sentfile -translation binary
    fcopy $sentfile $concatdresultfile
    close $sentfile
    puts $concatdresultfile "!recv:"
    set recvfile [open "$RESULTFOLDER/received.txt"]
    fconfigure $recvfile -translation binary
    fcopy $recvfile $concatdresultfile
    close $recvfile
    puts $concatdresultfile "#####"

    #no cleanup on debug
    if {$DEBUG != "true"} {
        file delete "$RESULTFOLDER/sent.txt"
        file delete "$RESULTFOLDER/received.txt"    
        file delete {*}[glob -nocomplain "$RESULTFOLDER/*.vcd"]
    }
    puts "finished experiment #$i"
    #increment line
    gets $fp data
    incr i
}
close $concatdresultfile
#

#vcd flush

exit