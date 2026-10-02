"""Calibrates image review (pass / local_edit / regenerate + which regions) on the real CLM.

usage: python calib/eval_image.py   (needs clm-serve) -> calib/report_image.md, calib/scores_image.json
Split is by brief (the pass/local/regenerate triplets of one brief stay together) to avoid leakage.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
from clm_router import policy  # noqa: E402
from clm_router.client import CLM  # noqa: E402
from evaluate import auc, best_threshold, prf  # noqa: E402

CLS = ["pass", "local_edit", "regenerate"]
SUFFIX = "Question: judge whether this generated image meets the brief."


def load():
    rows = [json.loads(l) for l in open(HERE / "image_dataset.jsonl", encoding="utf-8")]
    for r in rows:
        r["split"] = "dev" if int(r["id"][1:3]) % 2 == 1 else "test"
    return rows


def req_of(r):
    return {"task": r["brief"], "image": {"brief": r["brief"], "criteria": r["criteria"], "description": r["description"],
                                          "regions": r["regions"]}}


def state(r, variant):
    img = req_of(r)["image"]
    regions = "\n".join(f"- [{x['id']}] {x['description']}" for x in img["regions"]) or "- (none)"
    base = (f"Image brief / requirement: {img['brief']}\nMust-have criteria:\n" + "\n".join(f"- {c}" for c in img["criteria"]) +
            f"\nDescription of the produced image: {img['description']}\nPer-region observations:\n{regions}")
    if variant == "A_current":
        return base + "\nMeasured metrics: {}"
    if variant == "B_suffix":
        return base + "\nMeasured metrics: {}\n" + SUFFIX
    return base + "\n" + SUFFIX  # C_clean: no empty metrics line + suffix


V1 = {"pass": "Every must-have criterion is met by the described image and nothing is wrong",
      "local_edit": "Mostly right, but one or two specific regions or elements violate a criterion; fix only those",
      "regenerate": "The image is wrong as a whole (wrong subject, style or layout, or most criteria fail); start over"}


def questions(r):
    qs = {
        "verdict:v0": {"type": "choice", "instructions": "Does this image pass the brief, need a local edit, or need full regeneration?",
                       "criteria": policy.IMAGE_ACTIONS},
        "verdict:v1": {"type": "choice", "instructions": "Compare the described image with the brief and criteria. Which outcome is correct?",
                       "criteria": V1},
        "meets": {"type": "noul", "instructions": "Does the described image meet every must-have criterion?"},
        "global:g0": {"type": "noul", "instructions": "Is the problem global (wrong subject, layout, style, resolution, heavy artifacts) "
                      "rather than confined to a few small regions?"},
        "global:g1": {"type": "noul", "instructions": "Is the image fundamentally wrong (wrong subject, style or layout) "
                      "rather than having a small local flaw?"},
    }
    for x in r["regions"]:
        qs[f"region:r0:{x['id']}"] = {"type": "noul", "instructions": f"Is the region '{x['id']}' defective or inconsistent with the brief?"}
        qs[f"region:r1:{x['id']}"] = {"type": "noul", "instructions": f"Does the description of the region '{x['id']}' violate any "
                                      "must-have criterion or the brief?"}
    return qs


def read(a):
    return a["noul"] if "noul" in a else a["probabilities"]


def macro_f1(y, p):
    fs = []
    for c in CLS:
        tp = sum(a == c and b == c for a, b in zip(y, p)); fp = sum(a != c and b == c for a, b in zip(y, p))
        fn = sum(a == c and b != c for a, b in zip(y, p))
        pr = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
        fs.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(fs) / 3


def main():
    rows, clm = load(), CLM()
    md = ["# Image review calibration", "", f"{len(rows)} cases (16 briefs x pass/local_edit/regenerate), split by brief.", ""]
    allsc = {}
    for var in ("A_current", "B_suffix", "C_clean"):
        sc = {}
        for r in rows:
            ans = clm.system_one(state(r, var), questions(r))
            sc[r["id"]] = {k: read(v) for k, v in ans.items()}
        allsc[var] = sc
        y = [r["verdict"] for r in rows]
        md += [f"## state format {var}", ""]
        # raw 5-way-style choice accuracy
        for v in ("v0", "v1"):
            pred = [max(CLS, key=lambda c: sc[r["id"]][f"verdict:{v}"].get(c, 0)) for r in rows]
            md.append(f"- raw choice {v}: accuracy {sum(a == b for a, b in zip(y, pred)) / len(y):.2f}, macro-F1 {macro_f1(y, pred):.2f}")
        # yes/no tree with per-question thresholds
        def labels(name):
            return {"meets": [int(r["verdict"] == "pass") for r in rows],
                    "g0": [int(r["verdict"] == "regenerate") for r in rows],
                    "g1": [int(r["verdict"] == "regenerate") for r in rows]}[name]
        keys = {"meets": "meets", "g0": "global:g0", "g1": "global:g1"}
        for n in keys:
            s = [sc[r["id"]][keys[n]] for r in rows]
            md.append(f"- AUC {n}: {auc(labels(n), s):.3f}")
        # region AUC: positives = the faulty region of local_edit cases; negatives = other regions of pass/local cases
        for rv in ("r0", "r1"):
            ys, ss = [], []
            for r in rows:
                if r["verdict"] == "regenerate":
                    continue
                for x in r["regions"]:
                    ys.append(int(x["id"] in r["bad"])); ss.append(sc[r["id"]][f"region:{rv}:{x['id']}"])
            md.append(f"- region AUC {rv}: {auc(ys, ss):.3f} ({sum(ys)} faulty / {len(ys)} regions)")
        md.append("")

        def tree_eval(meets_key, g_key, rv):
            res = {}
            for a, b in (("dev", "test"), ("test", "dev")):
                tr = [r for r in rows if r["split"] == a]; te = [r for r in rows if r["split"] == b]
                tm = best_threshold([int(r["verdict"] == "pass") for r in tr], [sc[r["id"]][meets_key] for r in tr], 1.0)
                tg = best_threshold([int(r["verdict"] == "regenerate") for r in tr], [sc[r["id"]][g_key] for r in tr], 1.0)
                ys2, ss2 = [], []
                for r in tr:
                    if r["verdict"] != "regenerate":
                        for x in r["regions"]:
                            ys2.append(int(x["id"] in r["bad"])); ss2.append(sc[r["id"]][f"region:{rv}:{x['id']}"])
                tr_ = best_threshold(ys2, ss2, 1.0)
                for r in te:
                    flagged = [x["id"] for x in r["regions"] if sc[r["id"]][f"region:{rv}:{x['id']}"] >= tr_]
                    if sc[r["id"]][g_key] >= tg:
                        act = "regenerate"
                    elif sc[r["id"]][meets_key] >= tm and not flagged:
                        act = "pass"
                    else:
                        act = "local_edit"
                    res[r["id"]] = (act, flagged, (tm, tg, tr_))
            return res

        md += ["| tree (meets / global / region wording) | CV accuracy | CV macro-F1 | target precision | target recall (local_edit cases) |", "|---|---|---|---|---|"]
        for g in ("g0", "g1"):
            for rv in ("r0", "r1"):
                res = tree_eval("meets", keys[g], rv)
                pred = [res[r["id"]][0] for r in rows]
                tp = fp = fn = 0
                for r in rows:
                    if r["verdict"] != "local_edit":
                        continue
                    got = set(res[r["id"]][1]); want = set(r["bad"])
                    tp += len(got & want); fp += len(got - want); fn += len(want - got)
                md.append(f"| meets / {g} / {rv} | {sum(a == b for a, b in zip(y, pred)) / len(y):.2f} | {macro_f1(y, pred):.2f} | "
                          f"{tp / max(1, tp + fp):.2f} | {tp / max(1, tp + fn):.2f} |")
        md.append("")
    (HERE / "scores_image.json").write_text(json.dumps(allsc), encoding="utf-8")
    text = chr(10).join(md)
    (HERE / "report_image.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
