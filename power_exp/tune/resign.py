"""Re-run signoff (with the fix passes) from a harden run's stored END state and keep
every run directory: python3 resign.py <variant dir> <run name> <out name>"""
import json, os, sys
from pathlib import Path
os.environ.setdefault("PD_NO_FIX_BUFFER", "")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "digital" / "agent"))
from pd import runner  # noqa: E402
v, run, out = Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3]
r = json.loads((v / run / "harden_result.json").read_text())
end = v / run / "store" / "END" / "state.json"
ov = dict(r["overrides"]); ov.update(json.loads(os.environ.get("OV", "{}")))
(v / out).mkdir(exist_ok=True)
so = runner.signoff(v, str(end), ov, v / out / "signoff", keep=os.environ.get("KEEP", "final"))
(v / out / "harden_result.json").write_text(json.dumps(
    {"ok": so.ok, "seconds": so.seconds, "error": so.error, "overrides": ov,
     "metrics": {}, "signoff_metrics": so.signoff_metrics, "log_tail": so.log_tail},
    indent=1, default=str))
print(so.ok, so.error[:500])
print(json.dumps(so.signoff_metrics, indent=1, default=str)[:3000])
