#!/usr/bin/env python3
"""Loop after widening the regulator to VOUT = a + b*VCTRL (b = 0.6) with the low-cap VCO.
Ring Kv per V of VCTRL = (RF supply sensitivity / 2) * b: SS 0.74, TT 1.29, FF-40 2.2 GHz/V at RF.
Same loop model as sim/retune/size.py (C2 143.6 pF, N 1201, regulator = single pole)."""
import sys
sys.path.insert(0, "/foss/designs/pll_compact/sim/retune")
from size import loop  # noqa: E402
B = 0.6
KV = {"SS/125": 0.74e9 / 2 * B, "TT/27": 1.29e9 / 2 * B, "FF/-40": 2.2e9 / 2 * B}
print("ring Kv per V of VCTRL:", {k: f"{v/1e6:.0f} MHz/V" for k, v in KV.items()})
print("old design: Icp 2.5 uA, Rz 440k, C1 1.29p, Kv 70.4 MHz/V -> fc %.1f kHz PM %.1f (pole 39k)" % loop(2.5e-6, 440e3, 1.29e-12, 70.4e6, 39e3))
for icp in (0.25e-6, 0.35e-6, 0.5e-6, 0.7e-6, 1.0e-6):
    for R in (440e3, 600e3, 800e3):
        row, worst = [], 999
        for c, kv in KV.items():
            for k_i in (0.75, 1.0, 1.37):
                for fr in (39e3, 84e3):
                    fc, pm = loop(icp * k_i, R, 1.29e-12, kv, fr)
                    worst = min(worst, pm)
            fc, pm = loop(icp, R, 1.29e-12, kv, 39e3 if c == "SS/125" else 84e3)
            row.append(f"{c}: fc {fc:5.1f} kHz PM {pm:4.1f}")
        print(f"Icp {icp*1e6:4.2f} uA Rz {R/1e3:3.0f}k | " + " | ".join(row) + f" | worst {worst:4.1f}")

# ---- final: b = 0.65, Icp from the new PLL_BIAS (regcheck.py), regulator pole at each corner's channel-0 point
# (rangecheck.py: SS/125 ~20-25 kHz near dropout, TT ~4 MHz, FF/-40 ~1.3 MHz at VCTRL 0.6)
print("\nfinal (b 0.65, Rz 440k, C1 1.29p):")
for c, icp, kvrf, fr in (("SS/125", 0.392e-6, 0.74e9, 20e3), ("SS/125 pole 25k", 0.392e-6, 0.74e9, 25e3),
                         ("TT/27", 0.466e-6, 1.29e9, 4e6), ("FF/-40", 0.573e-6, 2.2e9, 1.3e6)):
    fc, pm = loop(icp, 440e3, 1.29e-12, kvrf / 2 * 0.65, fr)
    print(f"  {c:16s} Icp {icp*1e6:.3f} uA, ring Kv {kvrf/2*0.65/1e6:.0f} MHz/V, reg pole {fr/1e3:.0f} kHz -> fc {fc:.1f} kHz, PM {pm:.1f} deg")
