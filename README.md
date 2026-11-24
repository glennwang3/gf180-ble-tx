# gf180-ble-tx

A transmit-only Bluetooth Low Energy (1M PHY, 2.4 GHz GFSK) beacon on the
GF180MCU open PDK, built with open-source tools.

The chip sends legacy advertising packets that a phone BLE scanner can see.
An integer-N PLL generates the carrier. A 1 MHz reference drives a phase
detector, charge pump and RC loop filter. A differential VCO runs at half the
RF frequency, and a ×2 doubler brings its output to 2.402–2.480 GHz. A 32/33
prescaler and an integer-N divider close the feedback loop. A 6-bit `CFG` word
selects the BLE channel. The digital block receives packets over a 1 Mbaud
UART and produces a signed GFSK modulation word for the DAC.

The tapeout top cell, `E03` (Chipathon 2026 team E03), is in [build/](build/README.md)
as `build/gds/E03.gds`. It holds the PLL with the low-cap Schottky-doubler VCO, the
VCO supply regulator, on-chip bias, loop filter, an RF buffer chain and the PA
device, and the UART/modulator. The PLL block layouts are in
[PLL/analog/](PLL/analog/README.md). The DAC, pad ring and metal fill are not
integrated yet. See [docs/plan.md](docs/plan.md) for the original project plan.

## Layout

| Folder     | Contents |
|------------|----------|
| `model/`   | Python golden model: packet build, CRC24, whitening, GFSK trajectory, decode |
| `em/`      | Inductor and passive EM models (OpenEMS, FastHenry2, gdsfactory) |
| `analog/`  | xschem schematics, ngspice/Xyce testbenches, layouts for DCO, PA, dividers |
| `digital/` | Verilog modulator, FLL calibration, SPI; cocotb tests; LibreLane config |
| `PLL/analog/` | Current PLL block layouts, extracted netlists and Xschem sheets |
| `build/`   | `E03` tapeout integration: GDS, LVS reference, build and export scripts, verification, post-PEX sims |
| `tapeout/` | Chip top-level in the shuttle template, DRC/LVS runs |
| `board/`   | KiCad bring-up board: crystal, RF match, antenna |

## PLL analog blocks (`PLL/analog/`)

This folder holds the current layouts and schematics for the PLL blocks. Each
block has a GDS and an extracted SPICE netlist. Details are in
[PLL/analog/README.md](PLL/analog/README.md).

| Folder | Block | Contents | Footprint |
|---|---|---|---:|
| [`vco/`](PLL/analog/vco) | Differential VCO, RF doubler and feedback buffer | Routed GDS, full-RC PEX | 41 × 30.175 µm |
| [`prescaler/`](PLL/analog/prescaler) | 32/33 dual-modulus prescaler | GDS, capacitance extraction | 33.195 × 21.74 µm |
| [`integer_n_divider/`](PLL/analog/integer_n_divider) | Integer-N feedback divider (digital, place-and-route) | GDS, LEF, DEF, RTL, routed Verilog, extracted SPICE, BLE channel table | 51.84 × 63.04 µm |
| [`phase_detector/`](PLL/analog/phase_detector) | Phase-frequency detector | GDS, capacitance extraction | 12.59 × 7.81 µm |
| [`charge_pump/`](PLL/analog/charge_pump) | Charge pump | GDS, capacitance extraction | 9.42 × 10.76 µm |
| [`schematics/`](PLL/analog/schematics) | Xschem sheets and symbols | Block sheets, standard-cell models, legacy `PLL.sch` | — |

- **VCO:** main DRC and LVS passed. The extracted VCO runs at 1.3072 GHz, and the doubler output is 2.6148 GHz.
- **Schematics:** open the sheets with Xschem, using the GF180MCU D symbol libraries and `schematics/` as the working directory. Device sizes in the schematics can differ from the extracted layouts.
- **Legacy sheet:** `PLL.sch` shows an earlier ring-oscillator and fractional-N architecture. The routed differential VCO and integer-N divider above replace it.

## Top-level integration (`build/`)

`build/gds/E03.gds` (top cell `E03`) integrates the low-cap Schottky-doubler VCO,
a graded self-biased buffer chain and the 50 µm class-C PA device, the A01
prescaler, divider, PFD and charge pump, the 3.3 V VCO supply regulator
(VDD_VCO = 1.40 V + 0.65·VCTRL), a bias block (~0.47 µA charge pump, 1.7 V
TAIL_BIAS), a stacked loop filter (440 kΩ, 143.6 pF, 1.29 pF) and the BLE
UART/modulator, on the six-metal GF180MCU E stack. All other cells carry the
`E03_` prefix; the top-level pins are the `info.yaml` pins (`vdd`, `vss`,
`reset_n`, `clk`, `Tx`, `ANT`). Details, checks and rebuild commands are in
[build/README.md](build/README.md). Earlier integrations: `A01_topcell`
(commit f8b50d8) and the XOR-doubler `PLL_COMPACT` (commit b418248).

- **Checks:** DRC 0 on `E03.gds`. LVS against `build/spice/` matches uniquely (22,902 devices, 12,522 nets). The connectivity check finds no problems.
- **RF after PEX (TT):** channel 0 at +0.09 dBm into 100 Ω (20 % drain efficiency); TT lock to channel 0 without cycle slips.
- **LVS config:** the root [`lvs_config.json`](lvs_config.json) points at `build/gds/E03.gds` and the reference netlists in `build/spice/`.
- **Open:** ±1 MHz reference spurs at TT/FF (CP ripple through the regulator), no RF output at SS/125 °C, the A01 PFD has no frequency detection, and REF_1M, VTUNE (DAC) and CFG are not yet on pads.

## Golden model

```sh
cd model
pip install -r requirements.txt
python ble_adv.py      # build and decode a "GF180-BLE" advertisement
pytest -q
```

## Tools

IIC-OSIC-TOOLS container with the `gf180mcuD` PDK, xschem, ngspice, Xyce,
KLayout, Magic, Netgen, OpenEMS, LibreLane, cocotb, Icarus Verilog.

## License

Apache-2.0
