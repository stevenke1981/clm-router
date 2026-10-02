"""Per-question thresholds (independent F-beta fits, few degrees of freedom) from cached CLM scores, then the full tree.

usage: python calib/eval_final.py   (reads calib/scores_next2.json written by eval_next2.py; no CLM calls)
-> calib/report_final.md, calib/thresholds.json
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
from clm_router import policy  # noqa: E402
from eval_next import CLASSES, confusion, macro_f1  # noqa: E402
from evaluate import auc, best_threshold, load, prf  # noqa: E402

SC = json.load(open(HERE / "scores_next2.json"))["without change signal"]
Q = {  # name -> (score key, label fn, beta)
    "risky": ("risky", lambda r: r["risky"], 2.0),
    "stuck": ("stuck", lambda r: r["stuck"], 1.0),
    "done": ("done:d0_goal", lambda r: int(r["next"] == "done"), 1.0),
    "unexpected": ("replan:p0_unexpected", lambda r: int(r["next"] == "replan" and not r["stuck"]), 1.0),
    "small_failure": ("retry:y0_small", lambda r: int(r["next"] == "retry"), 1.0),
    "failed": ("last_ok", lambda r: 1 - r["last_ok"], 1.0),  # score = 1 - last_ok probability
}


def val(r, name):
    k = Q[name][0]
    v = SC[r["id"]][k]
    return 1 - v if name == "failed" else v


def fit(rows):
    return {n: best_threshold([Q[n][1](r) for r in rows], [val(r, n) for r in rows], Q[n][2]) for n in Q}


def tree(r, t):
    if val(r, "risky") >= t["risky"]:
        return "ask_user"
    if val(r, "done") >= t["done"]:
        return "done"
    if policy.loop_signal(r["history"]) or val(r, "stuck") >= t["stuck"]:
        return "replan"
    if val(r, "unexpected") >= t["unexpected"]:
        return "replan"
    if val(r, "small_failure") >= t["small_failure"] or val(r, "failed") >= t["failed"]:
        return "retry"
    return "continue"


def main():
    rows = load()
    seen = {}
    for r in rows:
        seen[r["next"]] = seen.get(r["next"], -1) + 1
        r["split"] = "dev" if seen[r["next"]] % 2 == 0 else "test"
    y = [r["next"] for r in rows]
    cv = {}
    for a, b in (("dev", "test"), ("test", "dev")):
        t = fit([r for r in rows if r["split"] == a])
        for r in rows:
            if r["split"] == b:
                cv[r["id"]] = tree(r, t)
    cvp = [cv[r["id"]] for r in rows]
    t_all = fit(rows)
    ins = [tree(r, t_all) for r in rows]
    acc = lambda p: sum(a == b for a, b in zip(y, p)) / len(y)
    md = ["# Final calibration (per-question thresholds)", "",
          f"CV (2-fold): accuracy {acc(cvp):.2f}, macro-F1 {macro_f1(y, cvp):.2f}   |   in-sample: accuracy {acc(ins):.2f}, macro-F1 {macro_f1(y, ins):.2f}", "",
          "| question | AUC | threshold (all data) | precision | recall |", "|---|---|---|---|---|"]
    for n in Q:
        yy = [Q[n][1](r) for r in rows]; ss = [val(r, n) for r in rows]
        m = prf(yy, ss, t_all[n], Q[n][2])
        md.append(f"| {n} | {auc(yy, ss):.3f} | {t_all[n]:.2f} | {m['precision']:.2f} | {m['recall']:.2f} |")
    md += ["", "Confusion matrix (in-sample):", ""] + confusion(y, ins) + ["", "Confusion matrix (CV):", ""] + confusion(y, cvp)
    text = chr(10).join(md)
    (HERE / "report_final.md").write_text(text, encoding="utf-8")
    json.dump({k: round(v, 3) for k, v in t_all.items()}, open(HERE / "thresholds.json", "w"), indent=1)
    print(text)


if __name__ == "__main__":
    main()
