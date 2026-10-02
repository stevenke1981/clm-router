"""End-to-end: run all labelled image cases through the PRODUCTION path (router + policy) on the real CLM,
and (with --rust) compare with the Rust binary.   usage: python calib/check_image_prod.py [--rust]"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "python")); sys.path.insert(0, str(HERE))
from clm_router import route  # noqa: E402
from eval_image import CLS, load, macro_f1, req_of  # noqa: E402

EXE = str(HERE.parent / "rust" / "target" / "debug" / "clm-router.exe")


def main():
    rows = load()
    rows_py, mism = [], 0
    for r in rows:
        req = {"mode": "image_review", **req_of(r)}
        d = route(req)["decision"]
        rows_py.append(d)
        if "--rust" in sys.argv:
            rs = json.loads(subprocess.run([EXE, "-"], input=json.dumps(req), capture_output=True, text=True, encoding="utf-8").stdout)["decision"]
            same = (d["action"], d["targets"], round(d["confidence"], 4)) == (rs["action"], rs["targets"], round(rs["confidence"], 4))
            mism += not same
            if not same:
                print("MISMATCH", r["id"], d["action"], rs["action"], d["targets"], rs["targets"])
    y = [r["verdict"] for r in rows]; p = [d["action"] for d in rows_py]
    print(f"verdict accuracy {sum(a == b for a, b in zip(y, p)) / len(y):.2f}  macro-F1 {macro_f1(y, p):.2f}")
    for c in CLS:
        print(f"  {c:11s} correct {sum(a == b == c for a, b in zip(y, p))}/{y.count(c)}")
    loc = [(r, d) for r, d in zip(rows, rows_py) if r["verdict"] == "local_edit" and d["action"] == "local_edit"]
    print(f"local_edit target top-1 hit (among correctly routed): {sum(d['targets'][0] in r['bad'] for r, d in loc if d['targets'])}/{len(loc)}")
    print("wrong:", [(r["id"], r["verdict"], d["action"], round(d["confidence"], 2)) for r, d in zip(rows, rows_py) if r["verdict"] != d["action"]])
    low = [d["confidence"] for d in rows_py]
    print("confidence < 0.5:", sum(c < 0.5 for c in low), "| route fast:", sum(d["route"] == "fast" for d in rows_py))
    if "--rust" in sys.argv:
        print("python/rust mismatches:", mism)


main()
