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

The integrated top cell, `PLL_COMPACT`, is in [build/](build/README.md). It
holds the PLL, the VCO supply regulator, on-chip bias, loop filter, RF converter
and PA device, and the UART/modulator. The PLL block layouts are in
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
| `build/`   | `PLL_COMPACT` integration: layout, LVS reference, build scripts, verification, post-PEX lock sims |
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

`build/` holds `PLL_COMPACT`, a compact integration of the PLL blocks, the
3.3 V VCO supply regulator, a bias block (2.5 µA charge-pump current, 1.7 V
TAIL_BIAS), a stacked loop filter (440 kΩ, 143.6 pF, 1.29 pF), the RF converter
and PA device, and the BLE UART/modulator, on the six-metal GF180MCU E stack.
It replaces the first integration, `A01_topcell` (commit f8b50d8). Details,
checks and rebuild commands are in [build/README.md](build/README.md).

- **Checks:** DRC 78, all inherited from the VCO (OFFGRID, DF.9). Full-chip LVS matches uniquely (22,912 devices). The connectivity check finds no problems.
- **Post-PEX lock (SS, 125 °C):** channel 0 locks within ±50 kHz at 498 µs; a hop to channel 15 locks 478 µs after the hop.
- **LVS config:** the root [`lvs_config.json`](lvs_config.json) points at `build/gds/PLL_COMPACT.gds` and the reference netlists in `build/spice/`.
- **Open:** the PA converter fails after extraction (needs a CML pre-amp), channels 34–39 are out of tuning range at SS/125 °C, and the A01 PFD has no frequency detection (slow acquisition).

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
