# experiments/t1_experiment.py
"""
Three-pulse all-optical T1 using PulseBlaster + SR830.
First half (Ref HIGH): one laser pulse (INIT)
Second half (Ref LOW): second laser pulse, then dark τ, then read pulse
Reads SR830 R per τ and plots live.
"""
import time
import numpy as np
from spinapi import *
from hardware.sr830_control import sr830_connect, sr830_read_R
from hardware.pulseblaster_control import pb_init_simple

# Channels (edit to match wiring)
CH_LASER = (1 << 0)  # TTL to AOM / laser driver
CH_REF   = (1 << 1)  # TTL to SR830 Ref In (HIGH = first half)

# Internal helpers
def _program_three_pulse_sequence(tau_us: float, tref_ms: float, init_us: float, second_us: float, read_us: float):
    half_us = (tref_ms * 1000.0) / 2.0
    if init_us > half_us:
        raise ValueError("INIT longer than first half")
    if second_us + tau_us + read_us > half_us:
        raise ValueError("SECOND + τ + READ must fit in second half")

    high_base_us = half_us - init_us
    low_after_read_us = half_us - (second_us + tau_us + read_us)

    pb_start_programming(PULSE_PROGRAM)
    # First half (REF HIGH): baseline, then INIT
    pb_inst_pbonly(CH_REF, CONTINUE, 0, high_base_us)
    pb_inst_pbonly(CH_REF | CH_LASER, CONTINUE, 0, init_us)
    # Second half (REF LOW): SECOND, τ (dark), READ, remainder
    pb_inst_pbonly(CH_LASER, CONTINUE, 0, second_us)
    if tau_us > 0:
        pb_inst_pbonly(0, CONTINUE, 0, tau_us)
    pb_inst_pbonly(CH_LASER, CONTINUE, 0, read_us)
    pb_inst_pbonly(0, BRANCH, 0, max(1.0, low_after_read_us))
    pb_stop_programming()


def run(ax, emit, tref_ms=4.0, init_us=10.0, second_us=8.0, read_us=5.0, max_tau_us=1000.0, points=15):
    # Init hardware
    pb_init_simple()
    rm, li, tau_LI_s = sr830_connect(oflt_index=6)
    wait_s = max(0.02, 5.0 * tau_LI_s)

    taus_us = np.linspace(10.0, float(max_tau_us), int(points))
    taus_s = taus_us * 1e-6
    Rvals = []

    # Plot setup
    ax.set_title("All-optical T₁ (3-pulse)")
    ax.set_xlabel("τ (s)"); ax.set_ylabel("R (V)"); ax.grid(True)
    (line,) = ax.plot([], [], "o-")

    try:
        # Prime sequence
        _program_three_pulse_sequence(taus_us[0], tref_ms, init_us, second_us, read_us)
        pb_start()
        time.sleep(max(wait_s, 2 * (tref_ms / 1000.0)))

        for i, tau in enumerate(taus_us):
            if QThread.currentThread().isInterruptionRequested():
                emit(line="Interrupted by user.")
                break

            pb_stop()
            _program_three_pulse_sequence(float(tau), tref_ms, init_us, second_us, read_us)
            pb_start()

            time.sleep(wait_s)  # let lock-in settle
            R = sr830_read_R(li)
            Rvals.append(R)

            # Live plot
            line.set_data(taus_s[:i+1], Rvals)
            ax.relim(); ax.autoscale()
            emit(line=f"τ = {tau:.1f} µs → R = {R:.6e} V", status=f"Point {i+1}/{len(taus_us)}", progress=(i+1)/len(taus_us))

    finally:
        try: pb_stop(); pb_reset(); pb_close()
        except: pass
        try: li.close(); rm.close()
        except: pass

    return {"tau_s": taus_s.tolist(), "R_V": Rvals}
