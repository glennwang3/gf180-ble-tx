"""cocotb: the debug UART of ble_tx_uart (pin dbg_tx).

While it is on (command 11xx_xxe0 with e = 1, then an optional byte k), each packet
sends the marker 0x80 when its start byte is taken, then fine_code at the packet's
code indices k, k+80, k+160, ... (index 0 = first valid code), one 8N1 byte per
80 clocks, at the same baud rate as uart_rx.

Checks, decoding dbg_tx as a UART receiver would:
  * the marker comes first, then exactly the codes at k, k+80, ..., equal to the
    parallel fine_code pins at those indices, back to back;
  * k = 0..79 over 80 repeats of one packet gives every code exactly once, equal
    to the golden model's (the full 8 MS/s waveform);
  * off after reset and after 11xx_xx00: dbg_tx stays high through a packet;
  * 11xx_xx10 without a k byte keeps k; k > 79 sends the marker only; start bytes
    (1xxx_xxx1) do not change the setting; the PDU and channel still work.

Run: python test_ble_dbg_tx.py                 RTL, SPS=8 (all 80 offsets)
     GL=1 python test_ble_dbg_tx.py            gate level, digital/synth/ble_tx_uart_sps8.syn.v
     NETLIST=<file> GL=1 python test_ble_dbg_tx.py   another netlist
     DBG_KS="0 1 40 79"                        only these offsets in the full test
"""

import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_ble_tx_uart as T  # noqa: E402

BYTE_CLKS = 10 * T.CLKS_PER_BIT


def dbg_on(k=None):
    return [0xC2] + ([k] if k is not None else [])


async def trace_packet(dut):
    """Per clock from the start byte until dbg_tx has been idle for 2 byte times
    after the last code: (fine_code unsigned, code_valid, dbg_tx)."""
    rows, seen, quiet = [], False, 0
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        v, tx = int(dut.code_valid.value), int(dut.dbg_tx.value)
        rows.append((int(dut.fine_code.value), v, tx))
        seen |= bool(v)
        quiet = quiet + 1 if (seen and not v and tx) else 0
        if quiet > 2 * BYTE_CLKS:
            return rows
        assert len(rows) < 800 * T.sps_of(), "packet never finished"


async def send_traced(dut, start=0x81):
    tr = cocotb.start_soon(trace_packet(dut))
    await T.uart_bytes(dut, [start])
    rows = await tr
    await T.pause()
    return rows


def decode(rows):
    """8N1 bytes on dbg_tx: [(row of the start bit's first clock, byte)]."""
    out, r, n = [], 1, len(rows)
    tx = [row[2] for row in rows]
    while r < n:
        if tx[r - 1] == 1 and tx[r] == 0:
            mid = r + T.CLKS_PER_BIT // 2
            assert mid + 9 * T.CLKS_PER_BIT < n, "byte cut off at the end of the trace"
            assert tx[mid] == 0, f"start bit too short at row {r}"
            val = sum(tx[mid + (i + 1) * T.CLKS_PER_BIT] << i for i in range(8))
            assert tx[mid + 9 * T.CLKS_PER_BIT] == 1, f"framing error in byte at row {r}"
            out.append((r, val))
            r += 10 * T.CLKS_PER_BIT
        else:
            r += 1
    return out


def check_packet(rows, k):
    """Marker, then the codes at k, k+80, ...; returns {index: byte}."""
    valid = [i for i, row in enumerate(rows) if row[1]]
    codes = [rows[i][0] for i in valid]
    assert valid == list(range(valid[0], valid[0] + len(valid))), "code_valid not contiguous"
    got = decode(rows)
    assert got, "nothing on dbg_tx"
    assert got[0][1] == 0x80, f"first byte {got[0][1]:#04x}, not the marker"
    want_idx = list(range(k, len(codes), BYTE_CLKS))
    samples = got[1:]
    assert len(samples) == len(want_idx), (k, len(samples), len(want_idx))
    for (row, val), idx in zip(samples, want_idx):
        assert val == codes[idx], f"k={k}: code {idx} sent as {val:#04x}, was {codes[idx]:#04x}"
        assert codes[idx] != 0x80
    starts = [row for row, _ in samples]
    assert all(b - a == BYTE_CLKS for a, b in zip(starts, starts[1:])), "samples not back to back"
    return dict(zip(want_idx, (v for _, v in samples))), codes


