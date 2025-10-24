import pyvisa, time

class SR830:
    def __init__(self, visa_address: str, timeout_ms: int = 5000):
        self.addr = visa_address
        self.timeout = timeout_ms
        self.rm = None
        self.inst = None

    def connect(self):
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(self.addr, timeout=self.timeout)
        self.inst.write('OUTX 1'); self.inst.write('FMOD 0'); self.inst.write('RSLP 1')
        self.inst.write('HARM 1'); self.inst.write('ISRC 0'); self.inst.write('ICPL 0')
        self.inst.write('RMOD 1'); self.inst.write('OFSL 3'); self.inst.write('SEND 1')
        self.inst.write('ERST'); self.inst.write('REST')

    def set_time_constant_index(self, idx:int): self.inst.write(f'OFLT {idx}')
    def set_sample_rate_index(self, idx:int): self.inst.write(f'SRAT {idx}'); self.inst.write('SEND 1')
    def read_x(self) -> float: return float(self.inst.query('OUTP? 1'))
    def close(self):
        try:
            if self.inst: self.inst.close()
            if self.rm: self.rm.close()
        except: pass
