"""Shared text-only tool API for MCP and agents with shell/skill support."""
from __future__ import annotations

import argparse
import json
import sys

from . import policy
from .client import CLM
from .router import route


def _text(value, name, *, required=False):
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{name} must be {'a non-empty' if required else 'a'} string")


def _strings(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError(f"{name} must be an array of strings")


def gate_request(task, screen_text, history=None, last_action="", prev_screen_text="", platform="windows"):
    _text(task, "task", required=True)
    _text(screen_text, "screen_text", required=True)
    _text(last_action, "last_action")
    _text(prev_screen_text, "prev_screen_text")
    _strings(history if history is not None else [], "history")
    if platform not in ("windows", "linux"):
        raise ValueError("platform must be windows or linux")
    observation = {"text": screen_text}
    if prev_screen_text:
        observation["prev_text"] = prev_screen_text
    return {"mode": "computer_use", "platform": platform, "task": task, "history": history or [],
            "last_action": last_action or "(none)", "observation": observation}


def image_request(brief, criteria, description, regions=None):
    _text(brief, "brief", required=True)
    _text(description, "description", required=True)
    _strings(criteria, "criteria")
    if regions is not None and not isinstance(regions, list):
        raise ValueError("regions must be an array")
    regs, ids = [], set()
    for r in regions or []:
        if not isinstance(r, dict):
            raise ValueError("each region must be an object")
        rid = r.get("id")
        if isinstance(rid, bool) or not isinstance(rid, (str, int)) or not str(rid).strip():
            raise ValueError("region id must be a non-empty string or integer")
        rid = str(rid)
        _text(r.get("description"), "region description", required=True)
        if rid in ids:
            raise ValueError(f"duplicate region id: {rid}")
        ids.add(rid)
        regs.append({"id": rid, "description": r["description"]})
    return {"mode": "image_review", "task": brief,
            "image": {"brief": brief, "criteria": criteria, "description": description, "regions": regs}}


def summarize(out):
    d = out["decision"]
    result = {"action": d["action"], "route": d["route"], "confidence": round(d["confidence"], 3), "reasons": d["reasons"]}
    if "meets" in d["details"]:
        result.update(targets=d["targets"], **d["details"])
    else:
        result.update(scores={k: round(v["noul"], 3) for k, v in out["clm_raw"].items() if "noul" in v},
                      thresholds={"risky": policy.RISKY_T, "stuck": policy.STUCK_T, "done": policy.DONE_T})
    return result


def call_tool(name: str, arguments: dict, clm: CLM | None = None) -> dict:
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be a JSON object")
    builders = {"clm_gate": gate_request, "clm_review_image": image_request}
    if name not in builders:
        raise ValueError(f"unknown tool: {name}")
    return summarize(route(builders[name](**arguments), clm))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Text-only CLM tools; never captures the screen or forwards to a main model")
    parser.add_argument("tool", choices=["clm_gate", "clm_review_image"])
    parser.add_argument("input", help="UTF-8 JSON arguments file, or - for stdin")
    args = parser.parse_args(argv)
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        if args.input == "-":
            arguments = json.load(sys.stdin)
        else:
            with open(args.input, encoding="utf-8-sig") as f:
                arguments = json.load(f)
        result = call_tool(args.tool, arguments)
    except (ValueError, TypeError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
