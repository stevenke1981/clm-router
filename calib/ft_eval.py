"""Zero-shot reference head vs the heads fine-tuned on the OTHER fold (so every row is scored out-of-fold).

usage: python calib/ft_eval.py   (needs the llama.cpp embedder on :8090 and runs/ft/fold{0,1}/out/best_head.pt)
-> calib/report_ft.md, calib/scores_ft_zero.json, calib/scores_ft_tuned.json  (same layout as scores_next2.json, for eval_final.py)
"""
import json
import os
import sys
from pathlib import Path

import pyarrow.parquet as pq

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python")); sys.path.insert(0, str(HERE))
from clm import Engine  # noqa: E402
from clm.embedder import Embedder  # noqa: E402
from eval_next import CLASSES, macro_f1  # noqa: E402
from evaluate import auc, load  # noqa: E402

REF = os.path.join(os.path.expanduser("~"), ".cache", "clm", "CLM_v0.1-8B.pt")
KEYMAP = {"risky": "risky", "stuck": "stuck", "done": "done:d0_goal", "unexpected": "replan:p0_unexpected", "small_failure": "retry:y0_small", "last_action_ok": "last_ok"}
GOLD = {"risky": lambda r: r["risky"], "stuck": lambda r: r["stuck"], "done": lambda r: int(r["next"] == "done"),
        "unexpected": lambda r: int(r["next"] == "replan" and not r["stuck"]), "small_failure": lambda r: int(r["next"] == "retry"),
        "last_action_ok": lambda r: r["last_ok"]}


def main():
    rows = {r["id"]: r for r in load()}
    emb = Embedder("http://127.0.0.1:8090/v1/embeddings", "qwen3-8b", max_tokens=2048)
    zero = Engine(embedder=emb, checkpoint=REF, device="cpu")
    out = {"zero": {}, "tuned": {}}
    next5 = {"zero": {}, "tuned": {}}
    for k in (0, 1):
        tuned = Engine(embedder=emb, checkpoint=str(ROOT / "runs" / "ft" / f"fold{k}" / "out" / "best_head.pt"), device="cpu")
        for t in pq.read_table(ROOT / "runs" / "ft" / f"fold{k}" / "data" / "all" / "test-0.parquet").to_pylist():
            qs = json.loads(t["questions"])
            for name, eng in (("zero", zero), ("tuned", tuned)):
                ans = eng.answer(t["state"], qs)["answers"]
                out[name][t["id"]] = {KEYMAP[q]: ans[q]["noul"] for q in KEYMAP}
                next5[name][t["id"]] = ans["next5"]["probabilities"]
        print("fold", k, "scored", flush=True)
    for name in out:
        (HERE / f"scores_ft_{name}.json").write_text(json.dumps({"without change signal": out[name]}), encoding="utf-8")

    ids = list(rows)
    md = ["# Zero-shot vs fine-tuned heads (out-of-fold)", "",
          "Heads fine-tuned on 52 rows (about 360 questions) of the other fold, scored on the 52 unseen rows; both folds pooled = 104 out-of-fold rows. "
          "Folds are grouped by task. Labels are the assistant's own.", "", "| question | zero-shot AUC | fine-tuned AUC |", "|---|---|---|"]
    for q in KEYMAP:
        y = [GOLD[q](rows[i]) for i in ids]
        md.append(f"| {q} | {auc(y, [out['zero'][i][KEYMAP[q]] for i in ids]):.3f} | {auc(y, [out['tuned'][i][KEYMAP[q]] for i in ids]):.3f} |")
    yn = [rows[i]["next"] for i in ids]
    md += ["", "| 5-way `next5` (abstract options) | accuracy | macro-F1 |", "|---|---|---|"]
    for name in ("zero", "tuned"):
        pred = [max(CLASSES, key=lambda c: next5[name][i].get(c, 0)) for i in ids]
        md.append(f"| {name} | {sum(a == b for a, b in zip(yn, pred)) / len(yn):.2f} | {macro_f1(yn, pred):.2f} |")
    text = chr(10).join(md)
    (HERE / "report_ft.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
