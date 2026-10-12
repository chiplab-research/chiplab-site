#!/usr/bin/env python3
"""Count accepted words and CSR side effects with long gaps between reads."""
from migen import Signal, run_simulation, passive
from repro import build
from target import Target


def check(domain, phase=0):
    top, pads, bus = build(domain)
    dut = top.dut
    target_low = Signal()
    top.comb += [pads.sda_i.eq(~(pads.sda_oe | target_low)),
                 pads.scl_i.eq(~pads.scl_oe)]
    target = Target()
    counts = dict(csr_writes=0, csr_pops=0, tx_words=0,
                  phy_results=0, cdc_writes=0, rx_words=0)
    results = []

    @passive
    def device():
        cycle = 0
        while True:
            target.step(cycle, (yield pads.scl_i), (yield pads.sda_i))
            yield target_low.eq(target.sda_low)
            cycle += 1
            yield

    @passive
    def monitor_sys():
        while True:
            if (yield dut.master._rxtx.wr_stb):
                counts["csr_writes"] += 1
            if (yield dut.master._rxtx.rd_stb):
                counts["csr_pops"] += 1
            if (yield dut.master.source.valid) and (yield dut.master.source.ready):
                counts["tx_words"] += 1
            if (yield dut.phy.source.valid) and (yield dut.phy.source.ready):
                counts["phy_results"] += 1
            if (yield dut.master.sink.valid) and (yield dut.master.sink.ready):
                counts["rx_words"] += 1
            yield

    @passive
    def monitor_i2c():
        while True:
            if (yield dut.crossbar.rx_cdc.sink.valid) and (yield dut.crossbar.rx_cdc.sink.ready):
                counts["cdc_writes"] += 1
            yield

    def read(address):
        yield bus.adr.eq(address)
        yield bus.re.eq(1)
        yield
        yield bus.re.eq(0)
        yield
        value = (yield bus.dat_r)
        # These gaps rule out re-reading an entry before its pop takes effect.
        for _ in range(20):
            yield
        return value

    def host():
        for address, value in [(5, 0), (0, 1), (1, 256), (2, 80)]:
            yield from bus.write(address, value)
            for _ in range(10):
                yield
        assert (yield from read(4)) & 1
        yield from bus.write(3, 0)
        yield
        for _ in range(150):
            status = yield from read(4)
            if status & 2:
                results.append(((yield from read(3)), status))

    generators = {"sys": [host(), device(), monitor_sys()]}
    clocks = {"sys": 100}
    if domain != "sys":
        clocks["i2c"] = (50, phase)
        generators["i2c"] = [monitor_i2c()]
    run_simulation(top, generators, clocks=clocks)
    print("domain", domain, "i2c_phase_ns", phase,
          "counts", counts, "popped_results", results, flush=True)
    assert counts["csr_writes"] == counts["tx_words"] == counts["phy_results"] == 1
    expected = 1 if domain == "sys" else 2
    assert counts["csr_pops"] == counts["rx_words"] == len(results) == expected
    if domain != "sys":
        assert counts["cdc_writes"] == 2
    assert results == [(150, 3)] * expected
    assert [(kind, value) for _, kind, value in target.words] == [("address", 161), ("read", 150)]
    assert [kind for kind, _ in target.events] == ["S", "P"] and target.acks == [0, 1]


check("sys")
check("i2c")
check("i2c", phase=13)
