"""Pin-level target: UM10204 rev 7.0 sections 3.1.3--3.1.6, 3.1.10.
No DUT internals are inspected; SDA changes only after an SCL falling edge.
"""
class Target:
    def __init__(self, address=0x50, data=(0x96, 0x3c, 0xa5, 0x5a, 0x81, 0x7e), nack_at=None):
        self.address = address
        self.data = data
        self.nack_at = nack_at
        self.sda_low = 0
        self.prev_scl = self.prev_sda = 1
        self.started = False
        self.events = []
        self.edges = []
        self.words = []
        self.acks = []
        self.read_acks = []
        self.bit = 0
        self.word = 0
        self.read = False
        self.addr_phase = True
        self.index = 0
        self.byte_count = 0
        self.acked = False
        self.ignore = False

    def step(self, cycle, scl, sda):
        # Resolve pins BEFORE calling. This routine changes only target output.
        if (scl, sda) != (self.prev_scl, self.prev_sda):
            self.edges.append((cycle, scl, sda))
        if scl and self.prev_scl and sda != self.prev_sda:
            if not sda:
                self.events.append(('S', cycle))
                self.started = True
                self.bit = self.word = 0
                self.addr_phase = True
                self.read = self.ignore = False
                self.sda_low = 0
            else:
                self.events.append(('P', cycle))
                self.started = False
                self.sda_low = 0
        elif self.started and scl != self.prev_scl:
            if scl:
                if self.bit < 8:
                    self.word = (self.word << 1) | sda
                    self.bit += 1
                    if self.bit == 8:
                        self.words.append((cycle, 'address' if self.addr_phase else ('read' if self.read else 'write'), self.word))
                else:
                    self.acks.append(sda)
                    if self.read and not self.addr_phase:
                        self.read_acks.append(sda)
                        self.ignore = bool(sda)
                    self.acked = True
            else:
                if self.acked:
                    if self.addr_phase:
                        self.read = bool(self.word & 1)
                        self.ignore = (self.word >> 1) != self.address or self.nack_at == self.byte_count
                        self.addr_phase = False
                        self.index = 0
                    elif self.read:
                        self.index += 1
                    self.byte_count += 1
                    self.bit = self.word = 0
                    self.acked = False
                if self.ignore:
                    self.sda_low = 0
                elif self.bit == 8:
                    if self.addr_phase:
                        self.sda_low = (self.word >> 1) == self.address and self.nack_at != self.byte_count
                    else:
                        self.sda_low = (not self.read) and self.nack_at != self.byte_count
                elif self.read and not self.addr_phase:
                    value = self.data[self.index % len(self.data)]
                    self.sda_low = 1 - ((value >> (7-self.bit)) & 1)
                else:
                    self.sda_low = 0
        self.prev_scl, self.prev_sda = scl, sda
