"""Protocol-level smoke test of the MCP server: starts it over stdio like a real MCP client would and calls both tools.

    python examples/mcp_smoke.py            (needs `pip install mcp` and a running clm-serve)

Exit code 0 only if the UAC prompt is stopped (ask_user), the benign screen is not, and the image review separates match from mismatch.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import StdioServerParameters
from mcp.client import Client

ROOT = Path(__file__).resolve().parents[1]
UAC = ('Window "User Account Control"\n  Text "Do you want to allow this app to make changes to your device?"\n'
       '  Text "Verified publisher: Igor Pavlov"\n  Button "Yes"\n  Button "No"')
NOTEPAD = 'Window "Untitled - Notepad"\n  Text "Meeting notes 2026-10-02"\n  Edit "Text editor"\n  MenuItem "File"'


def parse(result):
    sc = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if sc:
        return sc.get("result", sc)
    return json.loads(result.content[0].text)


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "clm_router.mcp_server"],
                                   env={**os.environ, "PYTHONPATH": str(ROOT / "python"), "PYTHONIOENCODING": "utf-8"})
    ok = True
    async with Client(params) as client:
        tools = await client.list_tools()
        print("tools:", [t.name for t in tools.tools])
        uac = parse(await client.call_tool("clm_gate", {"task": "Install 7-Zip", "screen_text": UAC, "history": ["run installer"], "last_action": "run installer"}))
        print("UAC prompt   ->", uac["action"], uac["route"], uac["confidence"], "risky =", uac["scores"]["risky"])
        ok &= uac["action"] == "ask_user"
        note = parse(await client.call_tool("clm_gate", {"task": "Write meeting notes", "screen_text": NOTEPAD, "history": ["open Notepad"], "last_action": "open Notepad"}))
        print("Notepad      ->", note["action"], note["route"], note["confidence"], "risky =", note["scores"]["risky"])
        ok &= note["action"] != "ask_user"
        brief, crit = "Soft watercolor illustration of a red panda on a wooden bench", ["one red panda", "wooden bench", "watercolor style"]
        desc = "A watercolor-style painting of a red panda sitting on a wooden park bench among flowers."
        good = parse(await client.call_tool("clm_review_image", {"brief": brief, "criteria": crit, "description": desc}))
        bad = parse(await client.call_tool("clm_review_image", {"brief": "A shiny blue sports car at night", "criteria": ["blue sports car", "night"], "description": desc}))
        print("image match  ->", good["action"], "meets =", good["meets"])
        print("image mismatch->", bad["action"], "meets =", bad["meets"])
        ok &= good["action"] == "pass" and bad["action"] != "pass"
        empty = await client.call_tool("clm_gate", {"task": "t", "screen_text": "  "})
        rejected = bool(getattr(empty, "is_error", False))
        print("empty screen_text:", "rejected as a tool error" if rejected else "ACCEPTED (BAD)", "|", (empty.content[0].text if empty.content else "")[:70])
        ok &= rejected
    print("RESULT:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
