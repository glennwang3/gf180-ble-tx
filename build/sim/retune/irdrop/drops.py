import re, sys
PEX = "/foss/designs/pll_compact/layout/pex_loop/LOOP_PART_rcpex.spice"
RES = "/foss/designs/pll_compact/layout/pex_loop/LOOP_PART.res.ext"
v = {}
for l in open("nodes.txt"):
    m = re.match(r"\s*(\S+)\s*=\s*(\S+)", l)
    if m:
        try: v[m.group(1).lower()] = float(m.group(2))
        except ValueError: pass
xy = {}
for l in open(RES):
    p = l.split()
    if p and p[0] == "rnode":
        xy[p[1].strip('"').lower()] = (int(p[4]) / 100.0, int(p[5]) / 100.0)   # um
rs = []
for l in open(PEX):
    p = l.split()
    if p and p[0].startswith("R") and len(p) >= 4:
        a, b = p[1].lower(), p[2].lower()
        if a.split(".")[0] == "vdd" and a in v and b in v:
            r = float(p[3]); dv = v[a] - v[b]
            rs.append((abs(dv), r, abs(dv) / r * 1e3, a, b))
rs.sort(reverse=True)
print("biggest VDD drops: dV[mV]  R[ohm]  I[mA]  nodes (xy raw)")
for dv, r, i, a, b in rs[:25]:
    print(f"{dv*1e3:7.2f} {r:8.2f} {i:6.3f}  {a}{xy.get(a,'')} -> {b}{xy.get(b,'')}")
print("total R in VDD net:", sum(x[1] for x in rs), " resistors:", len(rs))
