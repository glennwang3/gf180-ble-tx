"""Q rise / fall transition of gf180mcu_fd_sc_mcu7t5v0__dffrnq_1 vs load, from the 3.3 V liberty files."""
import re
for corner in ("tt_025C_3v30", "ss_125C_3v00" , "ss_125C_3v30"):
    p = f"/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__{corner}.lib"
    try:
        txt = open(p).read()
    except FileNotFoundError:
        continue
    i = txt.index("cell (\"gf180mcu_fd_sc_mcu7t5v0__dffrnq_1\")") if "cell (\"gf180mcu_fd_sc_mcu7t5v0__dffrnq_1\")" in txt else txt.index("cell (gf180mcu_fd_sc_mcu7t5v0__dffrnq_1)")
    j = txt.index("\n  cell", i + 10)
    c = txt[i:j]
    q = c[c.index('pin ("Q")') if 'pin ("Q")' in c else c.index("pin (Q)"):]
    unit = re.search(r"capacitive_load_unit\s*\(([^)]*)\)", txt).group(1)
    tu = re.search(r'time_unit\s*:\s*"([^"]*)"', txt).group(1)
    print(f"== {corner}  (cap unit {unit}, time unit {tu})")
    for kind in ("rise_transition", "fall_transition"):
        k = q.index(kind)
        blk = q[k:q.index("}", k)]
        idx1 = re.search(r'index_1\s*\(\s*"([^"]*)"', blk).group(1)
        idx2 = re.search(r'index_2\s*\(\s*"([^"]*)"', blk).group(1)
        vals = re.search(r'values\s*\((.*?)\)\s*;', blk, re.S).group(1)
        rows = [r.strip().strip('"').strip("\\").strip().strip('"') for r in vals.split('",')]
        print(f"  {kind}: index_1 (input slew) {idx1}")
        print(f"     index_2 (load)       {idx2}")
        print(f"     first rows: {rows[0]} | {rows[1] if len(rows) > 1 else ''}")
