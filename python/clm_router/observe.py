"""Observation layer: turn the screen into text, cheapest source first.

  layer 0  a11y  UI Automation (Windows) / AT-SPI (Linux)   free, ~50 ms
  layer 1  ocr   Windows.Media.Ocr / tesseract              free, local
  layer 2  vlm   OBS_VLM=local  -> OmniParser server        local GPU
                 OBS_VLM=online -> OpenRouter (free models) screenshot LEAVES this machine

The router escalates to the next layer when CLM is not confident.
"""
from __future__ import annotations

import base64
import os
import platform
import re
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.error
from pathlib import Path

from .client import post_json

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
LAYERS = ["a11y", "ocr", "vlm"]
MIN_CHARS = {"a11y": 80, "ocr": 40, "vlm": 1}  # below this the layer is "not enough text"
IS_WIN = platform.system() == "Windows"

ONLINE_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
UI_PROMPT = (
    "You are reading a computer screenshot for an automation agent. List the visible app/window, "
    "dialogs, buttons, inputs, menus and any error text, one per line as: role \"label\" @(x,y) in "
    "pixels of the image. Then one line starting 'STATE:' summarising what the screen shows. Be concise."
)
IMAGE_PROMPT = (
    "Describe this generated image for a QA reviewer: subject, composition, style, any text exactly as "
    "written, and visible defects (hands, faces, artifacts). Then list regions as: [id] description."
)


def _run(cmd: list[str], timeout=30) -> str:
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]}: {r.stderr.strip()[:200]}")
    return r.stdout


def _ps(script: str, *args: str) -> str:
    return _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / script), *args])


def screenshot(path: str | None = None) -> str:
    out = path or str(Path(tempfile.mkdtemp(prefix="clm_")) / "screen.png")
    if IS_WIN:
        _ps("screenshot.ps1", out)
    else:
        for cmd in (["grim", out], ["scrot", "-o", out], ["import", "-window", "root", out],
                    ["gnome-screenshot", "-f", out]):
            if shutil.which(cmd[0]):
                _run(cmd)
                break
        else:
            raise RuntimeError("no screenshot tool (grim/scrot/imagemagick/gnome-screenshot)")
    return out


def png_size(path: str) -> tuple[int, int]:
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def _a11y() -> str:
    if IS_WIN:
        title, hwnd = os.getenv("OBS_WINDOW_TITLE"), os.getenv("OBS_WINDOW_HWND")  # read this window instead of the foreground one
        sel = ["-Hwnd", hwnd] if hwnd else ["-Title", title] if title else []
        return _ps("uia_dump.ps1", *sel, "-MaxNodes", os.getenv("OBS_MAX_NODES", "300"), "-MaxDepth", os.getenv("OBS_MAX_DEPTH", "24"))  # web pages sit deep in the tree
    return _run(["python3", str(SCRIPTS / "atspi_dump.py")])


def _ocr(img: str) -> str:
    if IS_WIN:
        return _ps("ocr.ps1", img)
    if not shutil.which("tesseract"):
        raise RuntimeError("tesseract not installed")
    return _run(["tesseract", img, "stdout", "-l", os.getenv("TESSERACT_LANG", "eng")], 60)


def browser_without_content(a11y_text: str) -> bool:
    """A Chromium/Edge window whose accessibility tree has the browser UI but no web `Document`: the page itself is invisible."""
    if "Google Chrome" not in a11y_text and "Microsoft Edge" not in a11y_text:
        return False
    lines = a11y_text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"\s*Document\b", line):
            indent, kids = len(line) - len(line.lstrip()), 0
            for nxt in lines[i + 1:]:                      # Chrome builds the page tree lazily: Document can exist with no children
                if len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                kids += 1
            return kids < 5
    return True


def _omniparser(img: str) -> str:
    url = os.environ["OMNIPARSER_URL"].rstrip("/")
    w, h = png_size(img)
    b64 = base64.b64encode(Path(img).read_bytes()).decode()
    r = post_json(f"{url}/parse/", {"base64_image": b64}, timeout=120)
    lines = []
    for i, it in enumerate(r.get("parsed_content_list", [])):
        bb = it.get("bbox") or [0, 0, 0, 0]
        x, y = int((bb[0] + bb[2]) / 2 * w), int((bb[1] + bb[3]) / 2 * h)  # bbox is normalised xyxy
        kind = "clickable" if it.get("interactivity") else it.get("type", "element")
        lines.append(f'[{i}] {kind} "{str(it.get("content", "")).strip()}" @({x},{y})')
    return "\n".join(lines)


