#!/usr/bin/env python3
"""GFSK DAC stimulus for a bit pattern, using the repo's golden model (model/ble_adv.py), which the ble_tx RTL
matches bit-exactly: SPS = 8 (CLK_8M), 2 kHz/LSB, +-125 at 250 kHz deviation, code 0 when idle.
The 8-bit code drives VTUNE through the DAC: VTUNE = VB + code * LSB_V, LSB_V = 2 kHz / Kvt.
    python3 gfsk.py BITS VB LSB_mV T_LEAD_us T_TAIL_us OUT_PREFIX [T_FROM_us T_TO_us T_SETTLE_ns]
Writes OUT_PREFIX_codes.txt (t_us, code, f_ideal_Hz) and OUT_PREFIX.pwl for ngspice. With T_FROM/T_TO only that
window is written, shifted to start at T_SETTLE (VTUNE held at its T_FROM value before it) - for chunked runs.
"""
import sys
import os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "model"))
from ble_adv import gaussian_taps, fine_codes  # noqa: E402

SPS, DEV, STEP = 8, 250e3, 2e3
bits = [int(c) for c in sys.argv[1]]
vb, lsb = float(sys.argv[2]), float(sys.argv[3]) * 1e-3
lead, tail = float(sys.argv[4]), float(sys.argv[5])
pre = sys.argv[6]
nl, nt = int(round(lead * SPS)), int(round(tail * SPS))
nrz = np.concatenate([np.zeros(nl), np.repeat(2 * np.array(bits) - 1, SPS), np.zeros(nt)])
traj = DEV * np.convolve(nrz, gaussian_taps(SPS), mode="same")
code = fine_codes(traj, STEP)
assert np.abs(code).max() <= 127
ts = np.arange(len(code)) / (SPS * 1e6)                      # code k holds from ts[k] to ts[k+1]
np.savetxt(pre + "_codes.txt", np.column_stack([ts * 1e6, code, code * STEP]), fmt="%.4f %d %.0f",
           header="t_us code f_ideal_Hz (code holds until the next row)")
t0, t1, ts0 = 0.0, ts[-1] + 1 / (SPS * 1e6), 0.0
if len(sys.argv) > 7:
    t0, t1, ts0 = float(sys.argv[7]) * 1e-6, float(sys.argv[8]) * 1e-6, float(sys.argv[9]) * 1e-9
TR = 1e-9                                                    # DAC edge
pts = []
k0 = int(np.floor(t0 * SPS * 1e6 + 1e-9))
pts.append((0.0, vb + code[k0] * lsb))
for k in range(k0 + 1, len(code)):
    if ts[k] >= t1:
        break
    if code[k] != code[k - 1]:
        tt = ts[k] - t0 + ts0
        pts += [(tt, vb + code[k - 1] * lsb), (tt + TR, vb + code[k] * lsb)]
pts.append(((t1 - t0) + ts0, pts[-1][1]))
open(pre + ".pwl", "w").write("\n".join(f"{a:.6e} {b:.6f}" for a, b in pts) + "\n")
print(f"{len(code)} codes, {len(pts)} PWL points, code range {code.min()}..{code.max()}, "
      f"VTUNE {vb + code.min()*lsb:.4f}..{vb + code.max()*lsb:.4f} V, window {(t1-t0)*1e6:.3f} us")
