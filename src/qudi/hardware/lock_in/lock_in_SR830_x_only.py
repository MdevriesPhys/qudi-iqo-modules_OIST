# -*- coding: utf-8 -*-
"""
Qudi hardware file for the Stanford Research Systems SR830 Lock-In Amplifier.

Implements the FiniteSamplingInputInterface for ODMR use (X channel only).

Example config:

lockin_sr830:
    module.Class: 'lockin.lockin_sr830.SR830'
    options:
        visa_address: 'GPIB0::8::INSTR'
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
        self._sample_rate = 512.0   # Hz (SR830 max)
        self._frame_size = 1024

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_activate(self):
        self._rm = visa.ResourceManager()
        self._device = self._rm.open_resource(
            self._visa_address,
            timeout=self._comm_timeout
        )

        model = self._device.query('*IDN?')
        self.log.info(f'Connected to SR830: {model.strip()}')

        # Constraints: only X channel exposed
        channel_units = {'X': 'V'}
        self._constraints = FiniteSamplingInputConstraints(
            channel_units=channel_units,
            frame_size_limits=(1, 16383),       # SR830 internal buffer depth
            sample_rate_limits=(0.0625, 512.0)  # Hz, depends on time constant
        )

        # Reset buffer
        self._device.write('REST')
        self._device.write('ERES')

    def on_deactivate(self):
        if self._device is not None:
            self._device.close()
        if self._rm is not None:
            self._rm.close()
        self._device = None
        self._rm = None

    # ------------------------------------------------------------------
    # Interface properties
    # ------------------------------------------------------------------

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
        with self._thread_lock:
            return int(self._device.query('SPTS?'))

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_sample_rate(self, rate):
        with self._thread_lock:
            if not self._constraints.sample_rate_in_range(rate):
                raise ValueError('Sample rate out of range')
            # Map to SR830 SRAT codes
            rates = [
                0.0625, 0.125, 0.25, 0.5, 1, 2, 4, 8,
                16, 32, 64, 128, 256, 512
            ]
            idx = min(range(len(rates)), key=lambda i: abs(rates[i] - rate))
            self._device.write(f'SRAT {idx}')
            self._sample_rate = rates[idx]

    def set_active_channels(self, channels):
        # Only X allowed
        if set(channels) != {'X'}:
            raise ValueError('Only channel X is supported')
        self._active_channels = frozenset(['X'])

    def set_frame_size(self, size):
        if not self._constraints.frame_size_in_range(size):
            raise ValueError('Frame size out of range')
        self._frame_size = size

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    def start_buffered_acquisition(self):
        with self._thread_lock:
            self._device.write('REST')  # Reset data buffer

    def stop_buffered_acquisition(self):
        # SR830 has no explicit stop, just pause
        with self._thread_lock:
            self._device.write('PAUS')

    def get_buffered_samples(self, number_of_samples=None):
        with self._thread_lock:
            if number_of_samples is None:
                number_of_samples = self.samples_in_buffer
            if number_of_samples <= 0:
                return {'X': np.array([])}

            values = self._device.query_binary_values(
                f'TRAC? 1, {number_of_samples}',  # channel 1 = X
                datatype='f', is_big_endian=False
            )
            return {'X': np.array(values)}

    def acquire_frame(self, frame_size=None):
        if frame_size is None:
            frame_size = self._frame_size
        self.start_buffered_acquisition()
        # Wait until buffer has enough samples
        while self.samples_in_buffer < frame_size:
            time.sleep(frame_size / self._sample_rate * 0.1)
        return self.get_buffered_samples(frame_size)
