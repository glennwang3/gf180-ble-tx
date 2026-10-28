# Digital modulator

`ble_tx` turns a legacy advertising PDU into a stream of signed 8-bit DAC
codes for the PLL's modulation input: preamble, access address, PDU and CRC24 (whitened), Gaussian filtered
(BT = 0.5), one code per clock. It matches `model/ble_adv.py` bit for bit:

```python
air_bits(pdu, channel)                                    # air_bit at each sym_strobe
fine_codes(frequency_trajectory(bits, SPS), 2e3)          # fine_code while code_valid
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
set `channel`, pulse `start`. The length byte is latched at `start`; payload
bytes are read live, so only rewrite ones already sent. `busy` stays high
until the last code is out. The
first code arrives 2 symbols + 1 clock after `start`, because each output
sample needs the symbols up to 1.5 symbols ahead.

`SPS` is the clock in MHz (samples per 1 us symbol). The default is 8: an
8 MHz clock gives one code per clock for the 8 MS/s DAC. SPS 2 and 16 are also
generated and tested. Codes are 8-bit signed, 2 kHz/LSB, range -125..125
(+-250 kHz deviation); the DAC and VCO modulation gain set the real Hz/LSB.

## Running (IIC-OSIC-TOOLS container, from `/foss/designs/gf180-ble-tx/digital`)

```sh
python3 scripts/gen_gauss_lut.py                          # only after changing step/SPS
cd test && python3 test_ble_tx.py                         # RTL, SPS=2, 8 and 16
cd ../synth && SPS=8 yosys -c synth.tcl                   # netlist + area report
cd ../test && GL=1 SPS=8 python3 test_ble_tx.py           # gate-level sim of that netlist
cd ../librelane && librelane --manual-pdk --pdk-root $PDK_ROOT --pdk gf180mcuD \
    --scl gf180mcu_fd_sc_mcu7t5v0 config.yaml
```

## Pre-layout timing

`sta/sta.tcl` runs OpenSTA on the Yosys netlist at the ss_125C_4v50,
tt_025C_5v00 and ff_n40C_5v50 corners with the constraints in
`sta/ble_tx.sdc`: 8 MHz clock (period from `SPS`, or `CLOCK_PERIOD` in ns),
30% of the period for I/O on each side, 1 ns setup / 0.25 ns hold uncertainty
for the ideal clock, and the 3 ns max-slew limit LibreLane signs off against.
There are no wire parasitics yet, so expect post-layout slack to be a few ns
lower.

```sh
cd synth && SPS=8 yosys -c synth.tcl          # netlist
cd ../sta && SPS=8 sta -exit sta.tcl          # worst slack per corner + sta/reports/sta_sps8.rpt
```
