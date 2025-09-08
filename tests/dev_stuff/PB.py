# from spinapi import *

# # Enable the log file
# # pb_set_debug(0)

# print("Copyright (c) 2015 SpinCore Technologies, Inc.");
# print("Using SpinAPI Library version %s" % pb_get_version())
# print("Found %d boards in the system.\n" % pb_count_boards())
 
# print("This example program outputs at bit 0 and 1.\n\n");
# print("The program will loop 50 times for a total duration of 50 seconds. "\
#       "Bit 0 is HIGH for 500 ms and then LOW for 500 ms. "\
#       "Bit 1 outputs the same pattern as Bit 0 but offset by 250 ms.\n"); 
 
# pb_select_board(0)

# if pb_init() != 0:
# 	print("Error initializing board: %s" % pb_get_error())
# 	input("Please press a key to continue.")
# 	exit(-1)

# # Configure the core clock
# pb_core_clock(100)

# # Program the pulse program
# pb_start_programming(PULSE_PROGRAM)

# start = pb_inst_pbonly(0x1, Inst.LOOP, 50, 250.0 * ms)

# pb_inst_pbonly(0x3, Inst.CONTINUE, 0, 250.0 * ms)
# pb_inst_pbonly(0x2, Inst.CONTINUE, 0, 250.0 * ms)

# pb_inst_pbonly(0x0, Inst.END_LOOP, start, 250.0 * ms)

# pb_inst_pbonly(0x0, Inst.STOP, 0, 1.0 * ms)
# pb_stop_programming()

# # Trigger the board
# pb_reset() 
# pb_start()

# print("Continuing will stop program execution\n");
# input("Please press a key to continue.")

# pb_stop()
# pb_close()

###############################
# Docs for pb_inst_pbonly(...)
###############################
# flags		Set every bit to one for each flag you want to set high
# inst		Specify the instruction you want. Valid instructions are:
# 			Opcode #	Instruction	Meaning of inst_data field
#           0	CONTINUE	Not Used
#           1	STOP		Not Used
# 			2	LOOP		Number of desired loops
#			3	END_LOOP	Address of instruction originating loop
#			4	JSR			Address of first instruction in subroutine
# 			5	RTS			Not Used
# 			6	BRANCH		Address of instruction to branch to
# 			7	LONG_DELAY	Number of desired repetitions
# 			8	WAIT		Not Used
# 			See your board manual for a detailed description of each instruction.
# inst_data		Instruction specific data. Internally this is a 20 bit unsigned number, so the largest value that can be passed is 2^20-1 (the largest value possible for a 20 bit number). See above table to find out what this means for each instruction.
# length		Length of this instruction in nanoseconds. 


import spinapi
import ctypes
import os

# Define constants
FREQ = 100.0 # Master clock frequency in MHz
TAU_START = 1.0 # Start of tau loop in us
TAU_END = 5.0 # End of tau loop in us
TAU_STEP = 1.0 # Step of tau loop in us
OFF_TIME = 1.0 # Off time in us
BIT_1 = 0x01 # Hex value to represent turning on bit 1
BIT_0 = 0x00
c=0

def main():
    c=0
    # Initialize the board
    try:
        spinapi.pb_init()
    except Exception as e:
        print(f"Error initializing board: {e}")
        return

    # Set the clock frequency
    spinapi.pb_core_clock(FREQ)

    # Begin pulse program
    spinapi.pb_start_programming(spinapi.PULSE_PROGRAM)

    # Loop for 'tau' from 1us to 5us
    while c<1:
            for tau in range(int(TAU_START), int(TAU_END) + 1, int(TAU_STEP)):
                print(tau)
				# Instruction to turn on bit 1 for 'tau' microseconds 
                spinapi.pb_inst_pbonly(BIT_0, spinapi.Inst.CONTINUE, 0, tau * 1000) # Use ns for instruction time

				# Instruction to turn off all bits for 1 microsecond
                spinapi.pb_inst_pbonly(0, spinapi.Inst.CONTINUE, 0, int(OFF_TIME * 1000)) # Use ns for instruction time
            c=c+1

    # End of the pulse program
    spinapi.pb_inst_pbonly(0, spinapi.Inst.STOP, 0, 100) # Stop instruction with a short delay

    # Write the program to the board
    spinapi.pb_stop_programming()

    # Execute the program
    # spinapi.pb_start()
    # print("PulseBlaster program started. Press Enter to stop.")
    # input()

    # Stop and close the board
    spinapi.pb_stop()
    spinapi.pb_close()
    print("PulseBlaster program stopped and board closed.")

if __name__ == "__main__":
    main()