# gf180-ble-tx

A transmit-only Bluetooth Low Energy (1M PHY, 2.4 GHz GFSK) beacon on the
GF180MCU open PDK, built with open-source tools.

The first chip sends legacy advertising packets that a phone BLE scanner can
see. It uses a crystal-calibrated, open-loop 2.4 GHz LC DCO with direct GFSK
modulation through a fine capacitor bank, plus a switching PA at about 0 dBm.
A closed-loop PLL is planned for the second chip. See [docs/plan.md](docs/plan.md).

## Layout

| Folder     | Contents |
|------------|----------|
| `model/`   | Python golden model: packet build, CRC24, whitening, GFSK trajectory, decode |
| `em/`      | Inductor and passive EM models (OpenEMS, FastHenry2, gdsfactory) |
| `analog/`  | xschem schematics, ngspice/Xyce testbenches, layouts for DCO, PA, dividers |
| `digital/` | Verilog modulator, FLL calibration, SPI; cocotb tests; LibreLane config |
| `tapeout/` | Chip top-level in the shuttle template, DRC/LVS runs |
| `board/`   | KiCad bring-up board: crystal, RF match, antenna |

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
