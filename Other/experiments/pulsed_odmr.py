# experiments/pulsed_odmr.py
"""Pulsed ODMR scaffold: program PB for init/read + short MW pulse, read signal.
Plug in your PB + detector calls where noted.
"""
import numpy as np, time

def run(ax, emit, f_start_GHz=2.86, f_stop_GHz=2.90, points=61, mw_us=0.5):
    f = np.linspace(f_start_GHz*1e9, f_stop_GHz*1e9, int(points))
    C = []

    ax.set_title("Pulsed ODMR")
    ax.set_xlabel("MW frequency (Hz)")
    ax.set_ylabel("Contrast (arb)")
    ax.grid(True)
    (line,) = ax.plot([], [], "o-")

    for i, fi in enumerate(f):
        if QThread.currentThread().isInterruptionRequested():
            emit(line="Interrupted by user.")
            break
        # TODO: PB sequence: laser init → MW (mw_us) → laser read; read detector
        time.sleep(0.02)
        yi = 0.03*np.exp(-((fi-2.88e9)/2e6)**2)
        C.append(yi)

        line.set_data(f[:i+1], C)
        ax.relim(); ax.autoscale()
        emit(line=f"f = {fi/1e9:.6f} GHz → C = {yi:.4f}", status=f"Point {i+1}/{len(f)}", progress=(i+1)/len(f))

    return {"freq_Hz": f.tolist(), "contrast": C}
