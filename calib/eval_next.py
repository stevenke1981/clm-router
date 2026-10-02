"""Calibrates the `next` choice question and `last_action_ok` on the real CLM.

usage: python calib/eval_next.py        (needs clm-serve on :8700)   -> calib/report_next.md, calib/scores_next.json
"""
import json
import sys
from itertools import product
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
from clm_router import policy  # noqa: E402
from clm_router.client import CLM  # noqa: E402
from evaluate import auc, best_threshold, load, prf, to_req  # noqa: E402

CLASSES = ["continue", "retry", "replan", "ask_user", "done"]
INSTR = "Given the task, the recent steps and the current screen, which single next step is correct?"

C1 = {
    "continue": "The last step worked and the task is still in progress; carry on with the next planned step",
    "retry": "The last step failed in a small, fixable way (typo, mis-click, wrong field, command not found, "
             "nothing happened); redo that step with a correction",
    "replan": "The screen shows something the plan did not expect (error page, missing file or package, wrong app, "
              "unavailable feature); a different approach is needed",
    "ask_user": "A confirmation, password, payment or permission prompt needs a human decision",
    "done": "The goal of the task is already visible on screen; nothing more to do",
}
C2 = dict(C1, done="The end result the task asked for is already shown on screen (file exists, command finished, "
                   "message sent, setting applied)",
          continue_="")  # placeholder removed below
C2.pop("continue_")
C3 = {  # different order: put the rare classes first
    "done": C2["done"], "retry": C1["retry"], "replan": C1["replan"], "ask_user": C1["ask_user"],
    "continue": "None of the above: the task is progressing normally, so just continue",
}

NEXT = {
    "n0_current": {"type": "choice", "instructions": "What should happen next in this computer-use task?",
                   "criteria": policy.COMPUTER_USE_ACTIONS},
    "n1_contrast": {"type": "choice", "instructions": INSTR, "criteria": C1},
    "n2_done_explicit": {"type": "choice", "instructions": INSTR, "criteria": C2},
    "n3_reordered": {"type": "choice", "instructions": INSTR, "criteria": C3},
}
OK = {  # name -> (question, invert)
    "k0_current": ({"type": "noul", "instructions": "Did the last action achieve its intended effect on screen?"}, False),
    "k1_result": ({"type": "noul", "instructions": "Does the screen now show the result that the last action was meant to produce?"}, False),
    "k2_error": ({"type": "noul", "instructions": "After the last action, is there an error message, a wrong result "
                  "or no visible change at all?"}, True),
    "k3_choice": ({"type": "choice", "instructions": "How did the last action turn out?",
                   "criteria": {"worked": "The last action had the intended effect, even if the task is not finished yet",
                                "failed": "The last action had no effect, a wrong effect, or produced an error"}}, "worked"),
}


def questions():
    qs = {f"next:{k}": v for k, v in NEXT.items()}
    for k, (q, _) in OK.items():
        qs[f"ok:{k}"] = q
    qs["risky"] = policy.computer_use_questions()["risky"]
    qs["stuck"] = policy.computer_use_questions()["stuck"]
    return qs


def score(rows, clm, with_change):
    out = {}
    for r in rows:
        req = to_req(r, with_change)
        ans = clm.system_one(policy.computer_use_state(req), questions())
        e = {"risky": ans["risky"]["noul"], "stuck": ans["stuck"]["noul"]}
        for k in NEXT:
            e[f"next:{k}"] = {c: ans[f"next:{k}"]["probabilities"].get(c, 0.0) for c in CLASSES}
        for k, (_, inv) in OK.items():
            a = ans[f"ok:{k}"]
            v = a["probabilities"]["worked"] if isinstance(inv, str) else a["noul"]
            e[f"ok:{k}"] = 1 - v if inv is True else v
        out[r["id"]] = e
    return out


def macro_f1(y, p):
    fs = []
    for c in CLASSES:
        tp = sum(a == c and b == c for a, b in zip(y, p)); fp = sum(a != c and b == c for a, b in zip(y, p))
        fn = sum(a == c and b != c for a, b in zip(y, p))
        pr = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
        fs.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(fs) / len(fs)


def argmax(d, w=None):
    return max(CLASSES, key=lambda c: d[c] * (w[c] if w else 1.0))


