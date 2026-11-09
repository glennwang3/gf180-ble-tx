# Plan

Full write-up with sources: https://claude.ai/artifact/6g8gbiTWdi9Dkt8bkPgRi4

## Target (BLE 1M PHY, advertising only)

| Parameter        | Requirement                    |
|------------------|--------------------------------|
| Channels         | 37/38/39 = 2402/2426/2480 MHz  |
| Modulation       | GFSK, BT = 0.5, h = 0.45–0.55 (±250 kHz nominal) |
| Symbol rate      | 1 Msym/s                       |
| Carrier offset   | ±150 kHz                       |
| Drift in packet  | ≤ 50 kHz (packet ≤ 376 µs)     |
| TX power         | ~0 dBm at the pin              |

## Chip 1 architecture

- 2.4 GHz LC DCO with coarse, mid and fine capacitor banks.
- Digital FLL counts divided DCO cycles against a 32 MHz crystal before each
  packet, then freezes codes and transmits open-loop.
- Verilog modulator: packet build, whitening, CRC24, Gaussian LUT to fine code.
- Buffer plus inverter/class-E PA; final match on the PCB.
- Test structures: standalone inductors, divided DCO output pin, digital bypass.

## Roadmap

| Phase | Work | Exit criterion |
|-------|------|----------------|
| P0 | Tools, PDK, device fT sweep, Python golden model | fT known; model packet decodes |
| P1 | Spiral inductors and cap banks in OpenEMS | Tank Q and tuning cover 2402–2480 MHz over corners |
| P2 | DCO schematic, layout, PEX | Fine step < 30 kHz, drift < 50 kHz per packet |
| P3 | PA, ESD pad, bond wire and match co-sim | ~0 dBm into 50 Ω in sim |
| P4 | Digital modulator, FLL, SPI; LibreLane | Bit-exact vs model, timing clean at 32 MHz |
| P5 | Top-level integration, DRC/LVS, GDS | Accepted on shuttle |
| P6 | Bring-up board, SDR and phone test | Phone decodes the advertisement |

Candidate shuttle: wafer.space GF180MCU Run 3 (slot purchase by 9 Dec 2026,
GDS due 16 Dec 2026, parts Q2 2027).

## Status

- [x] P0: Python golden model (`model/`), CRC checked against scapy's implementation
- [ ] P0: device fT / gm-Id sweeps
- [x] P4: modulator RTL (`digital/`), bit-exact vs model in RTL and gate-level sim, 2 MHz clock
- [ ] Verify model against a real BLE sniffer capture
