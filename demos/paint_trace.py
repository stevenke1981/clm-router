"""Trace a reference image (demos/ref/regions.json, made by vectorize.py) in MS Paint with the CLM computer-use gate.

Per colour group:  CLM gate -> pencil-trace each region's outline (outer + holes) in its own colour -> hatch its interior.
Fill:              scanline hatching of the region mask with the pencil (no flood fill -> nothing can leak).
At the end:        numeric comparison with the reference (colour error, black-line IoU), then VLM description -> CLM image review.

usage: python demos/paint_trace.py [--no-record] [--no-review] [--window]
needs: clm-serve :8700, RecordScreen GUI running, Paint on top (1152x648 @100%), Windows 11 zh-TW Paint.
"""
import collections
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python")); sys.path.insert(0, str(ROOT / "demos"))
from PIL import ImageGrab  # noqa: E402
from clm_router import observe, route  # noqa: E402
from mouse import VK_A, VK_TAB, click, key, quick_line, stroke, type_text  # noqa: E402

TITLE = "小畫家"
TASK = "Trace the Crayon Shin-chan reference picture in Paint and colour it"
RECORD, REVIEW = "--no-record" not in sys.argv, "--no-review" not in sys.argv
WINDOW_ONLY = "--window" in sys.argv
RS = "http://127.0.0.1:17321"
CANVAS = (382, 365, 1535, 915)
TOOL_FILL, TOOL_PENCIL = (574, 227), (524, 227)
BLACK = (1127, 221)
PEN_SIZE = 3

REG = json.loads((ROOT / "demos" / "ref" / "regions.json").read_text(encoding="utf-8"))
UP, (W4, H4) = REG["up"], REG["size"]
S = 520 / H4                                   # reference (4x) pixel -> screen pixel
X0, Y0 = CANVAS[0] + (CANVAS[2] - CANVAS[0] - W4 * S) / 2, CANVAS[1] + 14
BBOX = (int(X0) - 6, int(Y0) - 6, int(X0 + W4 * S) + 6, int(Y0 + H4 * S) + 6)

os.environ["OBS_WINDOW_TITLE"] = TITLE
os.environ["OBS_MAX_NODES"] = "400"
log, history, skipped = [], [], []
prev_text = None


def to_screen(p):
    return (X0 + p[0] * S, Y0 + p[1] * S)


# ------------------------------------------------------------------ RecordScreen / CLM gate
def rs(path, body=None):
    token = (Path(os.environ["LOCALAPPDATA"]) / "RecordScreen" / "agent-token.txt").read_text().strip()  # never printed
    get = path in ("/api/v1/status", "/api/v1/windows")
    req = urllib.request.Request(RS + path, data=None if get else json.dumps(body or {}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="GET" if get else "POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def paint_hwnd():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Process mspaint | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1).MainWindowHandle"],
                         capture_output=True, text=True).stdout.strip()
    return int(out)


def gate(step, last_action):
    global prev_text
    o = observe.observe({}, 0)
    out = route({"mode": "computer_use", "platform": "windows", "task": TASK, "history": history[-8:], "last_action": last_action,
                 "observation": {"text": o["text"], "prev_text": prev_text}})
    prev_text = o["text"]
    d = out["decision"]
    log.append({"step": step, "last_action": last_action, "decision": d, "raw": {k: round(v.get("noul", 0), 3) for k, v in out["clm_raw"].items()}})
    print(f"[gate] {step:<30} -> {d['action']:<9} {d['route']:<6} conf={d['confidence']:.2f} {d['reasons']}", flush=True)
    return d


# ------------------------------------------------------------------ pixels
def pixel(p):
    return ImageGrab.grab(bbox=(int(p[0]) - 1, int(p[1]) - 1, int(p[0]) + 2, int(p[1]) + 2)).convert("RGB").getpixel((1, 1))


