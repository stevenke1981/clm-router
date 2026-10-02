"""Draw Crayon Shin-chan in MS Paint (Windows 11, zh-TW UI) with the CLM computer-use gate, recorded by RecordScreen.

Per step:   observe Paint (UI Automation) -> CLM decision (clm_router) -> act unless the decision is ask_user
Per fill:   pixel check that the region is enclosed (a flood fill that leaks would repaint the whole canvas)
At the end: screenshot of the canvas -> online VLM description -> CLM image review (pass / local_edit / regenerate)

usage: python demos/paint_shinchan.py [--no-record] [--no-review]
needs: clm-serve :8700, RecordScreen GUI running, Paint on top (1152x648 @100%, canvas at x382..1534 y365..915).
"""
import collections
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python")); sys.path.insert(0, str(ROOT / "demos"))
from PIL import ImageGrab  # noqa: E402
from clm_router import observe, route  # noqa: E402
from mouse import VK_A, bezier, click, ellipse, key, stroke  # noqa: E402

TITLE = "小畫家"
TASK = "Draw Crayon Shin-chan (bust: head, spiky hair, thick eyebrows, mouth, red shirt) in Paint"
RECORD, REVIEW = "--no-record" not in sys.argv, "--no-review" not in sys.argv
WINDOW_ONLY = "--window" in sys.argv   # default: whole desktop (single-window capture of Paint is black, see README)
RS = "http://127.0.0.1:17321"
CANVAS = (382, 365, 1535, 915)  # screen bbox of the visible canvas

PAL = {"black": (1127, 221), "darkred": (1187, 221), "red": (1217, 221), "rose": (1217, 251), "skin": (1127, 281)}
TOOL_FILL, TOOL_BRUSH = (574, 227), (700, 245)

os.environ["OBS_WINDOW_TITLE"] = TITLE
os.environ["OBS_MAX_NODES"] = "400"
log, history, prev_text, skipped = [], [], None, []


# ------------------------------------------------------------------ RecordScreen
def rs(path, body=None):
    token = (Path(os.environ["LOCALAPPDATA"]) / "RecordScreen" / "agent-token.txt").read_text().strip()  # never printed
    get = path in ("/api/v1/status", "/api/v1/windows")
    req = urllib.request.Request(RS + path, data=None if get else json.dumps(body or {}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                 method="GET" if get else "POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def paint_hwnd():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-Process mspaint | Where-Object MainWindowHandle -ne 0 | Select-Object -First 1).MainWindowHandle"],
                         capture_output=True, text=True).stdout.strip()
    return int(out)


# ------------------------------------------------------------------ CLM gate
def gate(step, last_action):
    global prev_text
    o = observe.observe({}, 0)
    req = {"mode": "computer_use", "platform": "windows", "task": TASK, "history": history[-8:], "last_action": last_action,
           "observation": {"text": o["text"], "prev_text": prev_text}}
    out = route(req)
    prev_text = o["text"]
    d = out["decision"]
    log.append({"step": step, "last_action": last_action, "source": o["source"], "chars": len(o["text"]), "decision": d,
                "raw": {k: round(v.get("noul", 0), 3) for k, v in out["clm_raw"].items()}})
    print(f"[gate] {step:<24} -> {d['action']:<9} {d['route']:<6} conf={d['confidence']:.2f} {d['reasons']}", flush=True)
    return d


# ------------------------------------------------------------------ pixels
def region_ok(pt, max_frac=0.30, tol=40):
    """Would a flood fill started at pt stay inside an enclosed region? (leaks reach the canvas border / get huge)"""
    img = ImageGrab.grab(bbox=CANVAS).convert("RGB")
    s = 2
    img = img.resize((img.width // s, img.height // s))
    w, h = img.size
    px = img.load()
    x0, y0 = (pt[0] - CANVAS[0]) // s, (pt[1] - CANVAS[1]) // s
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


def non_white_frac():
    img = ImageGrab.grab(bbox=CANVAS).convert("L").resize((288, 137))
    d = list(img.getdata())
    return sum(1 for v in d if v < 245) / len(d)


# ------------------------------------------------------------------ actions
def set_size(n):
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "ui_set.ps1"),
                    "-Title", TITLE, "-Name", "大小", "-Value", str(n)], capture_output=True, timeout=60)


def pick(color):
    click(*PAL[color], 0.2)


