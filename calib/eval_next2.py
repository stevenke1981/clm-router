"""Replaces the 5-way `next` choice by independent yes/no questions + a decision tree; thresholds by CV.

usage: python calib/eval_next2.py   (needs clm-serve) -> calib/report_next2.md
tree: risky -> ask_user ; done -> done ; loop/stuck -> replan ; unexpected -> replan ; small-failure -> retry ; else continue
"""
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
from clm_router import policy  # noqa: E402
from clm_router.client import CLM  # noqa: E402
from eval_next import CLASSES, confusion, macro_f1  # noqa: E402
from evaluate import auc, load, to_req  # noqa: E402

Q = {  # target -> {variant: question}
    "done": {
        "d0_goal": "Is the task's goal already accomplished and visible on screen, so nothing more needs to be done?",
        "d1_result": "Does the current screen show the final result that the task asked for?",
    },
    "replan": {
        "p0_unexpected": "Does the screen show something the plan did not expect (an error page, a missing file or package, "
                         "the wrong application, an unavailable feature), so that a different approach is needed?",
        "p1_wont_fix": "Is the current approach failing for a reason that simply repeating the step will not fix?",
    },
    "retry": {
        "y0_small": "Did the last step fail in a small, fixable way (a typo, a mis-click, text typed in the wrong field, "
                    "nothing happened), so that repeating it with a correction would work?",
    },
}
LABEL = {"done": "done", "replan": "replan", "retry": "retry"}


def all_questions():
    qs = {f"{t}:{n}": {"type": "noul", "instructions": q} for t, d in Q.items() for n, q in d.items()}
    base = policy.computer_use_questions()
    qs["risky"], qs["stuck"], qs["last_ok"] = base["risky"], base["stuck"], base["last_action_ok"]
    return qs


def score(rows, clm, with_change):
    qs, out = all_questions(), {}
    for r in rows:
        ans = clm.system_one(policy.computer_use_state(to_req(r, with_change)), qs)
        out[r["id"]] = {k: ans[k]["noul"] for k in qs}
    return out


def tree(r, e, pick, th):
    if e["risky"] >= policy.RISKY_T:
        return "ask_user"
    if e[pick["done"]] >= th["done"]:
        return "done"
    if policy.loop_signal(r["history"]) or e["stuck"] >= policy.STUCK_T:
        return "replan"
    if e[pick["replan"]] >= th["replan"]:
        return "replan"
    if e[pick["retry"]] >= th["retry"] or e["last_ok"] < th["ok"]:
        return "retry"
    return "continue"


GRID = {"done": (0.3, 0.5, 0.7, 0.85), "replan": (0.3, 0.5, 0.7, 0.85), "retry": (0.3, 0.5, 0.7, 0.85), "ok": (0.2, 0.36, 0.5)}


def fit(rows, sc, pick):
    y = [r["next"] for r in rows]
    best, bt = -1, None
    for combo in itertools.product(*GRID.values()):
        th = dict(zip(GRID, combo))
        f = macro_f1(y, [tree(r, sc[r["id"]], pick, th) for r in rows])
        acc = sum(a == tree(r, sc[r["id"]], pick, th) for a, r in zip(y, rows)) / len(rows)
        if (f, acc) > (best, 0):
            best, bt = f, th
    return bt


def main():
    rows, clm = load(), CLM()
    seen = {}
    for r in rows:
        seen[r["next"]] = seen.get(r["next"], -1) + 1
        r["split"] = "dev" if seen[r["next"]] % 2 == 0 else "test"
    y = [r["next"] for r in rows]
    md = ["# `next` as yes/no questions + decision tree", ""]
    out = {}
    for mode, wc in (("without change signal", False), ("with change signal", True)):
        sc = score(rows, clm, wc); out[mode] = sc
        md += [f"## {mode}", "", "AUC of each yes/no question against its label (positive vs all other cases):", "",
               "| question | AUC |", "|---|---|"]
        for t, d in Q.items():
            for n in d:
                md.append(f"| {t}:{n} | {auc([int(r['next'] == LABEL[t]) for r in rows], [sc[r['id']][f'{t}:{n}'] for r in rows]):.3f} |")
        md.append("")
        md += ["| picked variants | CV acc | CV macro-F1 | in-sample acc | in-sample macro-F1 | thresholds (all data) |", "|---|---|---|---|---|---|"]
        results = []
        for pd, pp, py in itertools.product(Q["done"], Q["replan"], Q["retry"]):
            pick = {"done": f"done:{pd}", "replan": f"replan:{pp}", "retry": f"retry:{py}"}
            cv = {}
            for a, b in (("dev", "test"), ("test", "dev")):
                th = fit([r for r in rows if r["split"] == a], sc, pick)
                for r in rows:
                    if r["split"] == b:
                        cv[r["id"]] = tree(r, sc[r["id"]], pick, th)
            cvp = [cv[r["id"]] for r in rows]
            th_all = fit(rows, sc, pick)
            ins = [tree(r, sc[r["id"]], pick, th_all) for r in rows]
            acc = lambda p: sum(a == b for a, b in zip(y, p)) / len(y)
            results.append((macro_f1(y, cvp), acc(cvp), pick, th_all, ins, acc(ins)))
            md.append(f"| {pd} / {pp} / {py} | {acc(cvp):.2f} | {macro_f1(y, cvp):.2f} | {acc(ins):.2f} | {macro_f1(y, ins):.2f} | {json.dumps(th_all)} |")
        results.sort(key=lambda t: t[:2], reverse=True)
        f, a, pick, th, ins, ia = results[0]
        md += ["", f"Best by CV macro-F1: {pick} thresholds {th}", "", "Confusion matrix (in-sample):", ""] + confusion(y, ins) + [""]
    (HERE / "scores_next2.json").write_text(json.dumps(out), encoding="utf-8")
    text = chr(10).join(md)
    (HERE / "report_next2.md").write_text(text, encoding="utf-8")
    print(text)


main()
