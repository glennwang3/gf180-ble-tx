"""How the figure of merit grows as a search spends its flow runs.

    python tools/plot_progress.py WORK [WORK ...] -o progress.png [--label NAME ...]

For each run, two lines against the number of flow runs used (the baseline is
run 1, every branch and every signoff is one more):

  solid    the best score signed off so far that passes the limits: what the
           search would hand in if it stopped there. It starts at 1.0, the
           baseline, LibreLane's flow as shipped, and only moves at a signoff.
  dashed   the best estimated score among candidates, with the corrections the
           search had at that moment: what it believed then.

Dots mark evaluations: hollow if the result broke a limit, filled otherwise. Compare runs only
when they were made under the same weights; the title says which.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]


def timeline(work: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pd import names
    rep = names.load_report(work / "report.json")       # old agent names read as new
    tree = json.loads((work / "tree.json").read_text())
    total = rep["cost"]["flow_runs"]
    checks = {a["after_flow_runs"]: a for a in rep["evaluations"] if "seconds" in a}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from export_trials import believed as believed_then
    then = believed_then(work)
    believed, real, dots = [], [], []
    best_real = 1.0
    for k in range(1, total + 1):
        if k in checks:
            a = checks[k]
            s = (a.get("signoff") or {}).get("score")
            # a dot is hollow only when the result broke a limit or the flow failed
            ok = s is not None and not a["outcome"].startswith("failed") \
                and "flow failed" not in a["outcome"]
            if ok:
                best_real = max(best_real, s)
            if s is not None:
                dots.append((k, s, ok))
        believed.append(then[k - 1])
        real.append(best_real)
    return {"rep": rep, "believed": believed, "real": real, "dots": dots}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("work", nargs="+")
    p.add_argument("-o", "--out", default="progress.png")
    p.add_argument("--label", action="append", default=[])
    p.add_argument("--no-estimate", action="store_true",
                   help="leave out the dashed lines, for a figure with many runs")
    p.add_argument("--title", default=None)
    a = p.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid = "#0b0b0b", "#52514e", "#e4e3df"
    fig, ax = plt.subplots(figsize=(8.5, 5.8), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    weights, longest = set(), 1
    for i, w in enumerate(a.work):
        t = timeline(Path(w))
        rep, c = t["rep"], COLORS[i % len(COLORS)]
        weights.add(json.dumps(rep["score"]["weights"], sort_keys=True))
        name = a.label[i] if i < len(a.label) else (rep.get("method") or Path(w).name)
        xs = list(range(1, len(t["real"]) + 1))
        longest = max(longest, len(xs))
        ax.step(xs, t["real"], where="post", color=c, lw=2,
                label=f"{name}: best signed off ({t['real'][-1]:.3f})")
        if not a.no_estimate:
            ax.step(xs, t["believed"], where="post", color=c, lw=1.2, ls=(0, (4, 3)), alpha=0.8,
                    label=f"{name}: best estimate")
        for k, s, ok in t["dots"]:
            ax.plot([k], [s], "o", ms=8, mfc=c if ok else "#fcfcfb", mec="#fcfcfb" if ok else c,
                    mew=2 if ok else 1.5, zorder=3)
        ax.annotate(f"{t['real'][-1]:.3f}", (xs[-1], t["real"][-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", color=ink, fontsize=9)
    ax.axhline(1.0, color=muted, lw=1, ls=":",
               label="baseline: each design's LibreLane default flow = 1.0")
    w = json.loads(weights.pop()) if len(weights) == 1 else None
    ax.set_title((a.title or "Figure of merit against flow runs spent")
                 + (f"   (weights timing {w['timing']:g} / power {w['power']:g} / area {w['area']:g})"
                    if w else "   (runs made under DIFFERENT weights)"),
                 color=ink, fontsize=11, loc="left")
    ax.set_xlabel("flow runs used (baseline = 1; each branch and each signoff is one)",
                  color=muted, fontsize=9)
    ax.set_ylabel("score (higher is better)", color=muted, fontsize=9)
    step = 1 if longest <= 25 else 5 if longest <= 120 else 10
    ax.set_xticks([1] + list(range(step, longest + 1, step)) if step > 1 else range(1, longest + 1))
    ax.grid(axis="y", color=grid, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(grid)
    ax.tick_params(colors=muted, labelsize=8.5)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2)
    fig.text(0.01, 0.01, "dots: evaluations (hollow = broke a limit). Solid: what the search would hand in "
             "if it stopped there." + ("" if a.no_estimate else " Dashed: what it believed."),
             color=muted, fontsize=7.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(a.out, facecolor=fig.get_facecolor())
    print("wrote", a.out)


if __name__ == "__main__":
    main()
