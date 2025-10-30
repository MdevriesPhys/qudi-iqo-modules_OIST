# main_gui.py (PyQt6)
import sys, traceback
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread

from experiments.mpl_canvas import MplCanvas

# Experiment runners (signature: run(ax, emit, **params))
try:
    from experiments.t1_experiment import run as run_t1
    from experiments.odmr_experiment import run as run_odmr
    from experiments.pulsed_odmr import run as run_podmr
    from experiments.ramsey_experiment import run as run_ramsey
    from experiments.t2_experiment import run as run_t2

except ImportError:
    # Dummy fallback functions for now so GUI can run without errors
    def run_t1(): return "T1 placeholder (no experiment connected)"
    def run_odmr(): return "ODMR placeholder (no experiment connected)"
    def run_podmr(): return "Pulsed ODMR placeholder (no experiment connected)"
    def run_ramsey(): return "no"
    def run_t2(): return "no"


class EmitProxy(QObject):
    message  = pyqtSignal(str)
    status   = pyqtSignal(str)
    progress = pyqtSignal(float)
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)


class Worker(QThread):
    def __init__(self, fn, ax, params):
        super().__init__()
        self.fn = fn
        self.ax = ax
        self.params = params
        self.emitter = EmitProxy()

    def run(self):
        try:
            def emit(**kwargs):
                if "line" in kwargs:
                    self.emitter.message.emit(kwargs["line"])  # log line
                if "status" in kwargs:
                    self.emitter.status.emit(kwargs["status"])  # status text
                if "progress" in kwargs:
                    self.emitter.progress.emit(float(kwargs["progress"]))  # 0..1
            # Fresh axes each run
            self.ax.clear()
            result = self.fn(self.ax, emit, **self.params)
            self.emitter.finished.emit(result)
        except Exception as e:
            tb = traceback.format_exc()
            self.emitter.error.emit(f"{e}\n{tb}")


