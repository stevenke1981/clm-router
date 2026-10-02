"""Smaller attack surface for the text CLM reads: keep the interactive / structural elements of a UI Automation dump and drop
free-form paragraphs, where prompt injection hides (Jev skill: "send only needed fields, filter in code first").

modes:  full      the dump as is
        ui        Window / Button / Hyperlink / Edit / MenuItem / CheckBox / RadioButton / ComboBox / TabItem / ListItem names only
                  (no coordinates, names cut to NAME_MAX chars, free `Text` dropped)
        ui+text   `ui` plus `Text` lines of at most SHORT_MAX chars (a dialog's question, a terminal prompt), at most TEXT_LINES of them
Only text that parses as a UIA dump is touched; OCR / terminal / plain text is returned unchanged (and still goes through
policy.injection_signal). Mirrored in rust/src/compact.rs when adopted.
"""
from __future__ import annotations

import re

ELEM = re.compile(r'^\s*(\w+) "(.*)" @\((-?\d+),(-?\d+),(\d+)x(\d+)\)( disabled)?\s*$')
KEEP_ROLES = {"Window", "Button", "SplitButton", "Hyperlink", "Edit", "MenuItem", "CheckBox", "RadioButton", "ComboBox", "TabItem", "ListItem"}
NAME_MAX, SHORT_MAX, TEXT_LINES = 80, 90, 12


def is_uia(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()]
    return bool(lines) and sum(bool(ELEM.match(l)) for l in lines) >= 0.5 * len(lines)


def compact(text: str, mode: str = "full") -> str:
    if mode == "full" or not is_uia(text):
        return text
    out, texts = [], []
    for line in text.splitlines():
        m = ELEM.match(line)
        if not m:
            continue
        role, name, *_rest, disabled = m.groups()
        name = " ".join(name.split())
        if role in KEEP_ROLES:
            out.append(f'{role} "{name[:NAME_MAX]}"' + (" disabled" if disabled else ""))
        elif role == "Text" and mode == "ui+text" and 0 < len(name) <= SHORT_MAX and len(texts) < TEXT_LINES:
            texts.append(f'Text "{name}"')
    return "\n".join(out + texts)
