"""cocotb: full transmit chain (RTL modulator + behavioral DAC, PLL, amplifier).

For each packet the test locks the PLL on the channel, opens the loop, sends
the packet, and records the VCO frequency once per sample. It then checks the
RF signal the way a BLE tester would:

- demodulated bits and decoded PDU match the golden model, CRC passes
- carrier centre-frequency error within +-150 kHz (offset plus drift)
- drift within the packet below 50 kHz, drift rate below 400 Hz/us
- frequency deviation 225..275 kHz on settled symbols (modulation index 0.45..0.55)
- output power within power class 3 (-20..0 dBm)

Run: python test_tx_chain.py              SPS=2 and SPS=16
     SPS=2 python test_tx_chain.py        one rate
"""

import math
import os
import random
import sys
from pathlib import Path

import numpy as np

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "model"))

from ble_adv import (  # noqa: E402
    adv_nonconn_pdu,
    air_bits,
    complete_local_name,
    decode,
    demod_bits,
    fine_codes,
    frequency_trajectory,
)

STEP_HZ = 20e3
F_REF = 2e6

# BLE 1M PHY transmitter limits (Core spec Vol 6 Part A 4.4)
MAX_CENTRE_ERR_HZ = 150e3
MAX_DRIFT_HZ = 50e3
MAX_DRIFT_RATE_HZ_PER_US = 400.0
DEV_MIN_HZ, DEV_MAX_HZ = 225e3, 275e3


def chan_mhz(ch):
    if ch == 37:
        return 2402
    if ch == 38:
        return 2426
    if ch == 39:
        return 2480
    return 2404 + 2 * ch if ch <= 10 else 2406 + 2 * ch


def demo_pdu():
    addr = bytes.fromhex("C0FFEE180001")
    return adv_nonconn_pdu(addr, bytes([2, 0x01, 0x06]) + complete_local_name("GF180-BLE"))


