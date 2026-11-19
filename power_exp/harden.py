"""Harden one power_exp variant with the repo's agent flow (pd.runner.baseline:
LibreLane to global routing, then signoff with the upsizing fix passes, power
from the variant's power_tb.v). No cache.

    cd /foss/designs/gf180-ble-tx-power
    python3 power_exp/harden.py power_exp/v0                      # config as is -> v0/run
    python3 power_exp/harden.py power_exp/v0 --width 300 --grt-repair   # -> v0/run_w300g

Signoff fix passes upsize only (PD_NO_FIX_BUFFER=1, see pd/runner.py).
"""
import argparse, json, os, sys, time
from pathlib import Path
os.environ.setdefault("PD_NO_FIX_BUFFER", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digital" / "agent"))

ap = argparse.ArgumentParser()
ap.add_argument("variant")
ap.add_argument("--width", type=float, help="die width in um (height stays 300)")
ap.add_argument("--fix-passes", type=int, help="signoff upsizing passes (default 5)")
ap.add_argument("--grt-repair", action="store_true", help="RUN_POST_GRT_DESIGN_REPAIR")
a = ap.parse_args()

v = Path(a.variant).resolve()
over, tag = {}, "run"
if a.width:
    over["DIE_WIDTH_UM"] = a.width
    tag += f"_w{a.width:g}"
if a.grt_repair:
    over["RUN_POST_GRT_DESIGN_REPAIR"] = "true"
    tag += "g"
if a.fix_passes is not None:
    os.environ["PD_FIX_PASSES"] = str(a.fix_passes)
    tag += f"_f{a.fix_passes}"
run = v / tag
run.mkdir(exist_ok=True)
from pd import runner  # noqa: E402  (after PD_FIX_PASSES is set)
t0 = time.time()
res = runner.baseline(v, run / "baseline", run / "store", overrides=over or None)
out = {"ok": res.ok, "seconds": time.time() - t0, "error": res.error, "overrides": over,
       "metrics": res.metrics, "signoff_metrics": res.signoff_metrics,
       "log_tail": res.log_tail}
(run / "harden_result.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: out[k] for k in ("ok", "seconds", "error", "overrides")}, default=str))
print(json.dumps(res.signoff_metrics, indent=1, default=str))
