"""cocotb: ble_tx_uart keeps working when its clock is stopped between beacons.

The controller (or whatever makes the 8 MHz) stops clk after a packet and starts
it again before the next one. While it is stopped uart_rx idles high. The flops
just hold. This checks that the block comes back cleanly: the PDU and channel
loaded before the stop are still there, and a new PDU loaded after the restart
goes out right, with clk stopped low and stopped high, for short and long stops.

Run (container), with the 9 tests of digital/test/test_ble_tx_uart.py first:
    NETLIST=<post-layout .nl.v> python3 test_clock_stop.py      gate level, SPS=8
    python3 test_clock_stop.py                                   RTL (digital/rtl)
"""

import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ClockCycles, Timer

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "digital" / "test"))
import test_ble_tx_uart as T  # noqa: E402



class StoppableClock:
    """clk with a 50% duty cycle that can be held low or high for a while."""

    def __init__(self, dut, period_ps):
        self.clk, self.half = dut.clk, period_ps // 2
        self.run, self.level = True, 0

    async def start(self):
        while True:
            if self.run:
                self.clk.value = 1
                await Timer(self.half, unit="ps")
                if not self.run and self.level == 1:   # stop with clk high
                    continue
                self.clk.value = 0
                await Timer(self.half, unit="ps")
            else:
                self.clk.value = self.level
                await Timer(self.half, unit="ps")


async def setup(dut):
    clock = StoppableClock(dut, T.clk_ps())
    cocotb.start_soon(clock.start())
    dut.rst_n.value = 0
    dut.uart_rx.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    await Timer(37_123, unit="ps")
    return clock


async def stop_for(dut, clock, us, level):
    """Stop clk at `level` for `us` microseconds, then run it again."""
    if level == 0:
        await ClockCycles(dut.clk, 1, rising=False)     # just after a falling edge
    else:
        await ClockCycles(dut.clk, 1, rising=True)      # just after a rising edge
    clock.level, clock.run = level, False
    await Timer(us * 1_000_000, unit="ps")
    assert int(dut.code_valid.value) == 0
    clock.run = True
    await Timer(3_123, unit="ps")


@cocotb.test()
async def packets_around_clock_stops(dut):
    """Load + send, stop the clock, resend the same PDU without reloading, stop,
    load a new PDU and channel, send. Stops low and high, 3 us to 2 ms."""
    clock = await setup(dut)
    rng = random.Random(11)
    pdu, ch = T.demo_pdu(), 38
    bits, codes = await T.send(dut, pdu, ch)
    T.check(pdu, ch, bits, codes)
    for i, (us, level) in enumerate(((200, 0), (2000, 1), (3, 0), (50, 1), (700, 0), (5, 1))):
        await stop_for(dut, clock, us, level)
        if i % 2 == 0:
            bits, codes = await T.start_and_capture(dut)   # buffer and channel kept
        else:
            pdu = T.rand_pdu(rng, rng.choice((0, 13, 31)))
            ch = rng.choice((37, 38, 39))
            bits, codes = await T.send(dut, pdu, ch)
        T.check(pdu, ch, bits, codes)


@cocotb.test()
async def stop_between_load_and_start(dut):
    """The PDU is loaded, the clock stops before the start byte, then the start
    after the restart sends it. Also a stop between the PDU and channel commands."""
    clock = await setup(dut)
    rng = random.Random(12)
    for level in (0, 1):
        pdu = T.rand_pdu(rng, 31)
        await T.write_pdu(dut, pdu)
        await stop_for(dut, clock, 300, level)
        await T.set_channel(dut, 39)
        await stop_for(dut, clock, 40, 1 - level)
        bits, codes = await T.start_and_capture(dut)
        T.check(pdu, 39, bits, codes)


def run():
    from cocotb_tools.runner import get_runner
    netlist = os.environ.get("NETLIST")
    if netlist:
        cells = Path(os.environ["PDK_ROOT"]) / "gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog"
        sources = [cells / "primitives.v", cells / "gf180mcu_fd_sc_mcu7t5v0.v", Path(netlist)]
        params, defines, tag = {}, {"FUNCTIONAL": 1, "UNIT_DELAY": "#1"}, "gl"
    else:
        rtl = Path(os.environ.get("RTL", REPO / "digital" / "rtl"))
        sources = [rtl / "ble_uart.v", rtl / "ble_tx.v", rtl / "ble_gauss_lut.v"]
        params, defines, tag = {"SPS": 8}, {}, "rtl"
    build = Path(os.environ.get("BUILD", f"/tmp/clockstop_{tag}"))
    r = get_runner("icarus")
    r.build(sources=sources, hdl_toplevel="ble_tx_uart", parameters=params, defines=defines,
            build_dir=build, always=True, timescale=("1ns", "1ps"))
    for mod in ("test_ble_tx_uart", "test_clock_stop"):
        r.test(hdl_toplevel="ble_tx_uart", test_module=mod, test_dir=HERE,
               build_dir=build, results_xml=build / f"results_{mod}.xml",
               extra_env={"TB_SPS": "8", "PYTHONPATH": f"{HERE}:{REPO / 'digital' / 'test'}"})


if __name__ == "__main__":
    run()
