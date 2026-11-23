import numpy as np
from size import loop
# SS/125 actual: Icp 2.09 uA (bias3), Rz 489 kOhm (res_ss, 125 C), Kv 70.4 MHz/V, regulator pole 39 kHz
for lbl, icp, R, kv, fr in (("SS/125 (Icp 2.09u, Rz 489k, pole 39k)", 2.09e-6, 489e3, 70.4e6, 39e3),
                            ("TT/27  (Icp 2.50u, Rz 439k, pole 84k)", 2.50e-6, 439e3, 70.4e6, 84e3)):
    fc, pm = loop(icp, R, 1.29e-12, kv, fr)
    print(f"{lbl}: fc {fc:.1f} kHz, PM {pm:.1f} deg")
