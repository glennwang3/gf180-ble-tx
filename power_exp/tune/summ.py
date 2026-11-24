"""Summarise harden_result.json files: python3 summ.py <run dirs...>"""
import json, sys
from pathlib import Path
C = ["tt_025C_3v30", "ss_125C_3v00", "ff_n40C_3v60"]
for d in sys.argv[1:]:
    p = Path(d) / "harden_result.json"
    if not p.exists():
        print(f"{d:40s} (no result)"); continue
    r = json.loads(p.read_text()); m = r.get("signoff_metrics") or {}
    if not r["ok"] or not m:
        print(f"{d:40s} FAIL {r['error'][:90]!r}"); continue
    g = lambda k: m.get(k, float("nan"))
    sl = "/".join(str(int(max(g(f"design__max_slew_violation__count__corner:{x}_{c}") for x in ("nom","min","max")))) for c in C)
    cap = int(g("design__max_cap_violation__count")); fo = int(g("design__max_fanout_violation__count"))
    print(f"{d:40s} cell {g('design__instance__area__stdcell'):8.0f} util {g('design__instance__utilization'):.3f} slew {sl:9s} cap {cap} fo {fo} "
          f"hold {g('timing__hold__ws'):+.3f} setup {g('timing__setup__ws'):6.1f} drc {int(g('magic__drc_error__count'))} lvs {int(g('design__lvs_error__count'))} ant {int(g('antenna__violating__nets'))} xor {int(g('design__xor_difference__count'))} eco {int(g('eco__passes'))}/{int(g('eco__upsized_cells'))} {r['seconds']:.0f}s")
