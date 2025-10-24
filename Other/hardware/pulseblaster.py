"""New approach to LIA with python"""
# pulseblaster_100hz.py

# Outputs a 100 Hz square wave on one PulseBlaster TTL channel.
import time
from spinapi import *

# ===== User settings =====

CLOCK_MHZ = 100.0          # PB core clock (ESR/ESR-PRO default 100 MHz)
FREQ_kHZ   = 200.0          # Output frequency (kHz)
FREQ_HZ = FREQ_kHZ/1000
LIA_CHANNEL   = (1 << 0)       # TTL D0. Use (1<<1) for D1, (1<<2) for D2, etc.
LAS_CHANNEL = (1<<1)
MWI_CHANNEL = (1<<2)
MWQ_CHANNEL = (1<<3)
BOARD     = 0              # PB board index if you have multiple

# =========================

def main():
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

    try:

        pb_start()
        while True:
            time.sleep(1.0)

    except KeyboardInterrupt:
        pass

    finally:
        pb_stop()
        pb_reset()
        pb_close()
        print("Stopped and closed PulseBlaster.")
if __name__ == "__main__":

    main()