def describe_online(img: str, prompt: str, retries: int = 3) -> str:
    key = os.environ["OPENROUTER_API_KEY"]
    b64 = base64.b64encode(Path(img).read_bytes()).decode()
    body = {"model": os.getenv("OBS_ONLINE_MODEL", ONLINE_MODEL), "max_tokens": 1500,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
    url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") + "/chat/completions"
    for attempt in range(retries):
        try:
            r = post_json(url, body, {"Authorization": f"Bearer {key}"}, timeout=120)
        except urllib.error.HTTPError as e:  # 429 / 5xx on the free tier are common
            r = {"error": {"code": e.code, "message": e.read().decode(errors="replace")[:200]}}
        if "choices" in r:
            break
        err = r.get("error", {})
        if attempt + 1 == retries or err.get("code") not in (429, 500, 502, 503, 504):
            raise RuntimeError(f"OpenRouter error {err.get('code')}: {err.get('message', r)}")
        time.sleep(3 * (attempt + 1))
    text = r["choices"][0]["message"].get("content") or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def parse_regions(vlm_text: str) -> list[dict]:
    """'[name] description' lines of a VLM answer -> [{id, description}]. Header-only lines such as '[key regions]' are skipped.
    Only spaces/tabs are allowed after the bracket: a whitespace class that includes the newline would glue the next region onto the header."""
    out = []
    for m in re.finditer(r"^[ \t]*\[([A-Za-z][^\]\n]*)\][ \t]*(\S.*)$", vlm_text, re.M):
        name, desc = m.group(1).strip(), m.group(2).strip()
        if desc.startswith("["):          # a header line followed directly by another region
            continue
        out.append({"id": name, "description": desc})
    return out


def vlm_backend() -> str | None:
    want = os.getenv("OBS_VLM", "")
    if want == "local" and os.getenv("OMNIPARSER_URL"):
        return "local"
    if want == "online" and os.getenv("OPENROUTER_API_KEY"):
        return "online"
    return None


def _vlm(img: str) -> str:
    return _omniparser(img) if vlm_backend() == "local" else describe_online(img, UI_PROMPT)


def observe(req: dict, start: int = 0) -> dict:
    """Try layers from `start`; return {text, source, layer, tried, errors}. `layer` indexes LAYERS."""
    tried, errors, best, last = [], {}, {"text": "", "source": None}, start - 1
    img = (req.get("observation") or {}).get("screenshot_path")
    for idx in range(start, len(LAYERS)):
        name = LAYERS[idx]
        try:
            if name == "vlm" and not vlm_backend():
                raise RuntimeError("no VLM configured (set OBS_VLM=local+OMNIPARSER_URL or online+OPENROUTER_API_KEY)")
            if name != "a11y" and img is None:
                img = screenshot()
            text = {"a11y": _a11y, "ocr": lambda: _ocr(img), "vlm": lambda: _vlm(img)}[name]().strip()
        except Exception as e:  # layer unavailable -> fall through to the next one
            errors[name] = str(e)[:200]
            tried.append(name)
            continue
        tried.append(name)
        label = "vlm_" + vlm_backend() if name == "vlm" else name
        if name == "a11y" and browser_without_content(text):      # page content is not exposed: add OCR, page text first
            try:
                img = img or screenshot()
                nl = chr(10)
                text = ("--- page content (OCR; x,y are screen pixels) ---" + nl + _ocr(img).strip() + nl
                        + "--- browser UI (accessibility tree) ---" + nl + text)
                label = "a11y+ocr"
            except Exception as e:
                errors["a11y+ocr"] = str(e)[:200]
        last = idx
        if len(text) > len(best["text"]):  # keep the richest text seen so far
            best = {"text": text, "source": label, "layer": idx}
        if len(text) >= MIN_CHARS[name]:
            break
    return {**best, "layer": last, "tried": tried, "errors": errors, "screenshot_path": img}
