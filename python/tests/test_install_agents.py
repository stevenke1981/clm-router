import importlib.util
import json
from pathlib import Path
import sys
import pytest

tomllib = pytest.importorskip("tomllib", reason="agent installer requires Python 3.11+")

spec = importlib.util.spec_from_file_location("install_agents", Path(__file__).resolve().parents[2] / "scripts/install_agents.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_install_preserves_settings_and_is_idempotent(tmp_path):
    codex = tmp_path / ".codex/config.toml"
    codex.parent.mkdir()
    original = '# keep this comment\nmodel = "custom"\n[mcp_servers.existing]\ncommand = "other"\n'
    codex.write_text(original, encoding="utf-8")
    oc = tmp_path / ".config/opencode/opencode.json"
    oc.parent.mkdir(parents=True)
    oc.write_text('{"model":"custom","mcp":{"existing":{"type":"remote","url":"http://localhost"}}}', encoding="utf-8")
    args = (tmp_path, Path(sys.executable), "http://localhost:8700", ["codex", "opencode", "pi"])
    plan = installer.build_plan(*args, use_env=False)
    installer.apply_plan(plan)
    parsed = tomllib.loads(codex.read_text(encoding="utf-8"))
    assert parsed["model"] == "custom" and parsed["mcp_servers"]["existing"]["command"] == "other"
    assert codex.read_text(encoding="utf-8").startswith(original.rstrip())
    assert json.loads(oc.read_text())["mcp"]["existing"]["url"] == "http://localhost"
    backup_count = len(list(tmp_path.rglob("*.clm-backup-*")))
    again = installer.build_plan(*args, use_env=False)
    assert plan == again
    installer.apply_plan(again)
    assert len(list(tmp_path.rglob("*.clm-backup-*"))) == backup_count == 2
    for agent in (".codex", ".config/opencode", ".pi/agent"):
        assert (tmp_path / agent / "skills/clm-router/scripts/run.py").exists()


def test_unmanaged_codex_server_is_not_overwritten():
    with pytest.raises(ValueError, match="unmanaged"):
        installer.codex_config('[mcp_servers.clm-gate]\ncommand="custom"', Path(sys.executable), "http://localhost")


def test_jsonc_conflict_is_detected_before_writing(tmp_path):
    oc = tmp_path / ".config/opencode/opencode.jsonc"
    oc.parent.mkdir(parents=True)
    oc.write_text("{// settings\n}")
    with pytest.raises(ValueError, match="competing"):
        installer.build_plan(tmp_path, Path(sys.executable), "http://localhost", ["codex", "opencode"], use_env=False)
    assert not (tmp_path / ".codex").exists()
