"""One gated step at a time in a Chrome window (used to drive https://flow.google.com/).

usage: python demos/flow_step.py <command> [args]
  look                      read the page (UI Automation; OCR if the page tree is empty) and show the CLM decision
  click "<label>" [role]    find the element whose name contains <label> (optionally of that role), gate, click its centre
  clickxy X Y               gate, click screen coordinates
  type "<text>"             gate, type text into the focused field
  key enter|tab|esc|down|up gate, press a key
  shot [name]               save a screenshot of the browser window to demos/flow/<name>.png (for local viewing only)
  note "<what happened>"    append to the action history without acting
Every acting command first runs: observe -> clm_router.route; `ask_user` (credentials, payments, irreversible choices) refuses.
State (history, previous page text, window handle) lives in demos/flow_state.json.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python")); sys.path.insert(0, str(ROOT / "demos"))
from PIL import ImageGrab  # noqa: E402
from clm_router import observe, route  # noqa: E402
from mouse import click, key, type_text  # noqa: E402

STATE = ROOT / "demos" / "flow_state.json"
TASK = "In Google Flow (flow.google.com): generate an image from a text prompt, check the result, and download it"
KEYS = {"enter": 0x0D, "tab": 0x09, "esc": 0x1B, "down": 0x28, "up": 0x26, "space": 0x20}


def load():
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"history": [], "prev_text": None, "hwnd": None, "log": []}
    if not st["hwnd"]:
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "find_window.ps1"), "-Title", "Flow"],
                             capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
        cands = [l.split("|", 1) for l in out if "Chrome" in l and "Claude Code" not in l]
        if not cands:
            sys.exit("no Chrome window with 'Flow' in its title")
        st["hwnd"] = int(cands[0][0])
    return st


def save(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def observe_page(st):
    os.environ["OBS_WINDOW_HWND"] = str(st["hwnd"]); os.environ["OBS_MAX_NODES"] = "400"
    for attempt in range(5):                      # Chrome builds the page accessibility tree lazily (and drops it when idle)
        o = observe.observe({}, 0)
        if o["source"] != "a11y+ocr" or attempt == 4:
            return o
        time.sleep(3)
    return o


def gate(st, last_action):
    o = observe_page(st)
    d = route({"mode": "computer_use", "platform": "windows", "task": TASK, "history": st["history"][-8:], "last_action": last_action,
               "observation": {"text": o["text"], "prev_text": st["prev_text"]}})["decision"]
    st["prev_text"] = o["text"]
    st["log"].append({"before": last_action, "source": o["source"], "decision": {k: d[k] for k in ("action", "route", "confidence", "reasons")}})
    print(f"[gate] before '{last_action}': {d['action']} {d['route']} conf={d['confidence']:.2f} {d['reasons']}  (observed via {o['source']}, {len(o['text'])} chars)")
    return d, o


ELEM = re.compile(r'^\s*(\w+) "(.*)" @\((-?\d+),(-?\d+),(\d+)x(\d+)\)( disabled)?$')


def elements(text):
    for line in text.splitlines():
        m = ELEM.match(line)
        if m:
            role, name, x, y, w, h, dis = m.groups()
            yield {"role": role, "name": name, "x": int(x), "y": int(y), "w": int(w), "h": int(h), "disabled": bool(dis)}


def raise_window(st):
    click(900, 38, 0.3)  # blank part of Chrome's tab strip (the Flow window is the one at the top): brings it to the front, changes nothing


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    st = load()
    if cmd == "look":
        d, o = gate(st, st["history"][-1] if st["history"] else "opened the page")
        keep = [e for e in elements(o["text"]) if e["role"] in ("Button", "Hyperlink", "Edit", "Text", "ComboBox", "ListItem", "MenuItem", "CheckBox", "RadioButton", "TabItem", "Image", "Document", "Group")
                and e["y"] > 110 and e["w"] > 0]
        for e in keep[:90]:
            print(f'  {e["role"]:<10} "{e["name"][:70]}" @({e["x"]},{e["y"]},{e["w"]}x{e["h"]}){" disabled" if e["disabled"] else ""}')
        if o["source"] == "a11y+ocr":
            print("  (page tree empty -> OCR text above the browser UI was used)")
    elif cmd == "shot":
        name = args[0] if args else "shot"
        (ROOT / "demos" / "flow").mkdir(exist_ok=True)
        r = [int(v) for v in subprocess.run(["powershell", "-NoProfile", "-Command",
             f"Add-Type -AssemblyName UIAutomationClient; $e=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{st['hwnd']}); $r=$e.Current.BoundingRectangle; '{{0}} {{1}} {{2}} {{3}}' -f [int]$r.X,[int]$r.Y,[int]$r.Right,[int]$r.Bottom"],
             capture_output=True, text=True).stdout.split()]
        path = ROOT / "demos" / "flow" / f"{name}.png"
        ImageGrab.grab(bbox=tuple(r)).save(path); print("saved", path, r)
    elif cmd == "note":
        st["history"].append(" ".join(args)); print("noted")
    else:
        if cmd == "click":
            label, role = args[0], (args[1] if len(args) > 1 else None)
            desc = f"click '{label}'"
        elif cmd == "clickxy":
            desc = f"click ({args[0]},{args[1]})"
        elif cmd == "type":
            desc = f"type '{args[0][:60]}'"
        elif cmd == "key":
            desc = f"press {args[0]}"
        else:
            sys.exit(f"unknown command {cmd}")
        d, o = gate(st, st["history"][-1] if st["history"] else "opened the page")
        if d["action"] == "ask_user":
            save(st); print(f"[REFUSED] CLM wants a human before '{desc}': {d['reasons']}"); sys.exit(3)
        raise_window(st)
        if cmd == "click":
            hits = [e for e in elements(o["text"]) if label.lower() in e["name"].lower() and (role is None or e["role"] == role) and not e["disabled"] and e["y"] > 110]
            if not hits:
                save(st); sys.exit(f"no element matching '{label}' ({role})")
            e = hits[0]; cx, cy = e["x"] + e["w"] // 2, e["y"] + e["h"] // 2
            print(f"clicking {e['role']} '{e['name'][:50]}' at ({cx},{cy})  [{len(hits)} match(es)]"); click(cx, cy, 1.0)
        elif cmd == "clickxy":
            click(int(args[0]), int(args[1]), 1.0)
        elif cmd == "type":
            type_text(args[0], 0.02)
        elif cmd == "key":
            key(KEYS[args[0]])
        st["history"].append(desc); time.sleep(1.5)
    save(st)


main()