@cocotb.test()
async def reconstructs_full_waveform(dut):
    await T.setup(dut)
    rng = random.Random(31)
    pdu = T.rand_pdu(rng, 31)          # 37-byte payload: the longest packet
    ch = 39
    await T.write_pdu(dut, pdu)
    await T.set_channel(dut, ch)
    ks = [int(x) for x in os.environ.get("DBG_KS", " ".join(map(str, range(BYTE_CLKS)))).split()]
    got, ref = {}, None
    for k in ks:
        await T.command(dut, dbg_on(k))
        rows = await send_traced(dut)
        part, codes = check_packet(rows, k)
        ref = ref or codes
        assert codes == ref, "the packet changed between repeats"
        for i, v in part.items():
            assert i not in got
            got[i] = v
    want = list(T.fine_codes(T.frequency_trajectory(T.air_bits(pdu, ch), T.sps_of()), T.STEP_HZ))
    for i, v in got.items():
        assert (v - 256 if v >= 128 else v) == want[i], f"code {i} differs from the model"
    if len(ks) == BYTE_CLKS:
        assert sorted(got) == list(range(len(want))), "some codes never sent"
    dut._log.info("%d offsets, %d of %d codes checked against the model", len(ks), len(got), len(want))


@cocotb.test()
async def off_by_default_and_when_disabled(dut):
    await T.setup(dut)
    pdu = T.demo_pdu()
    await T.write_pdu(dut, pdu)
    await T.set_channel(dut, 37)
    rows = await send_traced(dut)
    assert all(r[2] == 1 for r in rows), "dbg_tx moved while off (after reset)"
    await T.command(dut, dbg_on(3))
    rows = await send_traced(dut)
    check_packet(rows, 3)
    await T.command(dut, [0xC0])                          # off
    rows = await send_traced(dut)
    assert all(r[2] == 1 for r in rows), "dbg_tx moved after switching off"


@cocotb.test()
async def command_details(dut):
    """k kept without a k byte; k > 79 sends the marker only; start bytes with bit 6
    set leave the setting; PDU writes and the packet are unaffected."""
    await T.setup(dut)
    rng = random.Random(32)
    pdu = T.rand_pdu(rng, 12)
    await T.write_pdu(dut, pdu)
    await T.set_channel(dut, 38)
    await T.command(dut, dbg_on(17))
    await T.command(dut, [0xC0])
    await T.command(dut, dbg_on())                        # on again, k stays 17
    for sb in (0x81, 0xFF, 0xC1):
        rows = await send_traced(dut, sb)
        check_packet(rows, 17)
        bits = [r[0] for r in rows if r[1]]
        want = list(T.fine_codes(T.frequency_trajectory(T.air_bits(pdu, 38), T.sps_of()), T.STEP_HZ))
        assert [(b - 256 if b >= 128 else b) for b in bits] == want, f"packet changed (start {sb:#04x})"
    await T.command(dut, dbg_on(100))
    rows = await send_traced(dut)
    got = decode(rows)
    assert [v for _, v in got] == [0x80], f"k=100 sent {[hex(v) for _, v in got]}"


def run(gl=False):
    from cocotb_tools.runner import get_runner
    digital = HERE.parent
    sps = 8
    if gl:
        cells = Path(os.environ["PDK_ROOT"]) / "gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog"
        nl = Path(os.environ.get("NETLIST", digital / "synth" / f"ble_tx_uart_sps{sps}.syn.v"))
        sources = [cells / "primitives.v", cells / "gf180mcu_fd_sc_mcu7t5v0.v", nl]
        params, defines, tag = {}, {"FUNCTIONAL": 1, "UNIT_DELAY": "#1"}, "dbgtx_gl"
    else:
        rtl = Path(os.environ.get("RTL", digital / "rtl"))
        sources = [rtl / "ble_uart.v", rtl / "ble_tx.v", rtl / "ble_gauss_lut.v"]
        params, defines, tag = {"SPS": sps}, {}, "dbgtx_rtl"
    build = Path(os.environ.get("BUILD", HERE / f"sim_build_{tag}"))
    r = get_runner("icarus")
    r.build(sources=sources, hdl_toplevel="ble_tx_uart", parameters=params, defines=defines,
            build_dir=build, always=True, timescale=("1ns", "1ps"))
    r.test(hdl_toplevel="ble_tx_uart", test_module="test_ble_dbg_tx", test_dir=HERE,
           build_dir=build, results_xml=build / "results.xml", extra_env={"TB_SPS": str(sps)})


if __name__ == "__main__":
    run(gl=bool(os.environ.get("GL")))
