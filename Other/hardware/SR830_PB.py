"""SR830"""
import pyvisa
from spinapi import *
import time

# ===== User settings =====

CLOCK_MHZ = 100.0          # PB core clock (ESR/ESR-PRO default 100 MHz)
FREQ_kHZ   = 200.0          # Output frequency (kHz)
FREQ_HZ = FREQ_kHZ/1000
LIA_CHANNEL   = (1 << 0)       # TTL D0. Use (1<<1) for D1, (1<<2) for D2, etc.
LAS_CHANNEL = (1<<1)
MWI_CHANNEL = (1<<2)
MWQ_CHANNEL = (1<<3)
BOARD     = 0              # PB board index if you have multiple

# SR830 settings

VISA_ADDR = "GPIB0::1::INSTR"
TIME_CONST_S = 0.01       # lock-in time constant = 10 ms
SETTLE_FACTOR = 5         # wait ~5× time constant before reading

def init_pulseblaster():
    period_us = 1e6 / FREQ_HZ     # full period in microseconds
    half_us   = period_us / 2.0   # 50% duty
    pb_select_board(BOARD)
    pb_init()
    pb_core_clock(CLOCK_MHZ)

    # Program: LOW for half, HIGH for half, loop forever
    pb_start_programming(PULSE_PROGRAM)
    pb_inst_pbonly(0,        CONTINUE, 0, half_us)   # LOW half
    pb_inst_pbonly(LIA_CHANNEL,  BRANCH,   0, half_us)   # HIGH half, branch to start
    pb_stop_programming()

    print(f"Running {FREQ_kHZ:.1f} Hz on channel bit {LIA_CHANNEL:#x} "
          f"(period={period_us:.1f} us, duty=50%). Press Ctrl+C to stop.")

def init_sr830():
    rm = pyvisa.ResourceManager()
    li = rm.open_resource(VISA_ADDR, timeout=5000)
    li.clear()
    idn = li.query("*IDN?").strip()
    print(f"Connected to {idn}")

    # Basic setup
    li.write("OUTX 1")      # GPIB
    li.write("FMOD 0")      # external reference
    li.write("RSLP 1")      # rising edge
    li.write("HARM 1")      # fundamental
    li.write("ISRC 0")      # input A
    li.write("ICPL 0")      # AC coupling
    li.write("OFSL 3")      # 24 dB/oct
    li.write("OFLT 6")      # 10 ms time constant
    li.write("PHAS 0")      # phase adjust manually if needed
    return li

def read_R(li):
    """Read lock-in magnitude R (volts)."""
    val = float(li.query("OUTP? 3"))
    return val

def main():
    init_pulseblaster()
    li = init_sr830()
    pb_start()
    try:
        print("Measuring SR830 R output... Ctrl+C to stop.\n")
        while True:
            time.sleep(SETTLE_FACTOR * TIME_CONST_S)
            r = read_R(li)
            print(f"R = {r:.6f} V")
    except KeyboardInterrupt:

        print("Stopping...")

    finally:
        pb_stop()
        pb_reset()
        pb_close()
        li.close()

if __name__ == "__main__":

    main()