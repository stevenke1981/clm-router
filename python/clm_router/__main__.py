import argparse
import json
import sys

from .router import route

ap = argparse.ArgumentParser(prog="clm_router")
ap.add_argument("input", help="request JSON file, or - for stdin")
ap.add_argument("--send", action="store_true", help="forward to the main model")
a = ap.parse_args()
req = json.load(sys.stdin if a.input == "-" else open(a.input, encoding="utf-8"))
print(json.dumps(route(req, send=a.send), ensure_ascii=False, indent=2))