class Chain:
    def __init__(self, dut):
        self.dut = dut
        self.sps = int(os.environ["TB_SPS"])

    async def setup(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, 1_000_000 // self.sps, unit="ps").start())
        for s in (d.wr_en, d.start, d.pll_en, d.pll_hold, d.pa_en):
            s.value = 0
        d.channel.value = 37
        d.rst_n.value = 0
        await ClockCycles(d.clk, 3)
        d.rst_n.value = 1
        await RisingEdge(d.clk)

    async def lock(self, channel, timeout_us=200):
        """Enable the PLL on a channel; return the lock time in us."""
        d = self.dut
        d.pll_en.value = 0
        d.pll_hold.value = 0
        d.channel.value = channel
        await Timer(10, unit="ns")
        d.pll_en.value = 1
        for t in range(timeout_us):
            await Timer(1, unit="us")
            if int(d.locked.value):
                return t + 1
        raise AssertionError(f"PLL did not lock on channel {channel} in {timeout_us} us")

    async def send(self, pdu, channel):
        """Lock, open the loop, send a packet. Returns (lock_us, bits, freq offsets)."""
        d = self.dut
        lock_us = await self.lock(channel)
        assert int(d.n_div.value) * F_REF == chan_mhz(channel) * 1e6

        await RisingEdge(d.clk)
        for i, b in enumerate(pdu):
            d.wr_en.value = 1
            d.wr_addr.value = i
            d.wr_data.value = b
            await RisingEdge(d.clk)
        d.wr_en.value = 0
        d.pll_hold.value = 1
        d.pa_en.value = 1
        d.start.value = 1
        await RisingEdge(d.clk)
        d.start.value = 0

        # Sample mid-clock. The DAC registers the code on the next rising edge,
        # so the frequency for the code seen at sample k shows at sample k+1.
        valid, freq, bits, pout = [], [], [], []
        while True:
            await FallingEdge(d.clk)
            v = int(d.code_valid.value)
            valid.append(v)
            freq.append(float(d.f_rf.value))
            pout.append(float(d.pout_w.value))
            if v and int(d.sym_strobe.value):
                bits.append(int(d.air_bit.value))
            if not int(d.busy.value) and any(valid):
                break
        await FallingEdge(d.clk)
        freq.append(float(d.f_rf.value))
        d.pa_en.value = 0
        d.pll_hold.value = 0

        idx = [i + 1 for i, v in enumerate(valid) if v]
        f = np.array([freq[i] for i in idx])
        offset = f - chan_mhz(channel) * 1e6
        return lock_us, bits, offset, max(pout)


def measure(offset, bits, sps):
    """RF measurements on one packet's frequency offset (Hz) per sample."""
    ideal = fine_codes(frequency_trajectory(bits, sps), STEP_HZ) * STEP_HZ
    carrier = offset - ideal                    # carrier error at each sample
    t_us = np.arange(len(carrier)) / sps
    win = 50 * sps                              # 50 us windows for drift rate
    rate = max(abs(carrier[i + win] - carrier[i]) / 50.0 for i in range(0, len(carrier) - win, sps))

    # Deviation on symbols whose neighbours (+-2) are equal, i.e. settled.
    centre = np.array(offset[sps // 2 :: sps]) - np.array(carrier[sps // 2 :: sps])
    settled = [abs(centre[n]) for n in range(2, len(bits) - 2) if len(set(bits[n - 2 : n + 3])) == 1]
    return {
        "centre_err_hz": float(np.max(np.abs(carrier))),
        "drift_hz": float(carrier.max() - carrier.min()),
        "drift_rate_hz_per_us": float(rate),
        "deviation_hz": float(np.mean(settled)) if settled else float("nan"),
        "duration_us": float(t_us[-1]),
    }


def violations(m):
    v = []
    if m["centre_err_hz"] > MAX_CENTRE_ERR_HZ:
        v.append("centre frequency error")
    if m["drift_hz"] > MAX_DRIFT_HZ:
        v.append("drift")
    if m["drift_rate_hz_per_us"] > MAX_DRIFT_RATE_HZ_PER_US:
        v.append("drift rate")
    if not DEV_MIN_HZ <= m["deviation_hz"] <= DEV_MAX_HZ:
        v.append("deviation")
    return v


def check_packet(dut, pdu, channel, bits, offset, sps):
    want = air_bits(pdu, channel)
    assert bits == want, "modulator air bits differ from the model"
    rx = demod_bits(offset, sps)
    assert rx == want, f"demodulated RF differs in {sum(a != b for a, b in zip(rx, want))} bits"
    got, crc_ok = decode(rx, channel)
    assert crc_ok and got == pdu, "decoded PDU or CRC wrong"


def log(dut, channel, lock_us, m, pout_w):
    dut._log.info(
        "ch %d (%d MHz): lock %d us, centre err %.1f kHz, drift %.1f kHz, "
        "drift rate %.0f Hz/us, deviation %.1f kHz (h=%.3f), Pout %.2f dBm",
        channel, chan_mhz(channel), lock_us, m["centre_err_hz"] / 1e3, m["drift_hz"] / 1e3,
        m["drift_rate_hz_per_us"], m["deviation_hz"] / 1e3, 2 * m["deviation_hz"] / 1e6,
        10 * math.log10(pout_w / 1e-3),
    )


@cocotb.test()
async def nominal_channels(dut):
    """Advertising channels and both ends of the band meet the BLE TX limits."""
    c = Chain(dut)
    await c.setup()
    pdu = demo_pdu()
    for ch in (37, 38, 39, 0, 36):
        lock_us, bits, offset, pout = await c.send(pdu, ch)
        check_packet(dut, pdu, ch, bits, offset, c.sps)
        m = measure(offset, bits, c.sps)
        log(dut, ch, lock_us, m, pout)
        assert not violations(m), violations(m)
        assert -20.0 <= 10 * math.log10(pout / 1e-3) <= 0.0, "output power outside class 3"


@cocotb.test()
async def random_payloads(dut):
    rng = random.Random(7)
    c = Chain(dut)
    await c.setup()
    for n in (0, 13, 31):
        addr = bytes(rng.randrange(256) for _ in range(6))
        pdu = adv_nonconn_pdu(addr, bytes(rng.randrange(256) for _ in range(n)))
        ch = rng.choice((37, 38, 39))
        lock_us, bits, offset, pout = await c.send(pdu, ch)
        check_packet(dut, pdu, ch, bits, offset, c.sps)
        assert not violations(measure(offset, bits, c.sps))


@cocotb.test()
async def crystal_error(dut):
    """A 40 ppm crystal moves the carrier by 40 ppm and stays inside +-150 kHz."""
    c = Chain(dut)
    await c.setup()
    dut.u_pll.ref_ppm.value = 40.0
    pdu = demo_pdu()
    lock_us, bits, offset, pout = await c.send(pdu, 39)
    check_packet(dut, pdu, 39, bits, offset, c.sps)
    m = measure(offset, bits, c.sps)
    log(dut, 39, lock_us, m, pout)
    assert abs(m["centre_err_hz"] - 40e-6 * 2480e6) < 3e3, m
    assert not violations(m), violations(m)
    dut.u_pll.ref_ppm.value = 0.0


@cocotb.test()
async def loop_filter_leakage(dut):
    """With the loop open, leakage sets the drift. Find where it breaks the spec.

    dV/dt = ILEAK / (C1 + C2), drift rate = KVCO * dV/dt. 400 Hz/us needs
    ILEAK below about 0.31 nA with the default filter.
    """
    c = Chain(dut)
    await c.setup()
    pdu = demo_pdu()
    c_tot = 143.8e-12 + 11.13e-12
    for ileak, ok in ((0.1e-9, True), (1e-9, False)):
        dut.u_pll.ileak.value = ileak
        lock_us, bits, offset, pout = await c.send(pdu, 38)
        m = measure(offset, bits, c.sps)
        log(dut, 38, lock_us, m, pout)
        predicted = 200e6 * ileak / c_tot / 1e6     # Hz/us
        assert abs(m["drift_rate_hz_per_us"] - predicted) < 0.15 * predicted + 20, (m, predicted)
        assert (not violations(m)) == ok, (ileak, violations(m))
    dut.u_pll.ileak.value = 0.0


@cocotb.test()
async def pa_supply_sets_power(dut):
    """Output power follows (2*VDD/pi)^2 / (2*50): 0.49 V -> -0.12 dBm, half that -> -6.14 dBm."""
    c = Chain(dut)
    await c.setup()
    pdu = demo_pdu()
    for vdd, want_dbm in ((0.49, -0.119), (0.245, -6.139)):
        dut.u_pa.vdd_pa.value = vdd
        _, _, _, pout = await c.send(pdu, 37)
        got = 10 * math.log10(pout / 1e-3)
        dut._log.info("VDD_PA %.2f V -> %.2f dBm", vdd, got)
        assert abs(got - want_dbm) < 0.05, got
    dut.u_pa.vdd_pa.value = 0.49


def run(sps):
    from cocotb_tools.runner import get_runner

    sources = [
        ROOT / "digital" / "rtl" / "ble_tx.v",
        ROOT / "digital" / "rtl" / "ble_gauss_lut.v",
        HERE / "models" / "dac_behav.v",
        HERE / "models" / "pll_behav.v",
        HERE / "models" / "pa_behav.v",
        HERE / "tb_tx_chain.v",
    ]
    build = HERE / f"sim_build_sps{sps}"
    runner = get_runner("icarus")
    runner.build(sources=sources, hdl_toplevel="tb_tx_chain", parameters={"SPS": sps},
                 build_dir=build, always=True, timescale=("1ns", "1fs"))
    runner.test(hdl_toplevel="tb_tx_chain", test_module="test_tx_chain", test_dir=HERE,
                build_dir=build, results_xml=HERE / f"results_sps{sps}.xml",
                extra_env={"TB_SPS": str(sps)})


def test_sps2():
    run(2)


def test_sps16():
    run(16)


if __name__ == "__main__":
    for s in [int(x) for x in os.environ.get("SPS", "2 16").split()]:
        run(s)
