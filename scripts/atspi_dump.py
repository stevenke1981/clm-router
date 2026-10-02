"""Linux a11y outline of the active window via AT-SPI (needs python3-gi + gir1.2-atspi-2.0). Prints like uia_dump.ps1."""
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

MAX = 300
n = 0


def walk(node, d):
    global n
    if n >= MAX or d > 8:
        return
    try:
        name = (node.get_name() or "").strip()
        role = node.get_role_name()
        st = node.get_state_set()
        if (name or role in ("push button", "text", "check box", "menu item", "link")) and st.contains(Atspi.StateType.SHOWING):
            ext = node.get_extents(Atspi.CoordType.SCREEN)
            n += 1
            print(f'{"  " * d}{role} "{name}" @({ext.x},{ext.y},{ext.width}x{ext.height})')
        for i in range(node.get_child_count()):
            walk(node.get_child_at_index(i), d + 1)
    except Exception:
        pass


desk = Atspi.get_desktop(0)
for i in range(desk.get_child_count()):
    app = desk.get_child_at_index(i)
    for j in range(app.get_child_count()):
        w = app.get_child_at_index(j)
        if w.get_state_set().contains(Atspi.StateType.ACTIVE):
            walk(w, 0)
