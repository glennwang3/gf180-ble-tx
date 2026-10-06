"""cocotb: ble_tx control-path and corner cases, checked against model/ble_adv.py.

test_ble_tx.py checks normal packets bit for bit. This file covers how the
block behaves around them:

- every one of the 40 whitening channels
- the longest legal PDU (37-byte payload) and the empty one
- back-to-back packets with start raised the cycle busy falls
- start pulses while busy are ignored
- reset in the middle of a packet, then a clean packet
- PDU writes while busy do not disturb the packet already being sent
- the RF view: the codes, demodulated as a receiver would, decode with a good CRC

Run: python test_ble_tx_edge.py          RTL, SPS=2 and SPS=16
"""

import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "model"))
sys.path.insert(0, str(HERE))

from ble_adv import (  # noqa: E402
    adv_nonconn_pdu,
    air_bits,
    decode,
    demod_bits,
    fine_codes,
    frequency_trajectory,
)

STEP_HZ = 20e3


def sps_of():
    return int(os.environ["TB_SPS"])


def raw_pdu(rng, n):
    """Any PDU type with an n-byte payload (adv_nonconn_pdu caps AdvData at 31)."""
    return bytes([rng.randrange(16) | (rng.randrange(4) << 6), n]) + bytes(rng.randrange(256) for _ in range(n))


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 1_000_000 // sps_of(), unit="ps").start())
    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.start.value = 0
    dut.channel.value = 37
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def load(dut, pdu):
    for i, b in enumerate(pdu):
        dut.wr_en.value = 1
        dut.wr_addr.value = i
        dut.wr_data.value = b
        await RisingEdge(dut.clk)
    dut.wr_en.value = 0


async def collect(dut, hook=None):
    """Sample outputs until busy falls. hook(cycle) runs after each clock edge.

    Returns at the falling edge of the first idle cycle, so the caller can
    drive inputs for the next edge straight away.
    """
    codes, bits, cycles = [], [], 0
    while True:
        await RisingEdge(dut.clk)
        if hook:
            await hook(cycles)
        await ReadOnly()
        cycles += 1
        if int(dut.code_valid.value):
            codes.append(dut.fine_code.value.to_signed())
            if int(dut.sym_strobe.value):
                bits.append(int(dut.air_bit.value))
        if not int(dut.busy.value):
            await FallingEdge(dut.clk)
            return bits, codes
        assert cycles < 400 * sps_of(), "packet never finished"


async def start(dut, channel):
    dut.channel.value = channel
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0


def check(pdu, channel, bits, codes):
    sps = sps_of()
    want = air_bits(pdu, channel)
    assert bits == want, f"air bits differ (ch {channel}, {len(pdu)} bytes)"
    want_codes = list(fine_codes(frequency_trajectory(want, sps), STEP_HZ))
    assert codes == want_codes, f"fine codes differ (ch {channel}, {len(pdu)} bytes)"
    # Independent of the LUT: treat the codes as the RF frequency and decode it.
    got, crc_ok = decode(demod_bits([c * STEP_HZ for c in codes], sps), channel)
    assert crc_ok and got == pdu, "codes do not demodulate to the PDU"


@cocotb.test()
async def all_40_channels(dut):
    await setup(dut)
    rng = random.Random(40)
    for ch in range(40):
        pdu = raw_pdu(rng, rng.randrange(38))
        await load(dut, pdu)
        await start(dut, ch)
        check(pdu, ch, *(await collect(dut)))


@cocotb.test()
async def length_extremes(dut):
    await setup(dut)
    rng = random.Random(2)
    for n in (0, 1, 36, 37):
        pdu = raw_pdu(rng, n)
        await load(dut, pdu)
        await start(dut, 38)
        check(pdu, 38, *(await collect(dut)))


@cocotb.test()
async def back_to_back(dut):
    """Raise start on the first idle clock after busy falls: the next packet is exact."""
    await setup(dut)
    pdu = adv_nonconn_pdu(bytes.fromhex("A1B2C3D4E5F6"), bytes(range(12)))
    await load(dut, pdu)
    await start(dut, 37)
    for ch in (37, 38, 39):
        bits, codes = await collect(dut)
        check(pdu, ch, bits, codes)
        if ch != 39:
            await start(dut, ch + 1)


@cocotb.test()
async def start_ignored_while_busy(dut):
    await setup(dut)
    pdu = adv_nonconn_pdu(bytes.fromhex("C0FFEE180001"), b"\x02\x01\x06")
    await load(dut, pdu)
    await start(dut, 39)

    async def poke(cycle):
        # stop well before the end so no pulse lands on the first idle cycle
        dut.start.value = 1 if cycle % 37 == 5 and cycle < 120 * sps_of() else 0
        dut.channel.value = 37 if cycle % 2 else 38   # must be latched at start

    bits, codes = await collect(dut, poke)
    dut.start.value = 0
    check(pdu, 39, bits, codes)
    await ClockCycles(dut.clk, 4)
    assert not int(dut.busy.value), "a start pulse while busy queued a packet"


@cocotb.test()
async def reset_mid_packet(dut):
    await setup(dut)
    pdu = adv_nonconn_pdu(bytes.fromhex("112233445566"), bytes(range(20)))
    await load(dut, pdu)
    await start(dut, 37)
    await ClockCycles(dut.clk, 100 * sps_of())
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert not int(dut.busy.value) and not int(dut.code_valid.value)
    assert dut.fine_code.value.to_signed() == 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    # The buffer is not reset, so the same PDU can be sent again without reloading.
    await start(dut, 38)
    check(pdu, 38, *(await collect(dut)))


@cocotb.test()
async def write_while_busy(dut):
    """Payload bytes already on air can be overwritten without harm.

    The buffer is read live while sending. The length byte (pdu[1]) sets where
    the packet ends, so it must NOT be written while busy; this test only
    rewrites payload bytes the sequencer has passed.
    """
    await setup(dut)
    pdu = adv_nonconn_pdu(bytes(6), bytes(range(31)))
    await load(dut, pdu)
    await start(dut, 37)
    sps = sps_of()
    # PDU byte k goes on air at bit 40 + 8k; rewrite each byte 16 symbols after it left.
    sent_at = {k: (40 + 8 * (k + 1) + 16) * sps for k in range(2, len(pdu))}

    async def overwrite(cycle):
        hit = [k for k, c in sent_at.items() if c == cycle]
        dut.wr_en.value = 1 if hit else 0
        if hit:
            dut.wr_addr.value = hit[0]
            dut.wr_data.value = 0xA5

    bits, codes = await collect(dut, overwrite)
    dut.wr_en.value = 0
    check(pdu, 37, bits, codes)


def run(sps):
    from cocotb_tools.runner import get_runner

    digital = HERE.parent
    build = HERE / f"sim_build_edge_sps{sps}"
    runner = get_runner("icarus")
    runner.build(sources=[digital / "rtl" / "ble_tx.v", digital / "rtl" / "ble_gauss_lut.v"],
                 hdl_toplevel="ble_tx", parameters={"SPS": sps}, build_dir=build,
                 always=True, timescale=("1ns", "1ps"))
    runner.test(hdl_toplevel="ble_tx", test_module="test_ble_tx_edge", test_dir=HERE,
                build_dir=build, results_xml=HERE / f"results_edge_sps{sps}.xml",
                extra_env={"TB_SPS": str(sps)})


def test_edge_sps2():
    run(2)


def test_edge_sps16():
    run(16)


if __name__ == "__main__":
    for s in [int(x) for x in os.environ.get("SPS", "2 16").split()]:
        run(s)
