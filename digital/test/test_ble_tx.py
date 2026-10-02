"""cocotb: ble_tx must match model/ble_adv.py bit for bit.

Run: python test_ble_tx.py          RTL, SPS=2 and SPS=16 (Icarus)
     GL=1 SPS=2 python test_ble_tx.py   gate level, on digital/synth/ble_tx_sps2.syn.v
"""

import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "model"))

from ble_adv import (  # noqa: E402
    adv_nonconn_pdu,
    air_bits,
    complete_local_name,
    fine_codes,
    frequency_trajectory,
)

STEP_HZ = 20e3


def sps_of(dut):
    # the gate-level netlist has no parameters
    return int(os.environ["TB_SPS"])


async def send(dut, pdu, channel):
    sps = sps_of(dut)
    for i, b in enumerate(pdu):
        dut.wr_en.value = 1
        dut.wr_addr.value = i
        dut.wr_data.value = b
        await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    dut.channel.value = channel
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    codes, bits, cycles = [], [], 0
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        cycles += 1
        if int(dut.code_valid.value):
            codes.append(dut.fine_code.value.to_signed())
            if int(dut.sym_strobe.value):
                bits.append(int(dut.air_bit.value))
        elif codes:
            break
        assert cycles < 400 * sps, "packet never finished"
    await RisingEdge(dut.clk)
    assert not int(dut.busy.value)
    return bits, codes


def check(dut, pdu, channel, bits, codes):
    sps = sps_of(dut)
    want_bits = air_bits(pdu, channel)
    want_codes = list(fine_codes(frequency_trajectory(want_bits, sps), STEP_HZ))
    assert bits == want_bits, f"air bits differ (ch {channel}, len {len(pdu)})"
    bad = [i for i, (a, b) in enumerate(zip(codes, want_codes)) if a != b]
    assert len(codes) == len(want_codes), (len(codes), len(want_codes))
    assert not bad, f"{len(bad)} codes differ, first at sample {bad[0]}: {codes[bad[0]]} vs {want_codes[bad[0]]}"


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 500, unit="ns").start())
    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.start.value = 0
    dut.channel.value = 37
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def demo_packet_all_channels(dut):
    await setup(dut)
    addr = bytes.fromhex("C0FFEE180001")
    pdu = adv_nonconn_pdu(addr, bytes([2, 0x01, 0x06]) + complete_local_name("GF180-BLE"))
    for ch in (37, 38, 39):
        bits, codes = await send(dut, pdu, ch)
        check(dut, pdu, ch, bits, codes)


@cocotb.test()
async def random_packets(dut):
    await setup(dut)
    rng = random.Random(1)
    for n in list(range(0, 32, 3)) + [31] * 5:
        addr = bytes(rng.randrange(256) for _ in range(6))
        data = bytes(rng.randrange(256) for _ in range(n))
        pdu = adv_nonconn_pdu(addr, data, tx_add_random=rng.random() < 0.5)
        ch = rng.choice((37, 38, 39, rng.randrange(40)))
        bits, codes = await send(dut, pdu, ch)
        check(dut, pdu, ch, bits, codes)


def run(sps, gl=False):
    from cocotb_tools.runner import get_runner

    digital = HERE.parent
    if gl:
        cells = Path(os.environ["PDK_ROOT"]) / "gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog"
        sources = [cells / "primitives.v", cells / "gf180mcu_fd_sc_mcu7t5v0.v",
                   digital / "synth" / f"ble_tx_sps{sps}.syn.v"]
        params, defines, tag = {}, {"FUNCTIONAL": 1, "UNIT_DELAY": "#1"}, f"gl_sps{sps}"
    else:
        sources = [digital / "rtl" / "ble_tx.v", digital / "rtl" / "ble_gauss_lut.v"]
        params, defines, tag = {"SPS": sps}, {}, f"sps{sps}"
    runner = get_runner("icarus")
    runner.build(
        sources=sources,
        hdl_toplevel="ble_tx",
        parameters=params,
        defines=defines,
        build_dir=HERE / f"sim_build_{tag}",
        always=True,
        timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel="ble_tx",
        test_module="test_ble_tx",
        test_dir=HERE,
        build_dir=HERE / f"sim_build_{tag}",
        results_xml=f"results_{tag}.xml",
        extra_env={"TB_SPS": str(sps)},
    )


def test_sps2():
    run(2)


def test_sps16():
    run(16)


if __name__ == "__main__":
    for s in [int(x) for x in os.environ.get("SPS", "2 16").split()]:
        run(s, gl=bool(os.environ.get("GL")))