def region_ok(pt, max_frac=0.30, tol=40):
    img = ImageGrab.grab(bbox=CANVAS).convert("RGB"); s = 2
    img = img.resize((img.width // s, img.height // s)); w, h = img.size; px = img.load()
    x0, y0 = int(pt[0] - CANVAS[0]) // s, int(pt[1] - CANVAS[1]) // s
    seed = px[x0, y0]
    near = lambda c: sum(abs(a - b) for a, b in zip(c, seed)) <= tol
    seen, q, area = {(x0, y0)}, collections.deque([(x0, y0)]), 0
    while q:
        x, y = q.popleft(); area += 1
        if x in (0, w - 1) or y in (0, h - 1) or area > max_frac * w * h:
            return False, area
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in seen and near(px[nx, ny]):
                seen.add((nx, ny)); q.append((nx, ny))
    return True, area


def count_colour(rgb, tol=24):
    img = ImageGrab.grab(bbox=CANVAS).convert("RGB").resize(((CANVAS[2] - CANVAS[0]) // 2, (CANVAS[3] - CANVAS[1]) // 2))
    return sum(1 for c in img.get_flattened_data() if abs(c[0] - rgb[0]) + abs(c[1] - rgb[1]) + abs(c[2] - rgb[2]) <= tol)


# ------------------------------------------------------------------ Paint actions
def set_size(n):
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "ui_set.ps1"),
                    "-Title", TITLE, "-Name", "大小", "-Value", str(n)], capture_output=True, timeout=60)


SWATCH = (1082, 228)       # the big "colour 1" swatch of Paint's palette


def set_colour(rgb):
    """Select `rgb` as colour 1 via the edit-colour dialog (hex field) and verify it on the swatch."""
    hexv = "#%02X%02X%02X" % tuple(rgb)
    click(1447, 252, 1.5); click(1107, 253, 0.3); key(VK_A, ctrl=True); type_text(hexv); key(VK_TAB); time.sleep(0.8)
    click(763, 908, 1.2)                                       # OK
    got = pixel(SWATCH)
    if sum(abs(a - b) for a, b in zip(got, rgb)) > 24:
        raise RuntimeError(f"colour 1 is {got}, wanted {tuple(rgb)} ({hexv})")
    return got


def set_black():
    click(*BLACK, 0.3)
    got = pixel(SWATCH)
    if sum(got) > 60:
        raise RuntimeError(f"colour 1 is {got}, wanted black")


def blank_canvas():
    click(900, 945, 0.4); click(1620, 600, 0.3)
    key(VK_A, ctrl=True); key(0x2E); time.sleep(0.6)           # Ctrl+A, Delete (Ctrl+A switches Paint to the selection tool)
    click(*TOOL_PENCIL, 0.3); click(*BLACK, 0.2); set_size(PEN_SIZE)


def region_mask(r):
    m = np.zeros((H4, W4), np.uint8)
    cv2.fillPoly(m, [np.array(r["outer"], np.int32)], 255)
    for h in r["holes"]:
        cv2.fillPoly(m, [np.array(h, np.int32)], 0)
    return m


HATCH = 2.4        # screen px between scanlines (pencil is PEN_SIZE=3 wide, so lines overlap)


def hatch_region(r):
    """Paint the region's own pixels with horizontal pencil strokes (no flood fill, so nothing can leak)."""
    m = region_mask(r)
    ys, xs = np.nonzero(m)
    n = 0
    y_screen = Y0 + ys.min() * S
    while y_screen <= Y0 + ys.max() * S:
        row = m[min(H4 - 1, max(0, int(round((y_screen - Y0) / S))))] > 0
        d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
        for a_, b_ in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
            x1, x2 = X0 + a_ * S + 0.5, X0 + (b_ - 1) * S - 0.5
            if x2 - x1 >= 1.0:
                quick_line((x1, y_screen), (x2, y_screen)); n += 1
        y_screen += HATCH
    return n


def trace_region(r):
    click(*TOOL_PENCIL, 0.2)
    for poly in [r["outer"]] + r["holes"]:                 # 1) outline, as the reference's contour
        pts = [to_screen(p) for p in poly]
        stroke(pts + [pts[0]], step=3.0, delay=0.002)
    return hatch_region(r)                                  # 2) interior


# ------------------------------------------------------------------ evaluation
def compare():
    ref = cv2.imread(str(ROOT / "demos" / "ref" / "shinchan_vol1_cover.jpg"))[150:376, 0:265].copy()
    cv2.circle(ref, (37, 20), 31, (255, 255, 255), -1); cv2.fillPoly(ref, [np.array([[50, 30], [72, 52], [64, 28]])], (255, 255, 255))
    shot = ImageGrab.grab(bbox=BBOX)
    got = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(ROOT / "demos" / "trace_result.png"), got)
    ref_r = cv2.resize(ref, (got.shape[1], got.shape[0]), interpolation=cv2.INTER_AREA)
    mad = float(np.mean(np.abs(ref_r.astype(float) - got.astype(float))))
    black = lambda im: cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) < 70
    a, b = black(ref_r), black(got)
    iou = float((a & b).sum() / max(1, (a | b).sum()))
    cv2.imwrite(str(ROOT / "demos" / "trace_side_by_side.png"), np.hstack([ref_r, got]))
    return {"mean_abs_colour_error": round(mad, 1), "black_line_iou": round(iou, 3), "bbox": BBOX}


