import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from clm_router import router, tools


def test_text_tools_never_auto_observe(monkeypatch):
    monkeypatch.setattr("clm_router.observe.observe", lambda *a: pytest.fail("unexpected screen capture"))
    with pytest.raises(ValueError, match="screen_text"):
        tools.call_tool("clm_gate", {"task": "t", "screen_text": "  "})


def test_region_zero_is_retained_and_duplicates_are_rejected():
    r = tools.image_request("poster", [], "bad headline", [{"id": 0, "description": "typo"}])
    assert r["image"]["regions"][0]["id"] == "0"
    with pytest.raises(ValueError, match="duplicate"):
        tools.image_request("poster", [], "bad", [{"id": 0, "description": "typo"}, {"id": "0", "description": "other"}])


@pytest.mark.parametrize("extra", [{"history": "abc"}, {"history": [3]}, {"platform": "invalid"}, {"last_action": None}])
def test_rejects_bad_tool_arguments(extra):
    with pytest.raises(ValueError):
        tools.gate_request("task", "screen", **extra)


def test_no_observation_does_not_call_backend(monkeypatch):
    monkeypatch.setattr("clm_router.observe.observe", lambda *a: {"text": "", "layer": 2})
    class Never:
        def system_one(self, *a):
            pytest.fail("backend called with no evidence")
    with pytest.raises(ValueError, match="No screen text"):
        router.route({"mode": "computer_use"}, Never())
    with pytest.raises(ValueError, match="No image description"):
        router.route({"mode": "image_review", "image": {}}, Never())


def test_tool_cli_invalid_input_has_json_error_and_nonzero_exit(tmp_path):
    path = tmp_path / "args.json"
    path.write_text(json.dumps({"task": "筆記", "screen_text": ""}), encoding="utf-8-sig")
    result = subprocess.run([sys.executable, "-m", "clm_router.tools", "clm_gate", str(path)],
                            capture_output=True, encoding="utf-8", cwd=tmp_path,
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    assert result.returncode == 1 and not result.stdout
    assert "screen_text" in json.loads(result.stderr)["error"]
