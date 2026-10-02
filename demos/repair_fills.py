"""Second pass: re-fill spots that are still white, verifying the pixel after every fill (retry up to 3x)."""
import math, sys, time
sys.path.insert(0, "D:/clm/demos")
from mouse import click
from PIL import ImageGrab

PAL = {"black": (1127, 221), "rose": (1217, 251)}
TOOL_FILL, TOOL_BRUSH = (574, 227), (700, 245)
CX, CY, RX, RY = 958, 590, 210, 185
hy = lambda x: CY - RY * math.sqrt(max(0.0, 1 - ((x - CX) / RX) ** 2))
px = lambda p: ImageGrab.grab(bbox=(p[0] - 1, p[1] - 1, p[0] + 2, p[1] + 2)).convert("RGB").getpixel((1, 1))
white = lambda c: sum(c) > 700


def fill_verified(color, p):
    for attempt in range(1, 4):
        if not white(px(p)):
            return True, attempt - 1
        click(*PAL[color], 0.3); click(*TOOL_FILL, 0.4); click(*p, 0.5)
    ok = not white(px(p)); click(*TOOL_BRUSH, 0.3)
    return ok, 3


click(900, 945, 0.4)                                   # Paint on top
jobs = [("rose", (958, 727), "tongue"), ("black", (900, int(hy(900) - 18)), "spike x=900"),
        ("black", (840, int(hy(840) - 27)), "spike tip x=840"), ("black", (1076, int(hy(1076) - 27)), "spike tip x=1076"),
        ("black", (900, int(hy(900) - 24)), "spike tip x=900"), ("black", (1016, int(hy(1016) - 27)), "spike tip x=1016")]
for color, p, name in jobs:
    before = px(p)
    ok, tries = fill_verified(color, p)
    print(f"{name:18s} at {p}: {before} -> {px(p)}  {'ok' if ok else 'STILL WHITE'} (retries {tries})", flush=True)
click(*TOOL_BRUSH, 0.3)
time.sleep(0.5)
ImageGrab.grab(bbox=(382, 365, 1535, 915)).save("D:/clm/demos/shinchan_result.png")