BRIEF = ("Crayon Shin-chan (Shinnosuke Nohara) cartoon from the manga cover: pink-orange face, thick black outline, black hair mass on top, "
         "two thick arched black eyebrows, two small black eyes with white highlights, a tiny nose dot, yellow-orange shirt, a hand at the chin")
CRITERIA = ["pink-orange face with a thick black outline", "black hair on top", "two thick arched black eyebrows", "two black eyes",
            "yellow-orange shirt", "no large flat-coloured areas covering the picture"]


def review(png):
    if not os.environ.get("OPENROUTER_API_KEY"):
        k = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User')"], capture_output=True, text=True).stdout.strip()
        if k:
            os.environ["OPENROUTER_API_KEY"] = k
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("[review] no OPENROUTER_API_KEY: skipped"); return None
    desc = observe.describe_online(str(png), observe.IMAGE_PROMPT, retries=6)
    regions = [{"id": m.group(1), "description": m.group(2).strip()} for m in re.finditer(r"^\s*\[([A-Za-z][\w -]*)\]\s*(.+)$", desc, re.M)]
    out = route({"mode": "image_review", "task": BRIEF, "image": {"brief": BRIEF, "criteria": CRITERIA, "description": desc, "regions": regions}})
    d = out["decision"]
    print(f"[review] CLM image verdict: {d['action']} conf={d['confidence']:.2f} targets={d['targets']} {d['reasons']}")
    return {"description": desc, "decision": d}


def main():
    hwnd = paint_hwnd()
    if hwnd not in {w["hwnd"] for w in rs("/api/v1/windows")["windows"]}:
        sys.exit(f"Paint hwnd {hwnd} is not in RecordScreen's window list")
    print(f"picture box on screen: {BBOX}  scale {S:.3f}; {len(REG['regions'])} regions")
    stopped = rev = metrics = None
    if RECORD:
        print("[rec] target:", "Paint window" if WINDOW_ONLY else "entire desktop", rs("/api/v1/target", {"hwnd": hwnd if WINDOW_ONLY else None}).get("ok"))
        click(900, 945, 0.5)
        print("[rec] start:", rs("/api/v1/recording/start", {"fps": 30})); time.sleep(1.5)
    try:
        blank_canvas()
        d = gate("set up custom colours", "opened Paint with a blank canvas")
        if d["action"] == "ask_user":
            print("[STOP] CLM wants a human:", d["reasons"]); return
        last = "set up custom colours"
        history.append(last)
        click(*TOOL_PENCIL, 0.3); set_size(PEN_SIZE)
        for color in ("skin", "black", "orange"):
            group = [r for r in REG["regions"] if r["color"] == color]
            d = gate(f"trace {color} regions ({len(group)})", last)
            if d["action"] == "ask_user":
                print(f"[STOP] CLM wants a human before tracing {color}:", d["reasons"]); break
            print(f"[colour] {color}: colour 1 =", set_black() if color == "black" else set_colour(REG["palette"][color]), flush=True)
            click(*TOOL_PENCIL, 0.2)
            t0 = time.time()
            strokes = sum(trace_region(r) for r in group)
            history.append(f"trace {color} regions"); last = f"trace {color} regions"
            print(f"       {color}: {len(group)} regions, {strokes} hatch strokes, {time.time() - t0:.0f}s", flush=True)
        gate("finished", last)
        time.sleep(0.8)
        metrics = compare(); print("[compare]", metrics)
    finally:
        if RECORD:
            time.sleep(1.0); stopped = rs("/api/v1/recording/stop"); print("[rec] stop:", stopped)
    if REVIEW and metrics:
        rev = review(ROOT / "demos" / "trace_result.png")
    (ROOT / "demos" / "trace_run.json").write_text(json.dumps({"log": log, "skipped": skipped, "metrics": metrics, "review": rev, "recording": stopped},
                                                               ensure_ascii=False, indent=1), encoding="utf-8")


main()
