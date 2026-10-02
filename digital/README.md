# Digital modulator

`ble_tx` turns a legacy advertising PDU into a stream of signed DCO fine-bank
codes: preamble, access address, PDU and CRC24 (whitened), Gaussian filtered
(BT = 0.5), one code per clock. It matches `model/ble_adv.py` bit for bit:

```python
air_bits(pdu, channel)                                    # air_bit at each sym_strobe
fine_codes(frequency_trajectory(bits, SPS), 20e3)         # fine_code while code_valid
```

| File | Contents |
|------|----------|
| `rtl/ble_tx.v` | Top: PDU buffer, bit sequencer, CRC24, whitening, filter window |
| `rtl/ble_gauss_lut.v` | Generated Gaussian LUT (do not edit) |
| `scripts/gen_gauss_lut.py` | Regenerates the LUT from the model (`--step-hz`, `--sps`, `--width`) |
| `test/test_ble_tx.py` | cocotb: compares RTL or gate-level netlist against the model |
| `synth/synth.tcl` | Quick Yosys synthesis onto `gf180mcu_fd_sc_mcu7t5v0` |
| `librelane/config.yaml` | LibreLane RTL-to-GDS flow |

## Interface

Write the PDU bytes (`header0`, `length`, payload) with `wr_en`/`wr_addr`/`wr_data`,
set `channel`, pulse `start`. `busy` stays high until the last code is out. The
first code arrives 2 symbols + 1 clock after `start`, because each output
sample needs the symbols up to 1.5 symbols ahead.

`SPS` is the clock in MHz (samples per 1 us symbol). The default is 2 for the
2 MHz reference; 16 (16 MHz) is also generated and tested. Fine codes are
6-bit signed, 20 kHz/LSB, range -12..12.

## Running (IIC-OSIC-TOOLS container, from `/foss/designs/gf180-ble-tx/digital`)

```sh
python3 scripts/gen_gauss_lut.py                          # only after changing step/SPS
cd test && python3 test_ble_tx.py                         # RTL, SPS=2 and 16
cd ../synth && SPS=2 yosys -c synth.tcl                   # netlist + area report
cd ../test && GL=1 SPS=2 python3 test_ble_tx.py           # gate-level sim of that netlist
cd ../librelane && librelane --manual-pdk --pdk-root $PDK_ROOT --pdk gf180mcuD \
    --scl gf180mcu_fd_sc_mcu7t5v0 config.yaml
```