def brush(color="black", size=6):
    click(*TOOL_BRUSH, 0.3); pick(color); set_size(size)


def pixel(p):
    return ImageGrab.grab(bbox=(p[0] - 1, p[1] - 1, p[0] + 2, p[1] + 2)).convert("RGB").getpixel((1, 1))


RGB = {"black": (0, 0, 0), "skin": (255, 215, 181), "darkred": (136, 0, 21), "rose": (255, 174, 201), "red": (237, 28, 36)}


def count_colour(rgb, tol=24):
    """Pixels of the canvas (2x downsampled, so x4 for real pixels) within `tol` of rgb."""
    img = ImageGrab.grab(bbox=CANVAS).convert("RGB").resize(((CANVAS[2] - CANVAS[0]) // 2, (CANVAS[3] - CANVAS[1]) // 2))
    return sum(1 for c in img.get_flattened_data() if abs(c[0] - rgb[0]) + abs(c[1] - rgb[1]) + abs(c[2] - rgb[2]) <= tol)


def fill(color, *points):
    """Flood fill each point only if its region is enclosed; afterwards check that the colour grew by about the region's
    size (a leak repaints far more) and undo with Ctrl+Z if it did; retry when Paint ate the click."""
    for p in points:
        if sum(pixel(p)) < 60 and color == "black":
            continue                                    # already black
        ok, area = region_ok(p)
        if not ok or area < 30:                         # leak, or just an antialiasing speck
            skipped.append({"color": color, "at": p, "area": area}); print(f"[skip] fill {color} at {p}: area {area}, enclosed={ok}", flush=True)
            continue
        for attempt in range(3):
            c0, before = count_colour(RGB[color]), pixel(p)
            pick(color); click(*TOOL_FILL, 0.3); click(*p, 0.6)
            if pixel(p) == before:
                print(f"[retry] fill {color} at {p} had no effect (attempt {attempt + 1})", flush=True); continue
            grew = count_colour(RGB[color]) - c0
            if grew > area * 1.6 + 60:                  # leaked: far more pixels changed than the region holds
                key(0x5A, ctrl=True); time.sleep(0.5)
                skipped.append({"color": color, "at": p, "area": area, "grew": grew, "note": "leak detected, undone"})
                print(f"[undo] fill {color} at {p} leaked (+{grew} px vs region {area}); undone", flush=True)
            break
        else:
            skipped.append({"color": color, "at": p, "area": area, "note": "no effect after 3 tries"})
    click(*TOOL_BRUSH, 0.3)


def blank_canvas():
    click(900, 945, 0.4)          # blank spot of Paint's status bar: Paint on top
    click(1620, 600, 0.3)         # workspace beside the canvas: keyboard focus without drawing
    key(VK_A, ctrl=True); key(0x2E); time.sleep(0.6)   # Ctrl+A, Delete  (Ctrl+A switches Paint to the selection tool!)
    brush("black", 6)


# ------------------------------------------------------------------ the drawing
CX, CY, RX, RY = 958, 590, 210, 185


def head_y(x):
    return CY - RY * math.sqrt(max(0.0, 1 - ((x - CX) / RX) ** 2))


def step_head():
    stroke(ellipse(CX, CY, RX, RY, -math.pi / 2, 1.5 * math.pi, 120))


def step_ears():
    for cx, sgn in ((750, -1), (1166, 1)):
        stroke([(cx + sgn * 34 * math.cos(t), 600 + 46 * math.sin(t)) for t in [(-math.pi / 2) + math.pi * i / 30 for i in range(31)]])


def step_hair():
    stroke(bezier((772, 505), (958, 545), (1144, 505)))
    for x in (840, 900, 958, 1016, 1076):
        stroke([(x - 22, head_y(x - 22)), (x, head_y(x) - 30), (x + 22, head_y(x + 22))])


def step_face():
    set_size(22)
    stroke([(850, 574), (920, 563)]); stroke([(996, 563), (1066, 574)])
    set_size(6)
    stroke(ellipse(884, 622, 26, 22)); stroke(ellipse(1032, 622, 26, 22))
    set_size(16)
    click(890, 625, 0.25); click(1026, 625, 0.25)
    set_size(5)
    stroke(bezier((944, 654), (958, 666), (972, 654)))


def step_mouth():
    set_size(6)
    stroke([(880, 692), (1036, 692)])
    stroke(ellipse(958, 692, 78, 60, 0, math.pi, 60)[::-1])
    set_size(4)
    stroke(ellipse(958, 727, 36, 14))


def step_body():
    set_size(6)
    for x in (930, 986):
        stroke([(x, 770), (x, 792)])
    stroke([(930, 792), (986, 792)])
    stroke([(770, 905), (800, 832), (880, 794), (930, 792)])
    stroke([(986, 792), (1036, 794), (1116, 832), (1146, 905), (770, 905)])


def step_fills():
    fill("black", (958, 455), *[(x, head_y(x) - d) for x in (840, 900, 958, 1016, 1076) for d in (12, 18, 24)])   # hair first:
    fill("skin", (958, 600), (726, 600), (1190, 600), (958, 781))                                                 # white->black never leaks into peach
    fill("darkred", (958, 702))
    fill("rose", (958, 727))
    fill("red", (958, 860))


STEPS = [("draw head outline", step_head), ("draw ears", step_ears), ("draw hair", step_hair),
         ("draw eyebrows eyes nose", step_face), ("draw mouth and tongue", step_mouth),
         ("draw neck and shirt", step_body), ("fill colours", step_fills)]

BRIEF = ("Crayon Shin-chan cartoon bust: round peach head, black spiky hair on top, very thick black eyebrows, "
         "two eyes with black pupils, open smiling mouth with a pink tongue, red shirt")
CRITERIA = ["round peach-coloured head", "black spiky hair on top", "very thick black eyebrows", "two eyes",
            "open smiling mouth", "red shirt", "no large black or flat-coloured areas covering the picture"]


def review(canvas_png):
    """VLM text description of the canvas -> CLM image review (the pipeline's image_review path)."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        key_ = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY','User')"],
                              capture_output=True, text=True).stdout.strip()
        if key_:
            os.environ["OPENROUTER_API_KEY"] = key_
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("[review] no OPENROUTER_API_KEY: skipped"); return None
    desc = observe.describe_online(str(canvas_png), observe.IMAGE_PROMPT, retries=6)
    regions = [{"id": m.group(1), "description": m.group(2).strip()} for m in re.finditer(r"\[([\w -]+)\]\s*(.+)", desc)]
    req = {"mode": "image_review", "task": BRIEF, "image": {"brief": BRIEF, "criteria": CRITERIA, "description": desc, "regions": regions}}
    out = route(req)
    print(f"[review] CLM image verdict: {out['decision']['action']} conf={out['decision']['confidence']:.2f} "
          f"targets={out['decision']['targets']} {out['decision']['reasons']}")
    return {"description": desc, "decision": out["decision"], "raw": out["clm_raw"]}


def main():
    hwnd = paint_hwnd()
    if hwnd not in {w["hwnd"] for w in rs("/api/v1/windows")["windows"]}:
        sys.exit(f"Paint hwnd {hwnd} is not in RecordScreen's window list (visible / not minimised?)")
    stopped = rev = None
    shot = ROOT / "demos" / "shinchan_result.png"
    if RECORD:
        print("[rec] target:", "Paint window" if WINDOW_ONLY else "entire desktop", rs("/api/v1/target", {"hwnd": hwnd if WINDOW_ONLY else None}).get("ok"))
        click(900, 945, 0.5)
        print("[rec] start:", rs("/api/v1/recording/start", {"fps": 30})); time.sleep(1.5)
    try:
        blank_canvas()
        last = "opened Paint with a blank canvas"
        for name, fn in STEPS:
            d = gate(name, last)
            if d["action"] == "ask_user":
                print(f"[STOP] CLM wants a human before '{name}': {d['reasons']}"); break
            fn(); history.append(name); last = name; time.sleep(0.4)
            print(f"       canvas non-white: {non_white_frac():.1%}", flush=True)
        else:
            gate("finished", last)
        time.sleep(0.8)
        ImageGrab.grab(bbox=CANVAS).save(shot)
    finally:
        if RECORD:
            time.sleep(1.0); stopped = rs("/api/v1/recording/stop"); print("[rec] stop:", stopped)
    if REVIEW:
        rev = review(shot)
    (ROOT / "demos" / "paint_run.json").write_text(json.dumps({"log": log, "skipped_fills": skipped, "review": rev, "recording": stopped},
                                                               ensure_ascii=False, indent=1), encoding="utf-8")


main()
