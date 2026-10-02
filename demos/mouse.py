"""Tiny Win32 mouse helper (physical pixels). Used by the Paint demo."""
import ctypes
import math
import time

u = ctypes.windll.user32
u.SetProcessDPIAware()
ctypes.windll.winmm.timeBeginPeriod(1)  # time.sleep(0.002) really sleeps ~2 ms instead of ~15 ms
_SW, _SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def move(x, y):
    """Absolute move as a real input event (MOUSEEVENTF_MOVE|ABSOLUTE), so apps see WM_MOUSEMOVE / pointer updates."""
    u.mouse_event(0x8001, int(round(x * 65535 / (_SW - 1))), int(round(y * 65535 / (_SH - 1))), 0, 0)


def click(x, y, pause=0.12):
    move(x, y); time.sleep(0.05)
    u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.03); u.mouse_event(4, 0, 0, 0, 0)
    time.sleep(pause)


def stroke(points, step=3.0, delay=0.003):
    """Press at points[0], glide through the polyline in <=step px moves, release at the end."""
    pts = list(points)
    move(*pts[0]); time.sleep(0.03); u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.03)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
        for i in range(1, n + 1):
            move(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n); time.sleep(delay)
    time.sleep(0.03); u.mouse_event(4, 0, 0, 0, 0); time.sleep(0.08)


def ellipse(cx, cy, rx, ry, a0=0.0, a1=2 * math.pi, n=90):
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def bezier(p0, p1, p2, n=40):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (i / n for i in range(n + 1))]


# ---- keyboard (SendInput, unicode) -------------------------------------------------------------
class _KI(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _IN(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KI), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _send(vk=0, ch=None, up=False):
    flags = (0x0002 if up else 0) | (0x0004 if ch is not None else 0)
    i = _IN(type=1); i.ki = _KI(vk, ord(ch) if ch is not None else 0, flags, 0, None)
    u.SendInput(1, ctypes.byref(i), ctypes.sizeof(_IN))


def type_text(s, delay=0.03):
    for ch in s:
        _send(ch=ch); _send(ch=ch, up=True); time.sleep(delay)


def key(vk, ctrl=False):
    if ctrl:
        _send(0x11)
    _send(vk); _send(vk, up=True)
    if ctrl:
        _send(0x11, up=True)
    time.sleep(0.1)


VK_TAB, VK_RETURN, VK_A = 0x09, 0x0D, 0x41


def quick_line(p0, p1, step=4.0, delay=0.0015):
    """Straight stroke for hatch-filling. The settle times matter: Paint processes input about once per frame (~16 ms);
    with shorter gaps it merges 'release at the end of line k' and 'press at the start of line k+1' into one stroke
    and draws a connecting line across the picture (seen as stripes through holes)."""
    move(*p0); time.sleep(0.025); u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.015)
    n = max(1, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / step))
    for i in range(1, n + 1):
        move(p0[0] + (p1[0] - p0[0]) * i / n, p0[1] + (p1[1] - p0[1]) * i / n); time.sleep(delay)
    time.sleep(0.015); u.mouse_event(4, 0, 0, 0, 0); time.sleep(0.035)
