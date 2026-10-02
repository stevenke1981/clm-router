"""Command line entry point; importing it has no side effects."""
import argparse
import json
import sys

from .router import route


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="clm-router")
    ap.add_argument("input", help="request JSON file, or - for stdin")
    ap.add_argument("--send", action="store_true", help="forward to the main model")
    a = ap.parse_args(argv)
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        if a.input == "-":
            req = json.load(sys.stdin)
        else:
            with open(a.input, encoding="utf-8-sig") as f:
                req = json.load(f)
        result = route(req, send=a.send)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0
