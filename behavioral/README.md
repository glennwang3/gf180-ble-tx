# Behavioral transmit chain

The full transmitter in Verilog: the real modulator RTL (`digital/rtl/ble_tx.v`)
driving behavioral models of the analog blocks in the proposal
(Figure 1a and 1b). Use it to check the system before the transistor-level
cells exist, and to set specs for them.

```
ble_tx (RTL) -> dac_behav -> pll_behav (PFD/CP, loop filter, VCO, /N) -> pa_behav -> ANT
```

| File | Contents |
|------|----------|
| `models/dac_behav.v` | 8-bit signed DAC, zero-order hold on the sample clock |
| `models/pll_behav.v` | Integer-N PLL, phase-domain: tri-state PFD and charge pump, type-II 3rd-order loop filter, VCO with a separate modulation input, divider, lock detect |
| `models/pa_behav.v` | Switching amplifier: power from supply and load, `(2*VDD/pi)^2 / (2*RL)` |
| `tb_tx_chain.v` | Wires the chain; maps BLE channel index to N for a 2 MHz reference |
| `test_tx_chain.py` | cocotb tests that measure the RF output against the BLE limits |

Real values cross module ports as `$realtobits` so it runs on Icarus.

## How a packet is sent

1. Enable the PLL on the channel with the loop closed; wait for `locked`.
2. Assert `pll_hold` (charge pump off, loop open) and start the modulator.
   GFSK has energy far below the 100 kHz loop bandwidth, so a closed loop would
   fight the modulation. With the loop open the DAC drives the VCO's
   modulation input directly.
3. Release `pll_hold` after the packet.

The modulator's 6-bit fine code (20 kHz/LSB) is sign-extended onto the 8-bit
DAC. With a 1 V span the DAC LSB is 3.906 mV, so the VCO modulation gain is
20 kHz / 3.906 mV = 5.12 MHz/V.

## Default analog parameters

| Block | Parameter | Default |
|------|----------|---------|
| Reference | `F_REF` | 2 MHz (N = 1201..1240) |
| VCO | `F0`, `KVCO` | 2.3 GHz at 0 V, 200 MHz/V (2402..2480 MHz at 0.51..0.90 V) |
| Charge pump | `ICP` | 100 uA |
| Loop filter | `R`, `C1`, `C2` | 41.3 kOhm, 143.8 pF, 11.1 pF: 100 kHz bandwidth, 60 deg phase margin at N = 1220 |
| Amplifier | `VDD_PA`, `RL` | 0.49 V, 50 Ohm: -0.12 dBm |

These are placeholders to replace with the real cells' numbers as the PLL,
DAC and amplifier designs firm up. `pll_behav.ref_ppm`, `pll_behav.ileak` and
`pa_behav.vdd_pa` can also be set from a test at run time.

## What the tests check

Per packet, the way a BLE tester would (Core spec Vol 6 Part A 4.4):

- the RF frequency, demodulated at symbol centres, decodes to the PDU with a good CRC
- centre-frequency error within +-150 kHz, drift within the packet under 50 kHz, drift rate under 400 Hz/us
- deviation on settled symbols 225..275 kHz (modulation index 0.45..0.55); the
  current 20 kHz fine-code step gives 240 kHz, h = 0.48
- output power within class 3 (-20..0 dBm)

| Test | Result with the defaults |
|------|--------------------------|
| `nominal_channels` (37, 38, 39, 0, 36) | lock in about 46 us, centre error about 1 kHz, h = 0.48, -0.12 dBm |
| `random_payloads` | decode with a good CRC |
| `crystal_error` (40 ppm) | carrier 99 kHz high, still inside +-150 kHz |
| `loop_filter_leakage` | 0.1 nA passes (129 Hz/us); 1 nA fails at 1290 Hz/us. Leakage on the loop filter must stay below about 0.3 nA |
| `pa_supply_sets_power` | 0.49 V gives -0.12 dBm, 0.245 V gives -6.14 dBm |

The leakage limit falls out of the drift-rate spec:
`KVCO * ILEAK / (C1 + C2) < 400 Hz/us`, so `ILEAK < 400e6 * 155 pF / 200 MHz/V = 0.31 nA`.
That is a real target for the PLL's charge pump and loop filter switches.

## Running

```sh
cd behavioral && python3 test_tx_chain.py        # SPS=2 and 16, about 1 minute
SPS=2 python3 test_tx_chain.py                   # one rate
```

The modulator RTL tests are in `digital/test/` (`test_ble_tx.py` for packets
against the model, `test_ble_tx_edge.py` for corner cases). CI
(`.github/workflows/sim.yml`) runs all three and checks their results with
`scripts/check_cocotb_results.py`.

## Not modelled yet

- VCO and reference phase noise, charge pump mismatch and reference spurs
- DAC INL/DNL, glitches and settling
- Amplifier ramp shape and harmonics
- 8 samples per symbol: the proposal's DAC runs at 8 MS/s, but `ble_tx`
  only has Gaussian tables for 2 and 16 samples per symbol today
