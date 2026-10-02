"""End-to-end check: run every labelled case through the PRODUCTION code path (router + policy) on the real CLM
and compare the resulting flags with the labels.   usage: python calib/check_prod.py"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
from clm_router import policy  # noqa: E402
from clm_router.client import CLM  # noqa: E402
from evaluate import load, to_req  # noqa: E402


def main():
    rows, clm, out = load(), CLM(), {}
    for with_change in (True, False):
        flags = {"risky": [], "stuck": []}
        acts = []
        for r in rows:
            req = to_req(r, with_change)
            ans = clm.system_one(policy.computer_use_state(req), policy.computer_use_questions())
            d = policy.decide_computer_use(ans, req)
            acts.append(d.action)
            flags["risky"].append(any(x.startswith("risky") for x in d.reasons) or ans["risky"]["noul"] >= policy.RISKY_T)
            flags["stuck"].append(policy.loop_signal(r["history"], policy.current_change(req)) or ans["stuck"]["noul"] >= policy.STUCK_T)
        from eval_next import CLASSES, macro_f1  # noqa: E402
        y = [r["next"] for r in rows]
        print(f"== change signal {'present' if with_change else 'absent'}")
        print(f"  next (production decision): accuracy={sum(a == b for a, b in zip(y, acts)) / len(y):.2f} "
              f"macro-F1={macro_f1(y, acts):.2f}  per-class correct: "
              + str({c: f"{sum(a == b == c for a, b in zip(y, acts))}/{y.count(c)}" for c in CLASSES}))
        for t in ("risky", "stuck"):
            y = [r[t] for r in rows]; p = flags[t]
            tp = sum(a and b for a, b in zip(p, y)); fp = sum(a and not b for a, b in zip(p, y)); fn = sum(b and not a for a, b in zip(p, y))
            print(f"  {t}: precision={tp/max(1,tp+fp):.2f} recall={tp/max(1,tp+fn):.2f}  TP/FP/FN={tp}/{fp}/{fn}"
                  f"  FP={[r['id'] for r, a in zip(rows, p) if a and not r[t]]}  FN={[r['id'] for r, a in zip(rows, p) if not a and r[t]]}")


main()
