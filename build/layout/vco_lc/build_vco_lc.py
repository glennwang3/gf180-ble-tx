#!/usr/bin/env python3
"""
Low-cap Schottky VCO for PLL_COMPACT, without the doubler's 2nd / 3rd output inverters.

Source (read only): /foss/designs/Diff_VCO_Second_Layout/low_cap_vco_20261122/delivery/Differential_VCO_low_cap.gds
Writes: Differential_VCO_LC.gds, cell Differential_VCO_LC

The doubler output chain of the delivered cell is three 2/1 um inverter columns at a 4 um pitch:
    x -16.8  MIM_TOP -> RF_DRV1 (self-biased by the ppoly chain)   kept
    x -20.8  RF_DRV1 -> RF_DRV2                                     removed
    x -24.8  RF_DRV2 -> RF_OUT                                      removed
Their outputs could not drive any load (PA analysis in sim/lowcap); the graded self-biased chain in
RF_CHAIN_PA now hangs on RF_DRV1.  Removed: every shape lying entirely inside the two columns' box,
plus the RF_DRV2 / RF_OUT labels.  The n-well, the M4 VSS / VBUF_DOUBLER buses, stage 1's taps and
the resistor arrays above and below extend outside the box and are kept unchanged.
RF_DRV1 stays on M1 at x -20.04 .. -16.64, y 4.06 .. 7.02 (tap point).
"""
import os
import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/foss/designs/Diff_VCO_Second_Layout/low_cap_vco_20261122/delivery/Differential_VCO_low_cap.gds"
OUT = os.path.join(HERE, "Differential_VCO_LC.gds")
U = 1000
CUT = db.Box(round(-26.80 * U), round(3.00 * U), round(-19.60 * U), round(8.10 * U))
GONE = {"RF_DRV2", "RF_OUT", "P", "N", "B"}         # P / N / B: stray resistor-test labels (N sits on RF_DRV1 and VSS)


def main():
    ly = db.Layout(); ly.read(SRC)
    top = ly.cell("Differential_VCO")
    n = 0
    for li in ly.layer_indexes():
        sh = top.shapes(li)
        dead = [s for s in sh.each() if (s.is_text() and s.text.string in GONE) or
                (not s.is_text() and (s.bbox() & CUT) == s.bbox())]
        for s in dead:
            sh.erase(s)
        n += len(dead)
    top.name = "Differential_VCO_LC"
    top.shapes(ly.layer(34, 10)).insert(db.Text("RF_DRV1", db.Trans(round(-18.80 * U), round(5.50 * U))))
    ly.write(OUT)
    print(f"removed {n} shapes; wrote {OUT}")


if __name__ == "__main__":
    main()
