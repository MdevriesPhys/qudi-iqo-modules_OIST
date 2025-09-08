from spinapi import *

# Enable the log file
# pb_set_debug(0)

print("Copyright (c) 2015 SpinCore Technologies, Inc.");
print("Using SpinAPI Library version %s" % pb_get_version())
print("Found %d boards in the system.\n" % pb_count_boards())
 
print("This example program outputs at bit 0 and 1.\n\n");
print("The program will loop 50 times for a total duration of 50 seconds. "\
      "Bit 0 is HIGH for 500 ms and then LOW for 500 ms. "\
      "Bit 1 outputs the same pattern as Bit 0 but offset by 250 ms.\n"); 
 
pb_select_board(0)

if pb_init() != 0:
	print("Error initializing board: %s" % pb_get_error())
	input("Please press a key to continue.")
	exit(-1)

# Configure the core clock
pb_core_clock(100)

# Program the pulse program
pb_start_programming(PULSE_PROGRAM)

start = pb_inst_pbonly(0x1, Inst.LOOP, 50, 250.0 * us)

pb_inst_pbonly(0x3, Inst.CONTINUE, 0, 250.0 * us)
pb_inst_pbonly(0x2, Inst.CONTINUE, 0, 250.0 * us)

pb_inst_pbonly(0x0, Inst.END_LOOP, start, 250.0 * us)

pb_inst_pbonly(0x0, Inst.STOP, 0, 1.0 * us)
pb_stop_programming()

# Trigger the board
pb_reset() 
pb_start()

print("Continuing will stop program execution\n");
input("Please press a key to continue.")

pb_stop()
pb_close()