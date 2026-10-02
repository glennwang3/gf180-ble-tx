"""Golden model for a transmit-only BLE 1M PHY advertiser.

Builds a legacy ADV_NONCONN_IND packet, applies CRC24 and whitening, and turns
the air bits into a Gaussian-filtered frequency trajectory. The digital
modulator (digital/) must match this bit-exactly, and the DCO fine-code
mapping is derived from `frequency_trajectory`.

Bit order: BLE sends every byte LSB first. Functions that return "bits" return
them in air order.
"""

import numpy as np

ADV_ACCESS_ADDRESS = 0x8E89BED6
ADV_CRC_INIT = 0x555555
ADV_CHANNEL_FREQ_MHZ = {37: 2402, 38: 2426, 39: 2480}

PDU_ADV_NONCONN_IND = 0x2
SYMBOL_RATE = 1e6
DEVIATION_HZ = 250e3  # modulation index 0.5
BT = 0.5


def bytes_to_bits(data):
    """Air-order bits (LSB of each byte first)."""
    return [(b >> i) & 1 for b in data for i in range(8)]


def bits_to_bytes(bits):
    assert len(bits) % 8 == 0
    return bytes(sum(bits[i + j] << j for j in range(8)) for i in range(0, len(bits), 8))


def _reverse24(x):
    out = 0
    for i in range(24):
        out |= ((x >> i) & 1) << (23 - i)
    return out


def crc24(pdu, init=ADV_CRC_INIT):
    """BLE CRC24 over the PDU. Returns 3 bytes in transmit order.

    Polynomial x^24+x^10+x^9+x^6+x^4+x^3+x+1, implemented as the reflected
    LFSR used by Ubertooth and scapy.
    """
    state = _reverse24(init)
    for byte in pdu:
        for _ in range(8):
            next_bit = (state ^ byte) & 1
            byte >>= 1
            state >>= 1
            if next_bit:
                state |= 1 << 23
                state ^= 0x5A6000
    return bytes([state & 0xFF, (state >> 8) & 0xFF, (state >> 16) & 0xFF])


def whiten_bits(bits, channel):
    """Data whitening, Core spec Vol 6 Part B 3.2: 7-bit LFSR x^7 + x^4 + 1.

    Position 0 starts at 1, positions 1..6 hold the channel index MSB first.
    Applying it twice restores the input.
    """
    reg = [1] + [(channel >> (5 - i)) & 1 for i in range(6)]
    out = []
    for b in bits:
        w = reg[6]
        out.append(b ^ w)
        reg = [w, reg[0], reg[1], reg[2], reg[3] ^ w, reg[4], reg[5]]
    return out


def adv_nonconn_pdu(adv_addr, adv_data, tx_add_random=True):
    """ADV_NONCONN_IND PDU: 2-byte header + AdvA (6 bytes, LSB first) + AdvData."""
    assert len(adv_addr) == 6 and len(adv_data) <= 31
    header0 = PDU_ADV_NONCONN_IND | (0x40 if tx_add_random else 0)
    payload = bytes(reversed(adv_addr)) + bytes(adv_data)
    return bytes([header0, len(payload)]) + payload


def complete_local_name(name):
    raw = name.encode()
    return bytes([len(raw) + 1, 0x09]) + raw


def air_bits(pdu, channel):
    """Preamble + access address + whitened (PDU + CRC), in air order."""
    aa = ADV_ACCESS_ADDRESS.to_bytes(4, "little")
    preamble = 0x55 if aa[0] & 1 else 0xAA
    head = bytes_to_bits(bytes([preamble]) + aa)
    body = whiten_bits(bytes_to_bits(pdu + crc24(pdu)), channel)
    return head + body


def gaussian_taps(sps, bt=BT, span=3):
    t = np.arange(-span * sps / 2, span * sps / 2 + 1) / sps
    sigma = np.sqrt(np.log(2)) / (2 * np.pi * bt)
    h = np.exp(-(t**2) / (2 * sigma**2))
    return h / h.sum()


def frequency_trajectory(bits, sps=16, deviation=DEVIATION_HZ):
    """Instantaneous frequency offset (Hz) at sps samples per symbol."""
    nrz = np.repeat(2 * np.asarray(bits) - 1, sps).astype(float)
    return deviation * np.convolve(nrz, gaussian_taps(sps), mode="same")


def fine_codes(freq_hz, step_hz):
    """Quantize the trajectory to signed DCO fine-bank codes."""
    return np.round(freq_hz / step_hz).astype(int)


def demod_bits(freq_hz, sps=16):
    """Slice the frequency at each symbol centre (ideal FM discriminator)."""
    return [int(f > 0) for f in freq_hz[sps // 2 :: sps]]


def decode(bits, channel):
    """Inverse of air_bits: returns (pdu, crc_ok)."""
    body = whiten_bits(bits[40:], channel)
    length = bits_to_bytes(body[8:16])[0]
    n = (2 + length + 3) * 8
    raw = bits_to_bytes(body[:n])
    pdu, crc = raw[:-3], raw[-3:]
    return pdu, crc24(pdu) == crc


if __name__ == "__main__":
    addr = bytes.fromhex("C0FFEE180001")  # random static address (top bits 11)
    pdu = adv_nonconn_pdu(addr, bytes([2, 0x01, 0x06]) + complete_local_name("GF180-BLE"))
    bits = air_bits(pdu, 37)
    f = frequency_trajectory(bits)
    codes = fine_codes(f, 20e3)
    print(f"PDU {pdu.hex()}  CRC {crc24(pdu).hex()}")
    print(f"{len(bits)} bits = {len(bits)} us on air at {ADV_CHANNEL_FREQ_MHZ[37]} MHz")
    print(f"fine code range at 20 kHz/step: {codes.min()}..{codes.max()}")
    print("decode:", decode(demod_bits(f), 37))
