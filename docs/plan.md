# Plan: digital part

Full write-up with sources: https://claude.ai/artifact/6g8gbiTWdi9Dkt8bkPgRi4

This plan covers the digital part of the BLE transmitter chip. The analog blocks on
the same chip (oscillator, power amplifier and their test structures) and the board
are designed by teammates and are not described here; the digital block hands them
its frequency codes (`fine_code`, `code_valid`).

## Target (BLE 1M PHY, advertising only)

| Parameter        | Requirement                    |
|------------------|--------------------------------|
| Channels         | 37/38/39 = 2402/2426/2480 MHz (whitening is seeded from the channel index) |
| Modulation       | GFSK, BT = 0.5, h = 0.45–0.55 (±250 kHz nominal) |
| Symbol rate      | 1 Msym/s                       |
| Packet           | legacy advertising, ≤ 376 µs on air |

## Digital architecture

- Verilog modulator: packet build, whitening, CRC24, Gaussian LUT to fine code.
  The digital logic runs on an 8 MHz clock, the 32 MHz crystal divided by 4:
  8 samples per 1 µs symbol, one fine code per clock (8 MS/s).
- UART front end: the controller loads the packet, channel and start over one
  pin, `uart_rx`. A second UART, the output `dbg_tx`, sends `fine_code` samples for
  debugging; it is off and clock-gated unless turned on.
- 3.3 V supply. Clock gating keeps the block at about 140 µW average at one packet
  per 100 ms. Signed-off layout: `tapeout/ble_tx_uart`, 330 x 300 µm.
- Digital FLL: counts divided oscillator cycles against the 32 MHz crystal before
  each packet, then freezes the codes so the packet goes out open-loop.

## Roadmap

| Phase | Work | Exit criterion |
|-------|------|----------------|
| P0 | Tools, PDK, Python golden model | Model packet decodes |
| P4 | Digital modulator, FLL, UART; LibreLane | Bit-exact vs model, timing clean at 8 MHz |
| P5 | Top-level integration with the analog blocks, DRC/LVS, GDS | Accepted on shuttle |
