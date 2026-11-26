#!/usr/bin/env python3
"""
PLL_COMPACT: compact BLE PLL / TX integration (GF180MCU, 6-metal E stack).

  low-cap Schottky VCO (Differential_VCO_LC: delivered cell minus the doubler's 2nd / 3rd inverters)  origin
  RF_CHAIN_PA (graded self-biased chain + 50u class-C PA), rotated     west of the VCO, RF_DRV1 link ~14 um
  32/33 prescaler (mirrored)                                          on top of the VCO, CORE_CLK ~12 um
  integer-N divider (mirrored in x)                                   right of the prescaler, MC ~2.5 um
  PFD (mirrored) + charge pump                                        right of the divider, FB_1M ~4 um
  VCO_REG_L (3.3 V tracking regulator)                                right of the VCO, VDD_VCO M5 strap
  PLL_LF_L (stacked MIM + MOS loop filter)                            right of the regulator
  ble_tx_uart (digital)                                               left, away from the VCO

Stage 1 (this file): placement + pin table.  Routing is added by route_top.py.
"""
import json
import os
import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/foss/designs/pll_integration_repo"
TOP = "PLL_COMPACT"
U = 1000

# name: (gds, cell, rot, mirror, dx, dy)   (klayout Trans: mirror at x axis first, then rotate)
PLACE = {
    "vco": (f"{HERE}/vco_lc/Differential_VCO_LC.gds", "Differential_VCO_LC", 0, False, 0.0, 0.0),
    "prescaler": (f"{REPO}/PLL/analog/prescaler/32_33_Prescaler_fixed.gds", "32_33_Complete_Prescaler", 0, True, -27.28, 41.76),
    "divider": (f"{REPO}/PLL/analog/integer_n_divider/ble_feedback_divider.gds", "ble_feedback_divider", 2, True, 73.84, 6.06),
    "pfd": (f"{REPO}/PLL/analog/phase_detector/Phase_Detector_FE_fixed.gds", "Phase_Detector_FE", 2, True, 85.0, 30.27),
    "pump": (f"{REPO}/PLL/analog/charge_pump/Charge_Pump_FE_fixed.gds", "Charge_Pump_FE", 0, False, 99.3, 30.27),
    "reg": (f"{HERE}/VCO_REG_L.gds", "VCO_REG_L", 0, False, 13.32, -101.27),
    "lf": (f"{HERE}/PLL_LF_L.gds", "PLL_LF_L", 0, False, 176.7, -100.67),
    "chain": (f"{HERE}/RF_CHAIN_PA.gds", "RF_CHAIN_PA", 3, True, -28.6, 6.43),     # (x, y) -> (-y - 28.6, -x + 6.43)
    "bias": (f"{HERE}/PLL_BIAS.gds", "PLL_BIAS", 0, False, 108.0, 3.2),
    "tx": (f"{REPO}/tapeout/ble_tx_uart/gds/ble_tx_uart.gds", "ble_tx_uart", 0, False, -340.0, -95.0),
}

# PFD_VARIANT=ts: the three-state PFD (TS_PFD, Centurelli et al. Fig. 4, from the user's TSPC cells) replaces the A01
# Phase_Detector_FE; it sits above the divider / bias (x 76 .. 156, y 72 .. 98).  Writes PLL_TSPFD.
PFD_TS = os.environ.get("PFD_VARIANT") == "ts"
TS0 = (76.0, 98.5)
TS_PIN = {"R": (4.0, -26.0), "V": (10.0, -26.0), "DN": (16.0, -26.0), "UPB": (22.0, -26.0),
          "vss": (30.0, -26.0), "3v3": (38.0, -26.0)}         # TS_PFD boundary ports (M5, below its bottom row)
ts_pt = lambda name: (round(TS0[0] + TS_PIN[name][0], 3), round(TS0[1] + TS_PIN[name][1], 3))
PINS_JSON = "pins_tspfd.json" if PFD_TS else "pins.json"
if PFD_TS:
    TOP = "PLL_TSPFD"
    del PLACE["pfd"]
    PLACE["tspfd"] = ("/foss/designs/Tri_State_Phase_Detector/TS_PFD.gds", "TS_PFD", 0, False, *TS0)
# LF_VARIANT=c10: PLL_LF_L10 (C1 10 pF: + 8.7 pF MIM row above the filter, build_lf10.py).  Writes <TOP>_C1.
LF10 = os.environ.get("LF_VARIANT") == "c10"
if LF10:
    TOP = TOP + "_C1"
    PINS_JSON = PINS_JSON.replace(".json", "_c1.json")
    PLACE["lf"] = (f"{HERE}/PLL_LF_L10.gds", "PLL_LF_L10", 0, False, 176.7, -100.67)


def trans(rot, mirror, dx, dy):
    return db.Trans(rot, mirror, round(dx * U), round(dy * U))


def assemble():
    ly = db.Layout(); ly.dbu = 0.001
    opt = db.LoadLayoutOptions()
    opt.cell_conflict_resolution = db.LoadLayoutOptions.RenameCell
    top = ly.create_cell(TOP)
    cells = {}
    for key, (gds, cname, rot, mir, dx, dy) in PLACE.items():
        before = {c.cell_index() for c in ly.each_cell()}
        ly.read(gds, opt)
        new = [c for c in ly.each_cell() if c.cell_index() not in before]
        cell = next(c for c in new if c.name.split("$")[0] == cname)
        top.insert(db.CellInstArray(cell.cell_index(), trans(rot, mir, dx, dy)))
        cells[key] = cell
    for c in list(ly.top_cells()):
        if c.cell_index() != top.cell_index():
            ly.delete_cell_rec(c.cell_index())
    return ly, top, cells


if __name__ == "__main__":
    ly, top, cells = assemble()
    boxes = {}
    for key, cell in cells.items():
        inst = next(i for i in top.each_inst() if i.cell_index == cell.cell_index())
        b = inst.dbbox()
        boxes[key] = b
        print(f"{key:10s} {cell.name:28s} bbox {b.left:8.2f},{b.bottom:8.2f} .. {b.right:8.2f},{b.top:8.2f}")
    keys = list(boxes)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if boxes[a].overlaps(boxes[b]) or (boxes[a] & boxes[b]).area() > 0:
                print("OVERLAP", a, b)
    ly.write(os.path.join(HERE, "placed.gds"))
    b = top.dbbox()
    print(f"TOP bbox {b.left:.2f},{b.bottom:.2f} .. {b.right:.2f},{b.top:.2f}  ({b.width():.1f} x {b.height():.1f})")
