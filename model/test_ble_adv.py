import numpy as np

from ble_adv import (
    adv_nonconn_pdu,
    air_bits,
    bytes_to_bits,
    complete_local_name,
    crc24,
    decode,
    demod_bits,
    frequency_trajectory,
    whiten_bits,
)

ADDR = bytes.fromhex("C0FFEE180001")


def _pdu():
    return adv_nonconn_pdu(ADDR, bytes([2, 0x01, 0x06]) + complete_local_name("GF180-BLE"))


def _whiten_reference(bits, channel):
    # Independent form: 7-bit register as an int, as in common sniffer code.
    lfsr = int(f"1{channel:06b}", 2)  # position 0 is the MSB of this int
    out = []
    for b in bits:
        w = lfsr & 1
        out.append(b ^ w)
        lfsr = (lfsr >> 1) | (w << 6)
        if w:
            lfsr ^= 0x04  # feed back into position 4
    return out


def test_crc_matches_scapy_algorithm_vector():
    # Empty PDU with init 0x555555: CRC register ends at bit-reversed init.
    assert crc24(b"") == bytes([0xAA, 0xAA, 0xAA])


def test_crc_detects_single_bit_errors():
    pdu = _pdu()
    good = crc24(pdu)
    for i in range(len(pdu) * 8):
        bad = bytearray(pdu)
        bad[i // 8] ^= 1 << (i % 8)
        assert crc24(bytes(bad)) != good


def test_whitening_is_involution_and_matches_reference():
    bits = bytes_to_bits(_pdu())
    for ch in (37, 38, 39):
        w = whiten_bits(bits, ch)
        assert whiten_bits(w, ch) == bits
        assert w == _whiten_reference(bits, ch)


def test_packet_length_and_header():
    pdu = _pdu()
    bits = air_bits(pdu, 37)
    assert len(bits) == 8 * (1 + 4 + len(pdu) + 3)
    assert len(bits) <= 376
    assert bits[:8] == [0, 1, 0, 1, 0, 1, 0, 1]  # 0xAA, LSB first


def test_gfsk_round_trip_all_adv_channels():
    pdu = _pdu()
    for ch in (37, 38, 39):
        f = frequency_trajectory(air_bits(pdu, ch))
        assert np.max(np.abs(f)) <= 250e3 + 1
        got, ok = decode(demod_bits(f), ch)
        assert ok and got == pdu
