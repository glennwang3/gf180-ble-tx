# ble_tx_uart layout

The signed-off layout of `ble_tx_uart`: the BLE advertising modulator (`ble_tx`)
with its one-pin UART front end (`ble_uart`) and the debug UART output `dbg_tx`,
on gf180mcuD, `gf180mcu_fd_sc_mcu7t5v0`, 5 metal layers, 3.3 V supply. The RTL is
the clock-gated design (V3 gating, see `power_exp/SUMMARY.md`) with the V7 debug
UART. This is a block for the chip's top level, not a full chip: it has no pad ring
and no metal fill.

| | |
|---|---|
| Die | 330 x 300 um (99,000 um2) |
| Standard cells | 76,571 um2, 85.7% utilisation (2,932 cells, 461 sequential cells, 49 clock gates) |
| Supply, corners | 3.3 V: tt_025C_3v30, ss_125C_3v00, ff_n40C_3v60, each with nom/min/max RC (9 corners) |
| Clock | 8 MHz (`clk`, 125 ns) |
| Power | 140.2 uW average at one packet per 100 ms (140.3 uW with `dbg_tx` on); 0.319 mW while transmitting, 0.139 mW idle, 0.172 mW while loading over `uart_rx` |
| Setup / hold slack, worst of 9 corners | +92.8 ns (max_ss_125C_3v00) / +0.18 ns (max_ff_n40C_3v60) |
| GDS sha256 (first 16) | `c810bf9a88c0feee` |

Slack per corner (ns):

| corner | setup nom / min / max RC | hold nom / min / max RC |
|---|---|---|
| tt_025C_3v30 | 105.0 / 105.1 / 104.8 | 0.538 / 0.547 / 0.502 |
| ss_125C_3v00 | 93.9 / 94.9 / 92.8 | 1.250 / 1.283 / 1.217 |
| ff_n40C_3v60 | 108.2 / 108.3 / 108.1 | 0.210 / 0.218 / 0.184 |

Power is OpenSTA at tt_025C_3v30 on the final netlist with the nominal SPEF and
switching activity from a gate-level VCD of that netlist (`power_exp/power/`): a
39-byte PDU loaded over `uart_rx` (458 us), the packet (389 us), then idle. Idle is
almost all of the average; 63% of it is the clock tree. With `dbg_tx` off its logic
is clock-gated.

## Pins

| Pin | Dir | |
|---|---|---|
| `clk` | in | 8 MHz clock |
| `rst_n` | in | reset, active low |
| `uart_rx` | in | 8N1 serial from the controller at clk/8 (1 Mbaud): the only controller connection |
| `fine_code[7:0]` | out | signed Gaussian-filtered frequency code, one per clock (to the analog modulation input) |
| `code_valid` | out | high while `fine_code` belongs to a packet |
| `air_bit` | out | the raw bit on air (test) |
| `sym_strobe` | out | first clock of each 1 us symbol (test) |
| `dbg_tx` | out | debug UART, 8N1 at 1 Mbaud, idle high: a marker and every 80th `fine_code` from offset `k` per packet. Off after reset; `C2 k` turns it on, `C0` off (`digital/README.md`) |
| `VDD`, `VSS` | power | 3.3 V |

There is no `busy` pin. A packet's air time is fixed by its length: once the start
byte has been sent, the controller waits `(10 + len) x 8 + 10` us, or 400 us for any
packet, before loading the next PDU (`digital/README.md`).

## Where it came from

- RTL: `digital/rtl/ble_uart.v`, `ble_tx.v`, `ble_gauss_lut.v` as of commit 2433cfc
  (V7 `dbg_tx`).
- Flow: `digital/agent`, design `designs/ble_tx_uart`, whose `config.yaml` is the
  3.3 V V7 recipe at 330 um. Lay it out again with

  ```sh
  cd digital/agent
  PD_FIX_HOLD=1 PD_FIX_PASSES=8 ./venv/bin/python -m pd.baseline --design designs/ble_tx_uart
  ```

  The signoff fix passes buffer, upsize and, with `PD_FIX_HOLD=1`, add hold delay
  cells (`pd/runner.py`, `pd/upsize.tcl`). Narrower dies (295-325 um) did not close
  (`power_exp/SUMMARY.md`).
- Signoff took six fix passes, 78 changes (`upsized_drivers.txt`): 58 drivers
  upsized, 3 buffers, 17 hold delay cells.
- The same files, with the power reports, are in `power_exp/layout_v7_330/`.

## What it passed

- Foundry KLayout DRC deck (`libs.tech/klayout/tech/drc`, variant D, 63 rule tables,
  front and back end): 0. The `mslot` table crashes on a known deck bug. Magic DRC 0,
  routing DRC 0, antenna 0.
- Netgen LVS 0; KLayout vs Magic GDS XOR 0.
- Setup and hold: 0 violations at all 9 corners (LibreLane's checkers on at every
  corner). Max slew (3 ns), capacitance and fanout: 0 at every corner. IR drop
  0.03 mV worst.
- `metrics.json` lists 2 `timing__drv__floating__nets` from the repair step after
  placement, and 10 unannotated nets per corner (0 after filtering): the outputs of
  the clock tree's 10 `clkload` dummy cells, unused by design.
- On `nl/ble_tx_uart.nl.v` with unit delay: `digital/test/test_ble_tx_uart.py`
  (9 tests, including the controller's fixed wait), `test_ble_dbg_tx.py` (all 80
  offsets) and the 2 clock-stop/restart tests (`power_exp/tune/test_clock_stop.py`).

## Files

| Folder | |
|---|---|
| `gds/` | the layout |
| `def/`, `lef/` | placement and routing; abstract for the top level |
| `lib/` | timing models at the 9 corners (3v30 / 3v00 / 3v60) |
| `nl/` | netlist (`.nl.v`), with power pins (`.pnl.v`), black-box header (`.vh`) |
| `sdc/` | constraints |
| `spef/` | parasitics, nominal corner |
| `sdf/` | delays at max_ss_125C_3v00 and max_ff_n40C_3v60 |
| `spice/` | extracted netlist used for LVS |
| `render/` | picture of the layout |
| `metrics.json`, `metrics.csv` | every signoff figure |
| `upsized_drivers.txt` | the signoff fix passes' changes |

Left out, as they can be made again from the config: the Magic and KLayout copies
of the GDS, the OpenROAD database, SPEF and SDF at the other corners.