class ExperimentTab(QWidget):
    """Reusable tab: parameters panel + run/stop + plot + log."""
    def __init__(self, title: str, runner, form_widget: QWidget):
        super().__init__()
        self.runner = runner
        self.form_widget = form_widget  # provides get_params()

        v = QVBoxLayout(self)
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Parameters box
        params_box = QGroupBox("Parameters")
        pv = QVBoxLayout(); pv.addWidget(self.form_widget); params_box.setLayout(pv)

        # Plot canvas
        self.canvas = MplCanvas(self, width=6, height=4, dpi=100)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("Run")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        btn_row.addWidget(self.btn_run); btn_row.addWidget(self.btn_stop)

        # Status + log
        self.status_lbl = QLabel("Idle")
        self.log = QTextEdit(); self.log.setReadOnly(True)

        v.addWidget(title_lbl)
        v.addWidget(params_box)
        v.addLayout(btn_row)
        v.addWidget(self.canvas)
        v.addWidget(self.status_lbl)
        v.addWidget(self.log)

        self.worker: Worker | None = None
        self.btn_run.clicked.connect(self.start_experiment)
        self.btn_stop.clicked.connect(self.stop_experiment)

    def start_experiment(self):
        if self.worker is not None and self.worker.isRunning():
            return
        params = self.form_widget.get_params()
        self.log.append(f"Starting with params: {params}")
        self.status_lbl.setText("Running…")
        self.btn_run.setEnabled(False); self.btn_stop.setEnabled(True)

        self.worker = Worker(self.runner, self.canvas.ax, params)
        self.worker.emitter.message.connect(self.on_message)
        self.worker.emitter.status.connect(self.on_status)
        self.worker.emitter.progress.connect(self.on_progress)
        self.worker.emitter.finished.connect(self.on_finished)
        self.worker.emitter.error.connect(self.on_error)
        self.worker.start()

    def stop_experiment(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.log.append("Stop requested (will finish current step)…")

    # Slots
    def on_message(self, text: str):
        if text:
            self.log.append(text)
            self.canvas.draw()

    def on_status(self, text: str):
        self.status_lbl.setText(text)

    def on_progress(self, frac: float):
        self.status_lbl.setText(f"Running… {int(frac*100)}%")

    def on_finished(self, result):
        self.btn_run.setEnabled(True); self.btn_stop.setEnabled(False)
        self.status_lbl.setText("Done")
        self.log.append("Finished.")
        self.canvas.draw()

    def on_error(self, text: str):
        self.btn_run.setEnabled(True); self.btn_stop.setEnabled(False)
        self.status_lbl.setText("Error")
        self.log.append(f"<pre>{text}</pre>")
        self.canvas.draw()


# -------- Parameter Forms (per tab) --------
class T1Form(QWidget):
    def __init__(self):
        super().__init__()
        f = QFormLayout(self)
        self.tref_ms = QDoubleSpinBox(); self.tref_ms.setRange(0.2, 100.0); self.tref_ms.setValue(20.0); self.tref_ms.setSuffix(" ms")
        self.init_us = QDoubleSpinBox(); self.init_us.setRange(0.1, 5000.0); self.init_us.setValue(20.0); self.init_us.setSuffix(" µs")
        self.second_us = QDoubleSpinBox(); self.second_us.setRange(0.1, 5000.0); self.second_us.setValue(20.0); self.second_us.setSuffix(" µs")
        self.read_us = QDoubleSpinBox(); self.read_us.setRange(0.1, 5000.0); self.read_us.setValue(20.0); self.read_us.setSuffix(" µs")
        self.max_tau_us = QDoubleSpinBox(); self.max_tau_us.setRange(10.0, 1e6); self.max_tau_us.setValue(4000.0); self.max_tau_us.setSuffix(" µs")
        self.points = QSpinBox(); self.points.setRange(3, 2000); self.points.setValue(15)
        self.loops= QSpinBox(); self.loops.setRange(1,100); self.loops.setValue(1)
        for label, w in [("Tref", self.tref_ms),("Init", self.init_us),("Second", self.second_us),("Read", self.read_us),("Max τ", self.max_tau_us),("Points", self.points),("Loops",self.loops)]:
            f.addRow(QLabel(label+":"), w)
    def get_params(self):
        return dict(tref_ms=self.tref_ms.value(), init_us=self.init_us.value(), second_us=self.second_us.value(), read_us=self.read_us.value(), max_tau_us=self.max_tau_us.value(), points=int(self.points.value()), loops=int(self.loops.value()))


class ODMRForm(QWidget):
    def __init__(self):
        super().__init__()
        f = QFormLayout(self)
        self.f_start = QDoubleSpinBox(); self.f_start.setRange(1.0, 20.0); self.f_start.setValue(2.86); self.f_start.setSuffix(" GHz")
        self.f_stop  = QDoubleSpinBox(); self.f_stop .setRange(1.0, 20.0); self.f_stop .setValue(2.90); self.f_stop .setSuffix(" GHz")
        self.points  = QSpinBox();       self.points .setRange(3, 5001);   self.points .setValue(101)
        for label, w in [("Start f", self.f_start),("Stop f", self.f_stop),("Points", self.points)]:
            f.addRow(QLabel(label+":"), w)
    def get_params(self):
        return dict(f_start_GHz=self.f_start.value(), f_stop_GHz=self.f_stop.value(), points=int(self.points.value()))

class PulsedODMRForm(QWidget):
    def __init__(self):
        super().__init__()
        f = QFormLayout(self)
        self.f_start = QDoubleSpinBox(); self.f_start.setRange(1.0, 20.0); self.f_start.setValue(2.86); self.f_start.setSuffix(" GHz")
        self.f_stop  = QDoubleSpinBox(); self.f_stop .setRange(1.0, 20.0); self.f_stop .setValue(2.90); self.f_stop .setSuffix(" GHz")
        self.points  = QSpinBox();       self.points .setRange(3, 2001);   self.points .setValue(61)
        self.mw_us   = QDoubleSpinBox(); self.mw_us  .setRange(0.01, 5000.0); self.mw_us.setValue(0.5); self.mw_us.setSuffix(" µs")
        for label, w in [("Start f", self.f_start),("Stop f", self.f_stop),("Points", self.points),("MW pulse", self.mw_us)]:
            f.addRow(QLabel(label+":"), w)
    def get_params(self):
        return dict(f_start_GHz=self.f_start.value(), f_stop_GHz=self.f_stop.value(), points=int(self.points.value()), mw_us=self.mw_us.value())

class RamseyForm(QWidget):
    def __init__(self):
        super().__init__()
        f = QFormLayout(self)
        self.tref_ms = QDoubleSpinBox(); self.tref_ms.setRange(0.2, 100.0); self.tref_ms.setValue(2.0); self.tref_ms.setSuffix(" ms")
        self.pi2_us  = QDoubleSpinBox(); self.pi2_us .setRange(0.01, 5000.0); self.pi2_us.setValue(0.2); self.pi2_us.setSuffix(" µs")
        self.max_tau_us = QDoubleSpinBox(); self.max_tau_us.setRange(0.1, 1e6); self.max_tau_us.setValue(50.0); self.max_tau_us.setSuffix(" µs")
        self.points = QSpinBox(); self.points.setRange(3, 5000); self.points.setValue(60)
        for label, w in [("Tref", self.tref_ms),("π/2", self.pi2_us),("Max τ", self.max_tau_us),("Points", self.points)]:
            f.addRow(QLabel(label+":"), w)
    def get_params(self):
        return dict(tref_ms=self.tref_ms.value(), pi2_us=self.pi2_us.value(), max_tau_us=self.max_tau_us.value(), points=int(self.points.value()))

class T2Form(QWidget):
    def __init__(self):
        super().__init__()
        f = QFormLayout(self)
        self.tref_ms = QDoubleSpinBox(); self.tref_ms.setRange(0.2, 100.0); self.tref_ms.setValue(2.0); self.tref_ms.setSuffix(" ms")
        self.pi_us   = QDoubleSpinBox(); self.pi_us  .setRange(0.01, 5000.0); self.pi_us.setValue(0.4); self.pi_us.setSuffix(" µs")
        self.max_tau_us = QDoubleSpinBox(); self.max_tau_us.setRange(0.1, 1e6); self.max_tau_us.setValue(200.0); self.max_tau_us.setSuffix(" µs")
        self.points = QSpinBox(); self.points.setRange(3, 5000); self.points.setValue(80)
        for label, w in [("Tref", self.tref_ms),("π", self.pi_us),("Max τ", self.max_tau_us),("Points", self.points)]:
            f.addRow(QLabel(label+":"), w)
    def get_params(self):
        return dict(tref_ms=self.tref_ms.value(), pi_us=self.pi_us.value(), max_tau_us=self.max_tau_us.value(), points=int(self.points.value()))


class NVGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NV Center Experiment Controller")
        self.setGeometry(100, 100, 1100, 800)

        tabs = QTabWidget()
        tabs.addTab(ExperimentTab("T1 (3-pulse)", run_t1, T1Form()), "T1")
        tabs.addTab(ExperimentTab("ODMR", run_odmr, ODMRForm()), "ODMR")
        tabs.addTab(ExperimentTab("Pulsed ODMR", run_podmr, PulsedODMRForm()), "Pulsed ODMR")
        tabs.addTab(ExperimentTab("Ramsey", run_ramsey, RamseyForm()), "Ramsey")
        tabs.addTab(ExperimentTab("T2 (Hahn)", run_t2, T2Form()), "T2")

        self.setCentralWidget(tabs)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = NVGui()
    w.show()
    sys.exit(app.exec())
