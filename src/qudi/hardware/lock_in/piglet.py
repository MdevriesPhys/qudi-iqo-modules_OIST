# -*- coding: utf-8 -*-
"""
This module controls Stanford Research Systems SR830 lock in amplifier via GPIB communication.

Copyright (c) 2025, the qudi developers. See the AUTHORS.md file at the top-level directory of this
distribution and on <https://github.com/Ulm-IQO/qudi-iqo-modules/>

This file is part of qudi.

Qudi is free software: you can redistribute it and/or modify it under the terms of
the GNU Lesser General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

Qudi is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with qudi.
If not, see <https://www.gnu.org/licenses/>.
"""

try:
    import pyvisa as visa # needed for GPIB communications
except ImportError:
    import visa
import time
import numpy as np

from qudi.util.mutex import Mutex
from qudi.core.configoption import ConfigOption
from qudi.interface.finite_sampling_input_interface import (
    FiniteSamplingInputInterface,
    FiniteSamplingInputConstraints,
)
from qudi.interface.fast_counter_interface import FastCounterInterface


class SR830(FiniteSamplingInputInterface, FastCounterInterface):
    """
    Hardware file for SR830 lock in amplifier.
    Example config for copy-paste:

    lockin_sr830:
        module.Class: 'lock_in.lock_in_SR830.SR830'
        options:
            interface: 'GPIB0::1::INSTR'
            comm_timeout: 5000
    """
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

        # FastCounter fields
        self._configured = False
        self.statusvar = 0  # 0 = unconfigured, 1 idle, 2 running, 3 paused
        self._bin_width_s = 1.0 / self._sample_rate
        self._record_length_s = self._frame_size / self._sample_rate
        self._number_of_gates = 0
        self._record_samples = self._frame_size
        self._measure_start_time = None

        # Scaling
        self._sensitivity_volts = None
        self._scale = 1e9  # fallback scale

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

        # Initialise scaling
        self._update_scale()

    def on_deactivate(self):
        self.log.info('Deactivating SR830')
        if self._device is not None:
            self._device.close()
        if self._rm is not None:
            self._rm.close()
        self._device = None
        self._rm = None

    # ----------- FiniteSamplingInputInterface properties -----------
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
            try:
                resp = self._device.query('SPTS?')
                return int(resp)
            except Exception:
                return 0

    # ----------- FiniteSamplingInputInterface configuration -----------
    def set_sample_rate(self, rate):
        with self._thread_lock:
            if not self._constraints.sample_rate_in_range(rate):
                raise ValueError('Sample rate out of range')
            rates = [
                0.0625, 0.125, 0.25, 0.5, 1, 2, 4, 8,
                16, 32, 64, 128, 256, 512
            ]
            idx = min(range(len(rates)), key=lambda i: abs(rates[i] - rate))
            self._device.write(f'SRAT {idx}')
            self._sample_rate = rates[idx]
            self._bin_width_s = 1.0 / self._sample_rate

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
        self._record_samples = self._frame_size
        self._record_length_s = self._record_samples / self._sample_rate

    # ----------- FiniteSamplingInputInterface acquisition -----------
    def start_buffered_acquisition(self):
        self.log.info("start buff") 
        with self._thread_lock:
            self._device.write('REST')  # Reset data buffer
            self._device.write('STRT')  # Start acquisition

    def stop_buffered_acquisition(self):
        self.log.info("stop buff")
        with self._thread_lock:
            self._device.write('PAUS')

    def get_buffered_samples(self, number_of_samples=None):
        with self._thread_lock:
            if number_of_samples is None:
                number_of_samples = self.samples_in_buffer
            if number_of_samples <= 0:
                return {ch: np.array([]) for ch in self._active_channels}

            data = {}
            for ch in ('X', 'Y'):
                code = {'X': 1, 'Y': 2}[ch]
                values = self._device.query(f'TRCA? {code},0,{number_of_samples}')
                values = np.fromstring(values, sep=",")
                if values.size > 0:
                    data[ch] = values[~np.isnan(values)]
                else:
                    data[ch] = np.array([])
            self.log.info(f"{data}")
            return {ch: data[ch] for ch in self._active_channels if ch in data}

    def acquire_frame(self, frame_size=None):
        if frame_size is None:
            frame_size = self._frame_size
        self.start_buffered_acquisition()
        while self.samples_in_buffer < frame_size:
            time.sleep(frame_size / self._sample_rate * 0.1)
        self.stop_buffered_acquisition()
        return self.get_buffered_samples(frame_size)

    # ----------- FastCounterInterface support -----------
    def _update_scale(self, desired_counts_fullscale=1e6):
        """Query SR830 sensitivity and update volts→counts scale."""
        try:
            resp = self._device.query('SENS?').strip()
            idx = int(resp)
        except Exception:
            self.log.warning("Failed to read SENS?; using fallback scale")
            self._scale = 1e9
            return

        sens_table_volts = {
            0: 2e-9,   1: 5e-9,   2: 1e-8,   3: 2e-8,   4: 5e-8,
            5: 1e-7,   6: 2e-7,   7: 5e-7,   8: 1e-6,   9: 2e-6,
            10: 5e-6, 11: 1e-5,  12: 2e-5,  13: 5e-5,  14: 1e-4,
            15: 2e-4, 16: 5e-4, 17: 1e-3, 18: 2e-3, 19: 5e-3,
            20: 1e-2, 21: 2e-2, 22: 5e-2, 23: 1e-1, 24: 2e-1,
            25: 5e-1, 26: 1.0
        }
        if idx not in sens_table_volts:
            self.log.warning(f"SENS index {idx} out of table; using fallback scale")
            self._scale = 1e9
            return

        self._sensitivity_volts = sens_table_volts[idx]
        self._scale = float(desired_counts_fullscale) / float(self._sensitivity_volts)
        self.log.info(f"SR830 sensitivity = {self._sensitivity_volts} V full scale, "
                      f"scale = {self._scale:.2e} counts/V")

    def get_constraints(self):
        constraints = dict()
        constraints['hardware_binwidth_list'] = [1.0 / self._sample_rate]
        return constraints

    def configure(self, bin_width_s, record_length_s, number_of_gates=0):
        self.log.info(f"BIN {bin_width_s}")
        self.log.info(f"RECORD {record_length_s}")
        self._number_of_gates = 0
        desired_rate = 1.0 / bin_width_s if bin_width_s > 0 else self._sample_rate
        self.set_sample_rate(desired_rate)
        record_samples = max(1, int(np.round(record_length_s *100* self._sample_rate)))
        min_frame, max_frame = self._constraints.frame_size_limits
        record_samples = min(max(record_samples, min_frame), max_frame)
        self.set_frame_size(record_samples)

        self._bin_width_s = 1.0 / self._sample_rate
        self._record_length_s = record_samples / self._sample_rate
        self._record_samples = record_samples
        self._configured = True
        self.statusvar = 1

        # Update sensitivity scaling each time we configure
        self._update_scale()

        return self._bin_width_s, self._record_length_s, self._number_of_gates

    def start_measure(self):
        if not self._configured:
            self.log.warning("SR830 start_measure called before configure()")
            return -1
        self.start_buffered_acquisition()
        self._measure_start_time = time.time()
        self.statusvar = 2
        return 0

    def stop_measure(self):
        self.stop_buffered_acquisition()
        self.statusvar = 1
        return 0

    def pause_measure(self):
        if self.statusvar == 2:
            self.stop_buffered_acquisition()
            self.statusvar = 3
        return 0

    def continue_measure(self):
        if self.statusvar == 3:
            self.start_buffered_acquisition()
            self.statusvar = 2
        return 0

    def is_gated(self):
        return False

    def get_data_trace(self):
        self.log.info("get data trace")
        if not self._configured:
            return np.array([], dtype='int64'), {'elapsed_sweeps': None, 'elapsed_time': None}

        timeout_s = max(1.0, self._record_length_s * 2.0)
        t0 = time.time()
        while self.samples_in_buffer < self._record_samples:
            if time.time() - t0 > timeout_s:
                break
            time.sleep(0.005)
        self.log.info(f"{self._record_samples}")
        buf = self.get_buffered_samples(self._record_samples)
        if 'X' in buf and buf['X'].size > 0:
            voltages = buf['X']
        elif 'Y' in buf and buf['Y'].size > 0:
            voltages = buf['Y']
        else:
            voltages = np.zeros(self._record_samples)

        if voltages.size < self._record_samples:
            voltages = np.pad(voltages, (0, self._record_samples - voltages.size), 'constant')
        elif voltages.size > self._record_samples:
            voltages = voltages[:self._record_samples]
        # voltage=self._device.query(f'OUTP?1')
        # self.log.info(f"{voltage}")
        pseudo_counts = np.round(voltages * self._scale).astype('int64')
        info_dict = {
            'elapsed_sweeps': None,
            'elapsed_time': None
        }
        if self._measure_start_time is not None:
            info_dict['elapsed_time'] = time.time() - self._measure_start_time
        self.log.info(f'voltage: {voltages}')
        return pseudo_counts, info_dict

    def get_status(self):
        return self.statusvar

    def get_binwidth(self):
        return 1.0 / self._sample_rate