def fit_weights(rows, sc, key):
    """Coordinate ascent on per-class multiplicative weights to maximise macro-F1 (grid, 3 sweeps)."""
    w = {c: 1.0 for c in CLASSES}
    y = [r["next"] for r in rows]
    for _ in range(3):
        for c in CLASSES:
            best = max((0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0),
                       key=lambda g: (macro_f1(y, [argmax(sc[r["id"]][key], {**w, c: g}) for r in rows]), -abs(g - 1)))
            w[c] = best
    return w


def end_to_end(r, e, key, w=None):
    """Same override order as policy.decide_computer_use (risky > loop > continue-but-failed)."""
    action = argmax(e[key], w)
    if e["risky"] >= policy.RISKY_T:
        return "ask_user"
    if (policy.loop_signal(r["history"]) or e["stuck"] >= policy.STUCK_T) and action in ("continue", "retry"):
        return "replan"
    return action


def confusion(y, p):
    lines = ["| true \\ pred | " + " | ".join(CLASSES) + " |", "|---|" + "---|" * len(CLASSES)]
    for t in CLASSES:
        lines.append(f"| {t} | " + " | ".join(str(sum(a == t and b == c for a, b in zip(y, p))) for c in CLASSES) + " |")
    return lines


def main():
    rows, clm = load(), CLM()
    for r in rows:  # (load() splits by risky/stuck only) -> re-split stratified by next label
        pass
    seen = {}
    for r in rows:
        seen[r["next"]] = seen.get(r["next"], -1) + 1
        r["split"] = "dev" if seen[r["next"]] % 2 == 0 else "test"
    md = [f"# next / last_action_ok calibration ({len(rows)} cases)", "",
          "Accuracy/macro-F1 are over all cases (raw = argmax of the choice question). 'e2e' applies the production "
          "overrides (risky > loop > continue-but-failed). 'CV' = per-class weights fitted on one half, scored on the other.", ""]
    allsc = {}
    for mode, wc in (("without change signal", False), ("with change signal", True)):
        sc = score(rows, clm, wc); allsc[mode] = sc
        y = [r["next"] for r in rows]
        md += [f"## {mode}", "", "| variant | raw acc | raw macro-F1 | e2e acc | e2e macro-F1 | CV e2e acc | CV e2e macro-F1 |", "|---|---|---|---|---|---|---|"]
        for k in NEXT:
            key = f"next:{k}"
            raw = [argmax(sc[r["id"]][key]) for r in rows]
            e2e = [end_to_end(r, sc[r["id"]], key) for r in rows]
            cv = {}
            for a, b in (("dev", "test"), ("test", "dev")):
                tr = [r for r in rows if r["split"] == a]; te = [r for r in rows if r["split"] == b]
                w = fit_weights(tr, sc, key)
                for r in te:
                    cv[r["id"]] = end_to_end(r, sc[r["id"]], key, w)
            cvp = [cv[r["id"]] for r in rows]
            acc = lambda p: sum(a == b for a, b in zip(y, p)) / len(y)
            md.append(f"| {k} | {acc(raw):.2f} | {macro_f1(y, raw):.2f} | {acc(e2e):.2f} | {macro_f1(y, e2e):.2f} | {acc(cvp):.2f} | {macro_f1(y, cvp):.2f} |")
        md.append("")
        best_k = max(NEXT, key=lambda k: macro_f1(y, [end_to_end(r, sc[r["id"]], f"next:{k}") for r in rows]))
        e2e = [end_to_end(r, sc[r["id"]], f"next:{best_k}") for r in rows]
        md += [f"Confusion matrix (e2e, {best_k}):", ""] + confusion(y, e2e) + [""]
        md += ["### last_action_ok (label 1 = ok)", "", "| variant | AUC | best-thr | precision(ok) | recall(ok) |", "|---|---|---|---|---|"]
        yo = [r["last_ok"] for r in rows]
        for k in OK:
            s = [sc[r["id"]][f"ok:{k}"] for r in rows]
            t = best_threshold(yo, s, 1.0); m = prf(yo, s, t)
            md.append(f"| {k} | {auc(yo, s):.3f} | {t:.2f} | {m['precision']:.2f} | {m['recall']:.2f} |")
        md.append("")
    (HERE / "scores_next.json").write_text(json.dumps(allsc), encoding="utf-8")
    text = chr(10).join(md)
    (HERE / "report_next.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
