"""Install CLM MCP + skills into Codex, OpenCode and Pi. Requires Python 3.11+.

Default is a dry run. --apply writes only the listed files, backing up changes.
Existing unrelated configuration is preserved. No agent clients/models are installed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "# BEGIN clm-router managed integration"
END = "# END clm-router managed integration"


def read(path):
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def codex_config(original, python, url):
    # Replace only our own section. Never rewrite another tool's TOML/comments.
    if original.count(BEGIN) != original.count(END) or original.count(BEGIN) > 1:
        raise ValueError("Malformed CLM managed block in Codex config")
    clean = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "", original, flags=re.S)
    parsed = tomllib.loads(clean)
    if "clm-gate" in parsed.get("mcp_servers", {}):
        raise ValueError("Codex already has an unmanaged clm-gate entry; rename/remove that entry before installing")
    block = f'''{BEGIN}
[mcp_servers.clm-gate]
command = {json.dumps(str(python))}
args = ["-m", "clm_router.mcp_server"]
startup_timeout_sec = 20
tool_timeout_sec = 90

[mcp_servers.clm-gate.env]
CLM_URL = {json.dumps(url)}
CLM_TIMEOUT = "60"
PYTHONIOENCODING = "utf-8"
{END}
'''
    result = clean.rstrip() + ("\n\n" if clean.strip() else "") + block
    tomllib.loads(result)
    return result


def opencode_config(original, python, url):
    config = json.loads(original) if original.strip() else {"$schema": "https://opencode.ai/config.json"}
    if not isinstance(config, dict) or not isinstance(config.get("mcp", {}), dict):
        raise ValueError("OpenCode config and mcp must be objects")
    config.setdefault("mcp", {})["clm-gate"] = {
        "type": "local", "command": [str(python), "-m", "clm_router.mcp_server"], "enabled": True,
        "timeout": 90000, "environment": {"CLM_URL": url, "CLM_TIMEOUT": "60", "PYTHONIOENCODING": "utf-8"}}
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def build_plan(user_home, python, url, agents, *, use_env=True):
    codex_dir = Path(os.getenv("CODEX_HOME") or user_home / ".codex") if use_env else user_home / ".codex"
    xdg = Path(os.getenv("XDG_CONFIG_HOME") or user_home / ".config") if use_env else user_home / ".config"
    pi_dir = Path(os.getenv("PI_CODING_AGENT_DIR") or user_home / ".pi/agent") if use_env else user_home / ".pi/agent"
    destinations = {"codex": codex_dir, "opencode": xdg / "opencode", "pi": pi_dir}
    plan = {}
    if "codex" in agents:
        path = codex_dir / "config.toml"
        plan[path] = codex_config(read(path), python, url)
    if "opencode" in agents:
        path = destinations["opencode"] / "opencode.json"
        if path.with_suffix(".jsonc").exists():
            raise ValueError(f"{path.with_suffix('.jsonc')} exists; merge the documented MCP entry there instead of creating competing config files")
        plan[path] = opencode_config(read(path), python, url)
    for agent in agents:
        dest = destinations[agent] / "skills/clm-router"
        for name in ("SKILL.md", "scripts/run.py"):
            plan[dest / name] = (ROOT / "skills/clm-router" / name).read_text(encoding="utf-8")
        plan[dest / "runtime.json"] = json.dumps({"python": str(python), "clm_url": url}, indent=2) + "\n"
    return plan


def apply_plan(plan):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for path, content in plan.items():
        if path.exists() and path.read_bytes() == content.encode("utf-8"):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".clm-backup-" + stamp))
        fd, tmp = tempfile.mkstemp(prefix=".clm-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, help="target user directory; ignores agent path environment overrides")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--clm-url", default="http://127.0.0.1:8700")
    parser.add_argument("--agents", nargs="+", choices=["codex", "opencode", "pi"], default=["codex", "opencode", "pi"])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        python = args.python.resolve(strict=True)
        # Verify the configured interpreter works even outside the repository.
        subprocess.run([str(python), "-c", "import clm_router.tools; import clm_router.mcp_server"],
                       cwd=python.parent, check=True, capture_output=True, timeout=30)
        plan = build_plan(args.home or Path.home(), python, args.clm_url, args.agents, use_env=args.home is None)
        for path, content in plan.items():
            unchanged = path.exists() and path.read_bytes() == content.encode("utf-8")
            print(f"{'unchanged' if unchanged else 'write' if args.apply else 'would write'}: {path}")
        if args.apply:
            apply_plan(plan)
        else:
            print("Dry run. Add --apply to install; existing changed files receive .clm-backup-* backups.")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
