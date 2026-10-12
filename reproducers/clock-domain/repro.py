#!/usr/bin/env python3
"""One valid CSR request must yield one result in the documented clock domain."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
from migen import Module, Signal, ClockDomain, run_simulation, passive
from migen.fhdl import verilog
from litex.soc.interconnect.csr_bus import CSRBank, Interface
from litei2c import LiteI2C
from target import Target

class Pads:
    def __init__(self):
        for name in ('scl_o', 'scl_oe', 'sda_o', 'sda_oe'):
            setattr(self, name, Signal(name_override=name))
        for name in ('scl_i', 'sda_i'):
            setattr(self, name, Signal(reset=1, name_override=name))

def build(domain):
    top = Module()
    pads = Pads()
    top.submodules.dut = dut = LiteI2C(10_000_000, pads=pads, clock_domain=domain)
    master = dut.master
    bus = Interface(data_width=32)
    top.submodules.regs = CSRBank([master._active, master._settings, master._addr,
                                 master._rxtx, master._status, dut.phy.speed_mode], bus=bus)
    return top, pads, bus

def migen_case(domain):
    top, pads, bus = build(domain)
    target_low = Signal()
    top.comb += [pads.sda_i.eq(~(pads.sda_oe | target_low)), pads.scl_i.eq(~pads.scl_oe)]
    target = Target()
    results = []
    @passive
    def device():
        cycle = 0
        while True:
            target.step(cycle, (yield pads.scl_i), (yield pads.sda_i))
            yield target_low.eq(target.sda_low)
            cycle += 1
            yield
    def read(address):
        yield bus.adr.eq(address)
        yield bus.re.eq(1)
        yield
        yield bus.re.eq(0)
        yield
        return (yield bus.dat_r)
    def host():
        yield from bus.write(5, 0)  # PHY Standard mode.
        for _ in range(10):
            yield
        for address, value in [(0, 1), (1, 0x100), (2, 0x50)]:
            yield from bus.write(address, value)
            yield
        assert (yield from read(4)) & 1, 'TX FIFO must have room'
        yield from bus.write(3, 0)  # Exactly one transfer request.
        yield
        # Poll RX ready, then pop each result.
        for _ in range(1300):
            status = yield from read(4)
            if status & 2:
                data = yield from read(3)
                results.append((data, status))
            yield
    clocks = {'sys': 100}
    if domain != 'sys':
        clocks['i2c'] = 50
    run_simulation(top, [host(), device()], clocks=clocks)
    return ([(kind, value) for _, kind, value in target.words],
            [kind for kind, _ in target.events], target.acks, results)

def iverilog_case(domain):
    top, pads, bus = build(domain)
    for name in ('adr', 're', 'we', 'dat_w', 'dat_r'):
        getattr(bus, name).name_override = 'csr_' + name
    ios = {getattr(pads, name) for name in ('scl_o','scl_oe','scl_i','sda_o','sda_oe','sda_i')}
    ios.update({getattr(bus, name) for name in ('adr','re','we','dat_w','dat_r')})
    top.clock_domains.cd_sys = ClockDomain('sys')
    top.clock_domains.cd_i2c = ClockDomain('i2c')
    ios.update({top.cd_sys.clk, top.cd_sys.rst, top.cd_i2c.clk, top.cd_i2c.rst})
    with TemporaryDirectory(prefix='litei2c-', dir=Path(__file__).parent) as folder:
        folder = Path(folder)
        rtl, lowered, exe = folder/'dut.v', folder/'dut_sim.v', folder/'sim.vvp'
        rtl.write_text(str(verilog.convert(top, ios=ios, name='dut')))
        subprocess.run(['yosys','-Q','-T','-q','-p',f'read_verilog "{rtl}"; hierarchy -top dut; proc; opt; write_verilog -noattr "{lowered}"'],
                       check=True, capture_output=True, text=True, timeout=30)
        subprocess.run(['iverilog','-g2012','-s','tb','-o',str(exe),str(lowered),str(Path(__file__).with_name('target_tb.sv'))],
                       check=True, capture_output=True, text=True, timeout=30)
        output = subprocess.run(['vvp',str(exe)],check=True,capture_output=True,text=True,timeout=30).stdout
    words, events, acks, results = [], [], [], []
    for line in output.splitlines():
        fields = line.split()
        if fields[0] == 'BYTE':
            words.append((['address','write','read'][int(fields[2])], int(fields[3], 16)))
        elif fields[0] in ('START','STOP'):
            events.append('S' if fields[0] == 'START' else 'P')
        elif fields[0] == 'ACK':
            acks.append(int(fields[2]))
        elif fields[0] == 'RESULT':
            results.append((int(fields[2], 16), int(fields[3], 16)))
    return words, events, acks, results

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--simulator', choices=['migen','iverilog'], default='migen')
    args = parser.parse_args()
    simulate = migen_case if args.simulator == 'migen' else iverilog_case
    failures = []
    for domain in ('sys', 'i2c'):
        words, events, acks, results = simulate(domain)
        # Hand-computed wire waveform: S 10100001 ACK 10010110 NACK P.
        assert words == [('address',0xa1),('read',0x96)], (domain,words)
        assert events == ['S','P'] and acks == [0,1], (domain,events,acks)
        # Status=3: TX ready and RX ready, with all error/unfinished bits zero.
        print(f'clock_domain={domain}: one rxtx write, {len(results)} result(s): {results}', flush=True)
        if results != [(0x96,3)]:
            failures.append((domain,results))
        if domain == 'sys':
            assert not failures, 'default-domain positive control failed'
    assert not failures, f'one transfer must produce exactly one result: {failures}'
