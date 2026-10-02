"""CLM uses last-token pooling, so the END of the state text matters. Compare constant closing lines.

usage: python calib/eval_suffix.py (needs clm-serve) -> calib/report_suffix.md
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
from clm_router import policy  # noqa: E402
from clm_router.client import CLM  # noqa: E402
from eval_next import CLASSES, macro_f1  # noqa: E402
from evaluate import auc, load, to_req  # noqa: E402

SUFFIX = {
    "none": "",
    "unknown_line": "\nScreen change since last step: unknown",
    "task_question": "\nQuestion: assess the current state of this computer-use task.",
    "end_marker": "\n--- end of observation ---",
    "task_restated": None,  # filled per case: repeat the task at the end
}


def state_for(r, name):
    base = policy.computer_use_state(to_req(r, False)).removesuffix(policy.STATE_SUFFIX).rstrip()
    if name == "task_restated":
        return base + f"\nReminder - the task is: {r['task']}"
    return base + SUFFIX[name]


def main():
    rows, clm, qs = load(), CLM(), policy.computer_use_questions()
    y = {k: [r[k] for r in rows] for k in ("risky", "stuck")}
    ydone = [int(r["next"] == "done") for r in rows]
    yok = [r["last_ok"] for r in rows]
    md = ["# Closing-line (suffix) sensitivity", "", "| suffix | risky AUC | stuck AUC | done AUC | last_ok AUC | decision accuracy | macro-F1 |", "|---|---|---|---|---|---|---|"]
    for name in SUFFIX:
        ans = [clm.system_one(state_for(r, name), qs) for r in rows]
        acts = []
        for r, a in zip(rows, ans):
            acts.append(policy.decide_computer_use(a, {"history": r["history"], "observation": {"change": "unknown"}}).action)
        p = lambda k: [a[k]["noul"] for a in ans]
        yn = [r["next"] for r in rows]
        md.append(f"| {name} | {auc(y['risky'], p('risky')):.3f} | {auc(y['stuck'], p('stuck')):.3f} | "
                  f"{auc(ydone, p('done')):.3f} | {auc(yok, p('last_action_ok')):.3f} | "
                  f"{sum(a == b for a, b in zip(yn, acts)) / len(yn):.2f} | {macro_f1(yn, acts):.2f} |")
        print(md[-1], flush=True)
    text = chr(10).join(md)
    (HERE / "report_suffix.md").write_text(text, encoding="utf-8")


main()
