"""Usage C for models without MCP: the CLM gate as a plain function-calling tool (see docs/03-tool-mcp.md).

    cd python && python ../examples/function_calling.py

TOOL_SPEC_* are the definitions to hand to the model API; handle_tool_call() runs a call the model made. No network access to a model
is needed to try it: the demo at the bottom plays the part of the model's tool call.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from clm_router import route  # noqa: E402

PARAMS = {
    "type": "object",
    "required": ["task", "screen_text"],
    "properties": {
        "task": {"type": "string", "description": "what the agent is trying to achieve"},
        "screen_text": {"type": "string", "description": "visible text / UI element names of the current screen (never empty)"},
        "history": {"type": "array", "items": {"type": "string"}, "description": "recent actions, oldest first"},
        "last_action": {"type": "string"},
        "prev_screen_text": {"type": "string", "description": "screen text before the last action (lets the gate see 'nothing changed')"},
    },
}
DESCRIPTION = ("Judge the current GUI screen BEFORE the next action. Returns action (ask_user | replan | retry | continue | done), route (fast | review), "
               "confidence and reasons. ask_user means stop and ask the human; continue is not permission for anything irreversible.")

TOOL_SPEC_ANTHROPIC = {"name": "clm_gate", "description": DESCRIPTION, "input_schema": PARAMS}                       # client.messages.create(tools=[...])
TOOL_SPEC_OPENAI = {"type": "function", "function": {"name": "clm_gate", "description": DESCRIPTION, "parameters": PARAMS}}  # chat.completions.create(tools=[...])


def handle_tool_call(name: str, arguments: dict) -> str:
    """Run one tool call and return the string to send back as the tool result."""
    if name != "clm_gate":
        return json.dumps({"error": f"unknown tool {name}"})
    if not arguments.get("screen_text", "").strip():
        return json.dumps({"error": "screen_text must not be empty"})          # never fall back to capturing the screen
    obs = {"text": arguments["screen_text"]}
    if arguments.get("prev_screen_text"):
        obs["prev_text"] = arguments["prev_screen_text"]
    d = route({"mode": "computer_use", "task": arguments["task"], "history": arguments.get("history", []),
               "last_action": arguments.get("last_action", "(none)"), "observation": obs})["decision"]
    return json.dumps({k: d[k] for k in ("action", "route", "confidence", "reasons")}, ensure_ascii=False)


if __name__ == "__main__":
    call = {"task": "Free up disk space", "history": ["open terminal", "type sudo apt autoremove"], "last_action": "press Enter",
            "screen_text": "The following packages will be REMOVED:\n  ubuntu-desktop gdm3 gnome-shell (+212 more)\nDo you want to continue? [Y/n]"}
    print("model asks for clm_gate with:", json.dumps(call)[:110], "...")
    print("tool result:", handle_tool_call("clm_gate", call))
