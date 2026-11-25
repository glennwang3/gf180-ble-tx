# gf180-ble-tx

A transmit-only Bluetooth Low Energy (1M PHY, 2.4 GHz GFSK) beacon on the
GF180MCU open PDK, built with open-source tools.

The chip sends legacy advertising packets that a phone BLE scanner can see.
This repository holds its digital part: the modulator that builds each packet and
turns it into GFSK frequency codes, and the one-pin UART interface it is loaded
through, with a debug UART output (`dbg_tx`). It runs at 3.3 V. The analog blocks on the same chip are designed by teammates and are not
covered here. See [docs/plan.md](docs/plan.md).

## Layout

| Folder     | Contents |
|------------|----------|
| `model/`   | Python golden model: packet build, CRC24, whitening, GFSK trajectory, decode |
| `behavioral/` | The modulator RTL driving placeholder models of the analog chain, to check its RF output |
| `digital/` | Verilog modulator, its one-pin UART front end and `dbg_tx` debug UART (FLL calibration to come); cocotb tests; Yosys, OpenSTA, LibreLane and the agent-driven layout flow |
| `tapeout/` | Signed-off blocks for the chip top level (now `ble_tx_uart`, 330 x 300 um at 3.3 V); later the top level in the shuttle template |

## Golden model

```sh
cd model
pip install -r requirements.txt
python ble_adv.py      # build and decode a "GF180-BLE" advertisement
pytest -q
```

## Tools

IIC-OSIC-TOOLS container with the `gf180mcuD` PDK, Yosys, OpenSTA, LibreLane,
KLayout, Magic, Netgen, Verilator, cocotb and Icarus Verilog.

## License

Apache-2.0
