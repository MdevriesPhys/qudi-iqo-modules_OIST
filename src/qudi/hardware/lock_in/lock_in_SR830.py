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
from qudi.interface.fast_counter_interface import FastCounterInterface
from qudi.util.overload import OverloadedAttribute


class SR830(FiniteSamplingInputInterface,FastCounterInterface):
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
        self.log.info(f'deactivating lock in')
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
            resp=self._device.query('SPTS?')
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
        with self._thread_lock:
            self._device.write('REST')  # Reset data buffer
            self._device.write(f'STRT')
            # self.log.info(f'TSTR {self._frame_size}')
            # self._device.write(f'TSTR {self._frame_size}')  # Trigger scan
            # self._device.write(f'TSTR 0')
            

    def stop_buffered_acquisition(self):
        with self._thread_lock:
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
        if frame_size is None:
            frame_size = self._frame_size
        self.start_buffered_acquisition()
        # Wait until enough samples are acquired
        while self.samples_in_buffer < frame_size:
            time.sleep(frame_size / self._sample_rate * 0.1)
        self.stop_buffered_acquisition()
        return self.get_buffered_samples(frame_size)
    
#--------Fast Counter stuff----------
    def get_constraints(self):
        """ Retrieve the hardware constrains from the Fast counting device.

        @return dict: dict with keys being the constraint names as string and
                      items are the definition for the constaints.

         The keys of the returned dictionary are the str name for the constraints
        (which are set in this method).

                    NO OTHER KEYS SHOULD BE INVENTED!

        If you are not sure about the meaning, look in other hardware files to
        get an impression. If still additional constraints are needed, then they
        have to be added to all files containing this interface.

        The items of the keys are again dictionaries which have the generic
        dictionary form:
            {'min': <value>,
             'max': <value>,
             'step': <value>,
             'unit': '<value>'}

        Only the key 'hardware_binwidth_list' differs, since they
        contain the list of possible binwidths.

        If the constraints cannot be set in the fast counting hardware then
        write just zero to each key of the generic dicts.
        Note that there is a difference between float input (0.0) and
        integer input (0), because some logic modules might rely on that
        distinction.

        ALL THE PRESENT KEYS OF THE CONSTRAINTS DICT MUST BE ASSIGNED!
        """

        constraints = dict()

        # the unit of those entries are seconds per bin. In order to get the
        # current binwidth in seonds use the get_binwidth method.
        constraints['hardware_binwidth_list'] = [1 / 1000e6]

        # TODO: think maybe about a software_binwidth_list, which will
        #      postprocess the obtained counts. These bins must be integer
        #      multiples of the current hardware_binwidth

        return constraints
    
    def configure(self, bin_width_s, record_length_s, number_of_gates=0):

        """ Configuration of the fast counter.

        @param float bin_width_s: Length of a single time bin in the time trace
                                  histogram in seconds.
        @param float record_length_s: Total length of the timetrace/each single
                                      gate in seconds.
        @param int number_of_gates: optional, number of gates in the pulse
                                    sequence. Ignore for not gated counter.

        @return tuple(binwidth_s, gate_length_s, number_of_gates):
                    binwidth_s: float the actual set binwidth in seconds
                    gate_length_s: the actual set gate length in seconds
                    number_of_gates: the number of gated, which are accepted
        """
        self._number_of_gates = number_of_gates
        self._bin_width = bin_width_s * 1e9
        self._record_length = 1 + int(record_length_s / bin_width_s)
        self.statusvar = 1


        self.pulsed.stop()

        return bin_width_s, record_length_s, number_of_gates

    def start_measure(self):
        """ Start the fast counter. """
        self.module_state.lock()
        self.pulsed.clear()
        self.pulsed.start()
        self.statusvar = 2
        return 0

    def stop_measure(self):
        """ Stop the fast counter. """
        if self.module_state() == 'locked':
            self.pulsed.stop()
            self.module_state.unlock()
        self.statusvar = 1
        return 0

    def pause_measure(self):
        """ Pauses the current measurement.

        Fast counter must be initially in the run state to make it pause.
        """
        if self.module_state() == 'locked':
            self.pulsed.stop()
            self.statusvar = 3
        return 0

    def continue_measure(self):
        """ Continues the current measurement.

        If fast counter is in pause state, then fast counter will be continued.
        """
        if self.module_state() == 'locked':
            self.pulsed.start()
            self.statusvar = 2
        return 0

    def is_gated(self):
        """ Check the gated counting possibility.

        Boolean return value indicates if the fast counter is a gated counter
        (TRUE) or not (FALSE).
        """
        return False

    def get_data_trace(self):
        """ Polls the current timetrace data from the fast counter.

        @return numpy.array: 2 dimensional array of dtype = int64. This counter
                             is gated the the return array has the following
                             shape:
                                returnarray[gate_index, timebin_index]

        The binning, specified by calling configure() in forehand, must be taken
        care of in this hardware class. A possible overflow of the histogram
        bins must be caught here and taken care of.
        """
        info_dict = {'elapsed_sweeps': None,
                     'elapsed_time': None}  # TODO : implement that according to hardware capabilities
        return np.array(self.pulsed.getData(), dtype='int64'), info_dict

    def get_status(self):
        """ Receives the current status of the Fast Counter and outputs it as
            return value.

        0 = unconfigured
        1 = idle
        2 = running
        3 = paused
        -1 = error state
        """
        return self.statusvar

    def get_binwidth(self):
        """ Returns the width of a single timebin in the timetrace in seconds. """
        width_in_seconds = self._bin_width * 1e-9
        return width_in_seconds