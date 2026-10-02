"""Builds the fine-tuning datasets for `train/finetune.py --task choice` (typed decisions) from calib/dataset.jsonl.

Each row = one screen with the 6 yes/no questions we use in production + the abstract 5-way `next5` choice, gold labels from the
hand-written labels. Split: 2 folds GROUPED BY TASK (the same task never appears in train and test: "Install 7-Zip" shows up in many
cases and would otherwise leak).  usage: python calib/ft_build.py -> runs/ft/fold{0,1}/data/all/{train,test}-0.parquet, runs/ft/folds.json
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "python")); sys.path.insert(0, str(HERE))
from clm_router import policy  # noqa: E402
from eval_next import C1, INSTR  # noqa: E402
from evaluate import load, to_req  # noqa: E402

Q = policy.computer_use_questions()
QUESTIONS = {k: Q[k] for k in ("risky", "stuck", "done", "unexpected", "small_failure", "last_action_ok")}
QUESTIONS["next5"] = {"type": "choice", "instructions": INSTR, "criteria": C1}


def gold(r):
    return {
        "risky": bool(r["risky"]), "stuck": bool(r["stuck"]), "done": r["next"] == "done",
        "unexpected": r["next"] == "replan" and not r["stuck"], "small_failure": r["next"] == "retry",
        "last_action_ok": bool(r["last_ok"]), "next5": r["next"],
    }


def row(r):
    state = policy.computer_use_state(to_req(r, False))
    return {"id": r["id"], "workflow": "all", "state": state, "questions": json.dumps(QUESTIONS, ensure_ascii=False),
            "gold": json.dumps({k: {"label": v} for k, v in gold(r).items()}, ensure_ascii=False)}


def main():
    rows = load()
    by_task = defaultdict(list)
    for r in rows:
        by_task[r["task"]].append(r)
    fold_of, size = {}, [0, 0]
    for task, rs in sorted(by_task.items(), key=lambda kv: -len(kv[1])):    # biggest groups first, to the emptier fold
        k = 0 if size[0] <= size[1] else 1
        fold_of[task] = k; size[k] += len(rs)
    print("tasks:", len(by_task), "| fold sizes:", size)
    folds = {}
    for k in (0, 1):
        test = [row(r) for r in rows if fold_of[r["task"]] == k]
        train = [row(r) for r in rows if fold_of[r["task"]] != k]
        out = ROOT / "runs" / "ft" / f"fold{k}" / "data" / "all"
        out.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(train), out / "train-0.parquet")
        pq.write_table(pa.Table.from_pylist(test), out / "test-0.parquet")
        folds[k] = {"train": [x["id"] for x in train], "test": [x["id"] for x in test]}
        print(f"fold{k}: train {len(train)} rows, test {len(test)} rows  -> {out}")
    (ROOT / "runs" / "ft" / "folds.json").write_text(json.dumps(folds), encoding="utf-8")


if __name__ == "__main__":
    main()
