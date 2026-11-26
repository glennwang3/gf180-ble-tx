#!/bin/bash
# Reference cycles (1 us bins) where DN or UP is on for > 100 ns in a closed-loop tx run (wrdata out.txt:
# t vctrl t vdd_vco t frf t vtune t dn t upb).   bash slips.sh CASE/out.txt [T_from_us]
awk -v T0="${2:-0}" '
NR > 0 && NF >= 12 {
  t = $1; b = int(t * 1e6);
  if (NR > 1 && pb == b) { dt = t - pt; if (pdn > 1.65) dn[b] += dt; if (pup < 1.65) up[b] += dt }
  pt = t; pb = b; pdn = $10; pup = $12; f[b] = $6; last = b
}
END {
  n = 0
  for (k = T0; k <= last; k++) if (dn[k] > 1e-7 || up[k] > 1e-7) {
    printf "  %4d us: DN %7.1f ns  UP %7.1f ns  f_RF %.4f GHz\n", k, dn[k] * 1e9, up[k] * 1e9, f[k] / 1e9; n++ }
  printf "cycles with DN or UP > 100 ns after %d us: %d of %d\n", T0, n, last - T0 + 1
}' "$1"
