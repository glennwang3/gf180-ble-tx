import sys, numpy as np
sys.path.insert(0, "/foss/designs/pll_compact/sim")
from rawread import read_raw
w = read_raw(sys.argv[1]); t = w["time"]
up = w["v(upb)"] < 1.65; dn = w["v(dn)"] > 1.65
for a in range(0, 60, 3):
    m = (t >= a*1e-6) & (t < (a+3)*1e-6)
    tu = np.trapezoid(up[m].astype(float), t[m]); td = np.trapezoid(dn[m].astype(float), t[m])
    print(f"{a}-{a+3} us: UP {tu/3e-6*100:5.1f}%  DN {td/3e-6*100:5.1f}%  vctrl {w['v(vctrl)'][m][-1]:.3f}  frf {w['frf'][m][-1]/1e9:.4f}")
def edges(x):
    b = x > 1.65; return t[1:][b[1:] & ~b[:-1]]
er, ev = edges(w["v(ref)"]), edges(w["v(fb)"])
print("ref edges", len(er), er[-4:]); print("fb edges", len(ev), ev[-4:])
for e in ev[-2:]:
    k = np.searchsorted(t, e); print("fb pts", [(f"{t[j]*1e9:.3f}", f"{w['v(fb)'][j]:.2f}") for j in range(k-3, k+3)])
for e in er[-2:]:
    k = np.searchsorted(t, e); print("ref pts", [(f"{t[j]*1e9:.3f}", f"{w['v(ref)'][j]:.2f}") for j in range(k-3, k+3)])
du = edges(up.astype(float)*3.3); dd = edges(dn.astype(float)*3.3)
print("UP rising", len(du), du[-6:]); print("DN rising", len(dd), dd[-6:])
