from spinapi import *
class PulseBlaster:
    LASER = (1<<0)
    REF   = (1<<1)

    def __init__(self, clock_mhz: float = 100.0):
        self.clock = clock_mhz
        self.ready = False

    def init(self):
        pb_select_board(0); pb_init(); pb_core_clock(self.clock); self.ready = True

    def program_t1_cycle(self, half_us: float, tau_us: float, read_us: float):
        assert self.ready
        pb_start_programming(PULSE_PROGRAM)
        pb_inst_pbonly(0, CONTINUE, 0, half_us)                    # LOW half
        pb_inst_pbonly(self.REF, CONTINUE, 0, tau_us)              # HIGH dark
        pb_inst_pbonly(self.REF|self.LASER, CONTINUE, 0, read_us)  # read pulse
        remain = max(1.0, half_us - tau_us - read_us)
        pb_inst_pbonly(self.REF, BRANCH, 0, remain)                # loop
        pb_stop_programming()

    def start(self): pb_start()
    def stop(self): pb_stop(); pb_reset()
    def close(self): 
        try: pb_close()
        except: pass
