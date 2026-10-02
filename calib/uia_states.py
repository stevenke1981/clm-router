"""Turns the hand-written dataset screens into UI-Automation-style dumps (Role "name" @(x,y,wxh)) so the compaction can be tested.

The dataset's `text` uses pseudo-structure: segments separated by ' | ' or newlines, some of them `Button "Yes"` / `Window "UAC"`.
Recognised segments become elements of that role; everything else becomes a `Text` element (a dialog sentence, a terminal line).
This is an approximation of a real dump (the real ones have far more elements): treat the numbers as indicative.
"""
import re

ROLE = re.compile(r'^(Window|Button|Link|Hyperlink|Edit|Text|MenuItem|ListItem|CheckBox|TabItem|ComboBox)\s+"(.*?)"')
MAP = {"Link": "Hyperlink"}


def segments(text: str):
    for line in text.splitlines():
        for seg in line.split(" | "):
            seg = seg.strip()
            if seg:
                yield seg


def element(role: str, name: str, i: int) -> str:
    return f'{" " * (2 + (i % 3))}{role} "{name}" @({100 + 7 * i},{120 + 26 * i},{max(40, 7 * len(name))}x24)'


def to_uia(row: dict) -> str:
    segs = list(segments(row["text"]))
    lines = []
    if not any(ROLE.match(s) and ROLE.match(s).group(1) == "Window" for s in segs):
        lines.append(f'Window "{row["platform"]} application - {row["task"][:40]}" @(0,0,1280x800)')
    for i, seg in enumerate(segs):
        m = ROLE.match(seg)
        if m:
            lines.append(element(MAP.get(m.group(1), m.group(1)), m.group(2), i))
        else:
            lines.append(element("Text", seg.replace('"', "'"), i))
    return "\n".join(lines)


def inject_into(uia: str, sentence: str, where: str) -> str:
    """Attacker-controlled text placed on the screen: as a page paragraph (Text), a link label, or a button label."""
    role = {"text": "Text", "link": "Hyperlink", "button": "Button"}[where]
    return uia + "\n" + element(role, sentence, 40)
