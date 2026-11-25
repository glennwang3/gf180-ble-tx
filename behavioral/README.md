# Behavioral transmit chain

A check of the modulator's output as RF: the real modulator RTL
(`digital/rtl/ble_tx.v`) drives simple behavioral stand-ins for the analog chain,
and the tests measure the resulting RF frequency the way a BLE tester would.

The analog models are placeholders for this check only. They are not the chip's
analog design, which teammates own, and their parameters (in the model files) are
not specs for it.

```
ble_tx (RTL) -> dac_behav -> pll_behav (loop opened during the packet) -> pa_behav -> ANT
```

| File | Contents |
|------|----------|
| `models/dac_behav.v`, `models/pll_behav.v`, `models/pa_behav.v` | Placeholder analog models: codes to voltage, voltage to frequency, frequency to output power |
| `tb_tx_chain.v` | Wires the chain to `ble_tx` |
| `test_tx_chain.py` | cocotb tests that measure the RF output against the BLE limits |

Real values cross module ports as `$realtobits` so it runs on Icarus.

## What the tests check

Per packet (Core spec Vol 6 Part A 4.4):

- the RF frequency, demodulated at symbol centres, decodes to the PDU with a good CRC
- centre-frequency error within +-150 kHz, drift within the packet under 50 kHz, drift rate under 400 Hz/us
- deviation on settled symbols 225..275 kHz (modulation index 0.45..0.55); the
  modulator's 2 kHz code step gives 250 kHz, h = 0.5
- output power within class 3 (-20..0 dBm)

| Test | What it varies |
|------|----------------|
| `nominal_channels` (37, 38, 39, 0, 36) | channel |
| `random_payloads` | payload contents and length |
| `crystal_error` | a reference error on the placeholder chain |
| `loop_filter_leakage` | drift added by the placeholder chain |
| `pa_supply_sets_power` | output power of the placeholder amplifier |

## Running

```sh
cd behavioral && python3 test_tx_chain.py        # SPS=2, 8 and 16, about 2 minutes
SPS=2 python3 test_tx_chain.py                   # one rate
```

The modulator RTL tests are in `digital/test/` (`test_ble_tx.py` for packets
against the model, `test_ble_tx_edge.py` for corner cases, `test_ble_tx_uart.py`
through the UART pin). CI (`.github/workflows/sim.yml`) runs them and this chain
test, and checks their results with `scripts/check_cocotb_results.py`.
