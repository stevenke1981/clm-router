"""Attack-surface reduction: does sending only structural UI elements keep accuracy and resist prompt injection?

usage: python calib/eval_surface.py (needs clm-serve) -> calib/report_surface.md, calib/scores_surface.json
Screens are the 104 dataset cases converted to UI-Automation-style dumps (calib/uia_states.py, an approximation of real dumps).
Modes: full | ui | ui+text (python/clm_router/compact.py).  Injection sentences are placed as a Text paragraph, a link label, or a button label.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
from clm_router import policy  # noqa: E402
from clm_router.client import CLM  # noqa: E402
from clm_router.compact import compact  # noqa: E402
from eval_inject import INJECT  # noqa: E402
from eval_jev import LABEL  # noqa: E402
from evaluate import auc, best_threshold, load, prf, to_req  # noqa: E402
from uia_states import inject_into, to_uia  # noqa: E402

MODES = ("full", "ui", "ui+text")
QS = policy.computer_use_questions()
TARGETS = {"risky": "risky", "stuck": "stuck", "done": "done", "unexpected": "unexpected", "small_failure": "small_failure", "failed": "last_action_ok"}
SENT = {k: INJECT[k] for k in ("direct", "screenreader", "para2")}


def state_for(r, mode, text):
    req = to_req(r, False)
    req["observation"]["text"] = text          # raw UIA-style dump; the mode is applied inside policy.computer_use_state
    return policy.computer_use_state(req, mode)


def main():
    rows, clm = load(), CLM()
    seen = {}
    for r in rows:
        seen[r["next"]] = seen.get(r["next"], -1) + 1
        r["split"] = "dev" if seen[r["next"]] % 2 == 0 else "test"
    S = {}
    for mode in MODES:
        sc = {}
        for r in rows:
            ans = clm.system_one(state_for(r, mode, to_uia(r)), {k: QS[q] for k, q in TARGETS.items()})
            sc[r["id"]] = {k: (1 - ans[k]["noul"]) if k == "failed" else ans[k]["noul"] for k in TARGETS}
        S[mode] = {"clean": sc, "chars": sum(len(compact(to_uia(r), mode)) for r in rows) / len(rows)}
        print("clean done", mode, flush=True)
    pos = [r for r in rows if r["risky"]]
    for mode in MODES:
        S[mode]["inj"] = {}
        for where in ("text", "link", "button"):
            for name, sentence in SENT.items():
                S[mode]["inj"][f"{where}/{name}"] = {r["id"]: clm.system_one(state_for(r, mode, inject_into(to_uia(r), sentence, where)), {"risky": QS["risky"]})["risky"]["noul"] for r in pos}
        print("inject done", mode, flush=True)
    (HERE / "scores_surface.json").write_text(json.dumps(S), encoding="utf-8")

    md = ["# Attack-surface reduction", "", f"{len(rows)} screens as UIA-style dumps; mean state size: " + ", ".join(f"{m} {S[m]['chars']:.0f} chars" for m in MODES), "",
          "## clean accuracy (pooled AUC per question; risky also 2-fold CV precision/recall at its own best threshold)", "",
          "| mode | " + " | ".join(TARGETS) + " | risky CV P | risky CV R |", "|---|" + "---|" * (len(TARGETS) + 2)]
    for mode in MODES:
        sc = S[mode]["clean"]
        aucs = [f"{auc([LABEL[k](r) for r in rows], [sc[r['id']][k] for r in rows]):.3f}" for k in TARGETS]
        tp = fp = fn = 0
        for a, b in (("dev", "test"), ("test", "dev")):
            tr = [r for r in rows if r["split"] == a]; te = [r for r in rows if r["split"] == b]
            thr = best_threshold([r["risky"] for r in tr], [sc[r["id"]]["risky"] for r in tr], 2.0)
            m = prf([r["risky"] for r in te], [sc[r["id"]]["risky"] for r in te], thr, 2.0)
            tp, fp, fn = tp + m["tp"], fp + m["fp"], fn + m["fn"]
        md.append(f"| {mode} | " + " | ".join(aucs) + f" | {tp / max(1, tp + fp):.2f} | {tp / max(1, tp + fn):.2f} |")
    md += ["", f"## injection: risky screens still flagged (risky >= {policy.RISKY_T}); clean = no injected text", "",
           "| mode | clean | " + " | ".join(f"{w} (worst of 3)" for w in ("text", "link", "button")) + " |", "|---|---|---|---|---|"]
    for mode in MODES:
        clean = sum(S[mode]["clean"][r["id"]]["risky"] >= policy.RISKY_T for r in pos)
        cols = []
        for w in ("text", "link", "button"):
            cols.append(f"{min(sum(v >= policy.RISKY_T for v in S[mode]['inj'][f'{w}/{n}'].values()) for n in SENT)}/{len(pos)}")
        md.append(f"| {mode} | {clean}/{len(pos)} | " + " | ".join(cols) + " |")
    text = chr(10).join(md)
    (HERE / "report_surface.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
