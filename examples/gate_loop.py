"""Usage A: the CLM gate in front of every action of an agent loop (see docs/01-gate.md).

    cd python && python ../examples/gate_loop.py        (needs a running clm-serve; CLM_URL if it is not on :8700)

The screens are canned so this runs anywhere; a real agent would read them from the application (UI Automation, DOM, terminal output...).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from clm_router import route  # noqa: E402

TASK = "Install 7-Zip"
SCREENS = [  # (what the agent just did, what it now sees)
    ("search '7zip download'", 'Window "7-Zip download - Google Search"\n  Hyperlink "Download 7-Zip"\n  Hyperlink "7-Zip - Wikipedia"'),
    ("click 'Download 7-Zip', open 7z2501-x64.exe", 'Window "7-Zip Setup"\n  Text "License Agreement"\n  RadioButton "I accept the terms"\n  Button "Next"\n  Button "Cancel"'),
    ("click Next, click Install", 'Window "User Account Control"\n  Text "Do you want to allow this app to make changes to your device?"\n  Button "Yes"\n  Button "No"'),
    ("(never reached)", 'Window "7-Zip Setup"\n  Text "Completed the 7-Zip Setup Wizard"\n  Button "Finish"'),
]

history, prev = [], None
for last_action, screen in SCREENS:
    out = route({"mode": "computer_use", "platform": "windows", "task": TASK, "history": history, "last_action": last_action,
                 "observation": {"text": screen, "prev_text": prev}})        # text given -> the screen is never captured
    d = out["decision"]
    print(f"after '{last_action}': {d['action']:<9} route={d['route']:<6} confidence={d['confidence']:.2f} {d['reasons']}")
    if d["action"] == "ask_user":
        print("-> stop here and ask the human before doing anything on this screen")
        break
    if d["route"] == "review":
        print("-> low confidence: re-check the evidence (or let the main model look) before acting")
    history.append(last_action)
    prev = screen
