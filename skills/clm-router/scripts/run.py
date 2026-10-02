"""Run the installed CLM text-only tool without depending on the shell's PATH."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    config = Path(__file__).resolve().parents[1] / "runtime.json"
    if not config.is_file():
        print("CLM skill is not installed: run scripts/install_agents.py with the project Python", file=sys.stderr)
        return 1
    settings = json.loads(config.read_text(encoding="utf-8"))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "CLM_URL": settings["clm_url"]}
    try:
        return subprocess.run([settings["python"], "-m", "clm_router.tools", *sys.argv[1:]], env=env).returncode
    except OSError as exc:
        print(f"CLM Python unavailable: {exc}. Re-run scripts/install_agents.py.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
