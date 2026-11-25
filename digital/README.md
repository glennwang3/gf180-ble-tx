# Digital modulator

`ble_tx` turns a legacy advertising PDU into a stream of signed 8-bit frequency
codes for the analog modulation input: preamble, access address, PDU and CRC24
(whitened), Gaussian filtered (BT = 0.5), one code per clock. It matches `model/ble_adv.py` bit for bit:

```python
air_bits(pdu, channel)                                    # air_bit at each sym_strobe
fine_codes(frequency_trajectory(bits, SPS), 2e3)          # fine_code while code_valid
```

| File | Contents |
|------|----------|
| `rtl/ble_tx.v` | Top: PDU buffer, bit sequencer, CRC24, whitening, filter window |
| `rtl/ble_gauss_lut.v` | Generated Gaussian LUT (do not edit) |
| `rtl/ble_uart.v` | UART receiver and command decoder `ble_uart`, and the chip-level top `ble_tx_uart` (UART + `ble_tx`) |
| `scripts/gen_gauss_lut.py` | Regenerates the LUT from the model (`--step-hz`, `--sps`, `--width`) |
| `test/test_ble_tx.py` | cocotb: compares RTL or gate-level netlist against the model |
| `test/test_ble_tx_edge.py` | cocotb: corner cases (all 40 channels, length limits, reset, writes while busy) |
| `test/test_ble_tx_uart.py` | cocotb: the same through the single UART pin, RTL or gate level |
| `synth/synth.tcl` | Quick Yosys synthesis onto `gf180mcu_fd_sc_mcu7t5v0` (`TOP=ble_tx_uart` for the chip-level block) |
| `sta/sta.tcl`, `sta/ble_tx.sdc` | Pre-layout timing (below) |
| `librelane/config.yaml` | Plain LibreLane RTL-to-GDS flow for `ble_tx` |
| `agent/` | Agent-driven LibreLane flow; `agent/designs/ble_tx_uart` gives the signed-off layout in `../tapeout/ble_tx_uart` |

## Interface

Write the PDU bytes (`header0`, `length`, payload) with `wr_en`/`wr_addr`/`wr_data`,
set `channel`, pulse `start`. The length byte is latched at `start`; payload
bytes are read live, so only rewrite ones already sent. `busy` stays high
until the last code is out. The
first air bit's code (`code_valid` high) arrives 3 symbols + 1 clock after the
clock edge that takes `start`; `fine_code` ramps into it from about 2 symbols,
because each output sample needs the symbols up to 1.5 symbols ahead.

`SPS` is the clock in MHz (samples per 1 us symbol). The default is 8: an
8 MHz clock gives one code per clock, 8 MS/s. SPS 2 and 16 are also generated
and tested. Codes are 8-bit signed, 2 kHz/LSB, range -125..125 (+-250 kHz
deviation); the analog modulation gain sets the real Hz/LSB.

## Serial interface (`ble_tx_uart`)

