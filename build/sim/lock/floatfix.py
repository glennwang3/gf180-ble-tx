#!/usr/bin/env python3
"""Find the floating pieces of an extracted subckt (node groups joined only by R / C, with no device terminal and no
port) and write a copy that ties each group to VSS through 1 Tohm.
    python3 floatfix.py IN.spice OUT.spice SUBCKT"""
import re
import sys

src, dst, name = sys.argv[1:4]
txt = open(src).read()
body = re.sub(r"\n\+", " ", txt)
m = re.search(rf"^\.subckt {name} (.*)$", body, re.M)
ports = set(m.group(1).split())
start = body.index(m.group(0))
end = body.index(".ends", start)
lines = body[start:end].splitlines()[1:]
parent = {}


def find(a):
    while parent.setdefault(a, a) != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


anchored = set()
for l in lines:
    t = l.split()
    if not t:
        continue
    k = t[0][0].upper()
    if k == "R":
        parent[find(t[1])] = find(t[2])
    elif k == "C":
        find(t[1]); find(t[2])
    elif k in "XMDQ":
        nn = [x for x in t[1:] if "=" not in x][:-1]          # terminals (last token = model / subckt)
        for x in nn:
            anchored.add(x)
groups = {}
for n in list(parent):
    groups.setdefault(find(n), set()).add(n)
ok = {find(n) for n in anchored | ports if n in parent or n in anchored}
floating = [sorted(g)[0] for r, g in groups.items() if r not in ok and not (g & (anchored | ports))]
print(f"{len(floating)} floating groups:", floating[:12], "..." if len(floating) > 12 else "")
vss = "VSS" if "VSS" in ports else sorted(ports)[0]
add = "".join(f"Rfloat{i} {n} {vss} 1e12\n" for i, n in enumerate(floating))
out = txt.replace(".ends", add + ".ends", 1) if txt.count(".ends") == 1 else txt[:txt.index(".ends", txt.index(m.group(0)))] + add + txt[txt.index(".ends", txt.index(m.group(0))):]
open(dst, "w").write(out)
