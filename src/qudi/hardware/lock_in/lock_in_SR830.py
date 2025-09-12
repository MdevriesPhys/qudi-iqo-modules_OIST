try:
    import pyvisa as visa #needed for GPIB communications
except ImportError:
    import visa
import time
import numpy as np

from qudi.util.mutex import Mutex
from qudi.core.configoption import ConfigOption
from qudi.interface.finite_sampling_input_interface import FiniteSamplingInputInterface, FiniteSamplingInputConstraints
from qudi.util.enums import SamplingOutputMode


# -*- coding: utf-8 -*-
"""
Qudi hardware file for the Stanford Research Systems SR830 Lock-In Amplifier.

Implements the FiniteSamplingInputInterface.

Example config:

lockin_sr830:
    module.Class: 'lock_in.lock_in_SR830.SR830'
    options:
        visa_address: 'GPIB0::1::INSTR'
        comm_timeout: 5000  # ms
"""

try:
    import pyvisa as visa
except ImportError:
    import visa
import numpy as np
import time

from qudi.util.mutex import Mutex
from qudi.core.configoption import ConfigOption
from qudi.interface.finite_sampling_input_interface import (
    FiniteSamplingInputInterface,
    FiniteSamplingInputConstraints,
)


class SR830(FiniteSamplingInputInterface):
    _visa_address = ConfigOption('visa_address', missing='error')
    _comm_timeout = ConfigOption('comm_timeout', default=5000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._thread_lock = Mutex()
        self._rm = None
        self._device = None
        self._constraints = None

        self._active_channels = frozenset(['X'])
        self._sample_rate = 512.0   # Hz, SR830 max
        self._frame_size = 1024
        self._buffer = {ch: np.array([]) for ch in ['X', 'Y']}

    def on_activate(self):
        self._rm = visa.ResourceManager()
        self._device = self._rm.open_resource(
            self._visa_address,
            timeout=self._comm_timeout
        )

        model = self._device.query('*IDN?')
        self.log.info(f'Connected to SR830: {model.strip()}')

        # Setup constraints
        channel_units = {'X': 'V', 'Y': 'V'}
        self._constraints = FiniteSamplingInputConstraints(
            channel_units=channel_units,
            frame_size_limits=(1, 16383),       # SR830 internal buffer depth
            sample_rate_limits=(0.0625, 512.0)  # SR830 time constant dependent
        )
        # Clear buffer
        self._device.write('REST')
        self._device.write('ERES')

    def on_deactivate(self):
        self.log.info(f'deactivating lockin')
        self._device.close()
        self._rm.close()
        self._device = None
        self._rm = None

    # ----------- Interface properties -----------

    @property
    def constraints(self):
        return self._constraints

    @property
    def active_channels(self):
        return self._active_channels

    @property
    def sample_rate(self):
        return self._sample_rate

    @property
    def frame_size(self):
        return self._frame_size

    @property
    def samples_in_buffer(self):
        # Query number of points in buffer
        with self._thread_lock:
            self.log.info(f"I am about to call SPTS?")
            resp=self._device.query('SPTS?')
            self.log.info({resp})
            return int(self._device.query('SPTS?'))

    # ----------- Configuration methods -----------

    def set_sample_rate(self, rate):
        with self._thread_lock:
            if not self._constraints.sample_rate_in_range(rate):
                raise ValueError('Sample rate out of range')
            # Map to SR830 sample rate codes (SRAT command)
            rates = [
                0.0625, 0.125, 0.25, 0.5, 1, 2, 4, 8,
                16, 32, 64, 128, 256, 512
            ]
            idx = min(range(len(rates)), key=lambda i: abs(rates[i] - rate))
            self._device.write(f'SRAT {idx}')
            self._sample_rate = rates[idx]

    def set_active_channels(self, channels):
        with self._thread_lock:
            for ch in channels:
                if not self._constraints.channel_valid(ch):
                    raise ValueError(f'Unknown channel {ch}')
            self._active_channels = frozenset(channels)

    def set_frame_size(self, size):
        if not self._constraints.frame_size_in_range(size):
            raise ValueError('Frame size out of range')
        self._frame_size = size

    # ----------- Acquisition methods -----------

    def start_buffered_acquisition(self):
        self.log.info(f'started buffered aq')
        with self._thread_lock:
            self.log.info(f'REST')
            self._device.write('REST')  # Reset data buffer
            self.log.info(f'STRT')
            self._device.write(f'STRT')
            # self.log.info(f'TSTR {self._frame_size}')
            # self._device.write(f'TSTR {self._frame_size}')  # Trigger scan
            # self._device.write(f'TSTR 0')
            

    def stop_buffered_acquisition(self):
        with self._thread_lock:
            self.log.info(f'PAUS')
            self._device.write('PAUS')

    def get_buffered_samples(self, number_of_samples=None):
        with self._thread_lock:
            if number_of_samples is None:
                number_of_samples = self.samples_in_buffer
            if number_of_samples <= 0:
                return {ch: np.array([]) for ch in self._active_channels}

            data = {}
            for ch in ('X', 'Y'):#change input channels above as well
                code = {'X': 1, 'Y': 2}[ch]
                values = self._device.query(
                    f'TRCA? {code}, 0,{number_of_samples}')
                values=np.fromstring(values,sep=",")
                data = data|{ch: values[:-1]}

            return data

    def acquire_frame(self, frame_size=None):
        self.log.info(f'acquire frame called')
        if frame_size is None:
            frame_size = self._frame_size
        self.start_buffered_acquisition()
        # Wait until enough samples are acquired
        while self.samples_in_buffer < frame_size:
            self.log.info(f'loop')
            time.sleep(frame_size / self._sample_rate * 0.1)
        self.log.info(f'got to end of frame call')
        self.stop_buffered_acquisition()
        return self.get_buffered_samples(frame_size)