`ble_tx_uart` puts a UART receiver in front of `ble_tx`, so the chip takes its
packet, channel and start over one input pin, `uart_rx`. Any MCU UART TX pin or
a USB-serial adapter can drive it. It is the only connection to the controller:
there is no read path and no `busy` pin. A packet's air time is fixed by its
length, so once the start byte has been sent, wait `(10 + len) x 8 + 10` us
(`len` = the PDU's length byte), or 400 us for any packet, before loading the
next PDU or starting again. A start sent while a packet is on air is ignored, and
a PDU written then can corrupt the packet on air.

`uart_rx` is standard 8N1: idle high, a low start bit, 8 data bits LSB first, a
high stop bit. A bit lasts `CLKS_PER_BIT` clocks (default 8), so the baud rate
is clk/8: 1 Mbaud at SPS=8, 250 kbaud at SPS=2, 2 Mbaud at SPS=16. The
receiver samples the middle of each bit and resynchronizes on every start bit,
so the sender may be about 3% off. Pulses shorter than half a bit are ignored
and a byte with a low stop bit is dropped.

A pause marks where a command starts: once the line has been idle for
`GAP_BITS` bit times (default 20, 20 us at 1 Mbaud; counted to within one bit), the next byte is a command.
Send each command as one burst, then pause.

| Command | Data | Action |
|---------|------|--------|
| `00aa_aaaa` | `d0 d1 ...` | Write PDU bytes from address `a` (0 = header0, 1 = length, 2.. = payload); the address increments |
| `01cc_cccc` | none | `channel = c` (latched by `ble_tx` at start; 37 after reset) |
| `1xxx_xxx1` | none | pulses `start` |
| `11xx_xxe0` | optional `k` | debug UART `dbg_tx` on (`e = 1`) or off (`e = 0`); a byte after it in the same burst sets the sample offset `k` (0..79; kept if not sent; 0 after reset) |
| `10xx_xxx0` | none | no operation |

A full 39-byte PDU loads in about 0.4 ms at 1 Mbaud. From Python:

```python
import serial, time
s = serial.Serial("/dev/tty.usbserial", 1_000_000)
s.write(bytes([0x00]) + pdu); time.sleep(0.001)   # PDU from address 0
s.write(bytes([0x40 | 37]));  time.sleep(0.001)   # channel 37
s.write(bytes([0x81])); s.flush()                 # start
time.sleep(400e-6)                                # on air; then the next packet
```

`fine_code`, `code_valid`, `air_bit` and `sym_strobe` come straight out of
`ble_tx`, as described above; its `busy` stays inside the block.

### Debug UART (`dbg_tx`)

`dbg_tx` is a second UART, an output: 8N1 at the same baud rate as `uart_rx`
(1 Mbaud at SPS=8), idle high, so a USB-serial adapter that does 1 Mbaud (FTDI
FT232R/FT232H, CP2102N, CH340) can capture it. It is off after reset; off, the
pin stays high and its logic is clock-gated, so it costs no power. While it is on,
each packet sends:

1. the marker `0x80` when the start byte is taken. Codes stay within +-125, so
   `0x80` (-128) never appears as a code;
2. `fine_code` (signed, two's complement) at the packet's code indices `k`,
   `k+80`, `k+160`, ... counted from its first valid code. One byte takes 80
   clocks, so they come back to back: 37 or 38 codes for a 37-byte payload.

A packet is deterministic, so sending it 80 times with `k = 0..79` gives every
code of the 8 MS/s waveform (3008 for a 37-byte payload). `k` above 79 sends
the marker only. Turning it off mid-packet lets the current byte finish. Change
the setting between packets: turned on mid-packet, which codes it samples is not
defined. The code index modulo 80 comes from `ble_tx`'s sample phase (its
`sym_phase` port) and a symbol counter modulo 10, so the debug logic costs about
3.5k um2 of cells (4.2k with its UART command decode).

```python
import serial, time
tx = serial.Serial("/dev/tty.usbserial-CMD", 1_000_000)        # to uart_rx
rx = serial.Serial("/dev/tty.usbserial-DBG", 1_000_000, timeout=0.01)  # from dbg_tx
tx.write(bytes([0x00]) + pdu); time.sleep(0.001)
tx.write(bytes([0x40 | 37]));  time.sleep(0.001)
wave = {}
for k in range(80):
    tx.write(bytes([0xC2, k])); time.sleep(0.001)   # debug on, offset k
    rx.reset_input_buffer()
    tx.write(bytes([0x81])); tx.flush(); time.sleep(0.001)
    data = rx.read(64)
    i = data.index(0x80)                             # marker
    for m, b in enumerate(data[i + 1:]):
        wave[k + 80 * m] = b - 256 if b >= 128 else b
codes = [wave[i] for i in sorted(wave)]              # full 8 MS/s waveform
tx.write(bytes([0xC0]))                              # debug off
```


## Running (IIC-OSIC-TOOLS container, from `/foss/designs/gf180-ble-tx/digital`)

```sh
python3 scripts/gen_gauss_lut.py                          # only after changing step/SPS
cd test && python3 test_ble_tx.py                         # RTL, SPS=2, 8 and 16
python3 test_ble_tx_uart.py                               # the same through the UART pin
python3 test_ble_dbg_tx.py                                # debug UART: 80 offsets rebuild the waveform
cd ../synth && SPS=8 yosys -c synth.tcl                   # netlist + area report
cd ../test && GL=1 SPS=8 python3 test_ble_tx.py           # gate-level sim of that netlist
cd ../synth && TOP=ble_tx_uart SPS=8 yosys -c synth.tcl   # with the UART front end
cd ../test && GL=1 SPS=8 python3 test_ble_tx_uart.py
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
lower. These are the script's 5 V corners (and `synth/synth.tcl` maps onto the
tt_025C_5v00 library); the chip runs at 3.3 V, and `ble_tx_uart` is signed off at
tt_025C_3v30, ss_125C_3v00 and ff_n40C_3v60 by the agent flow (`agent/designs/ble_tx_uart`).

```sh
cd synth && SPS=8 yosys -c synth.tcl          # netlist
cd ../sta && SPS=8 sta -exit sta.tcl          # worst slack per corner + sta/reports/sta_sps8.rpt
```
