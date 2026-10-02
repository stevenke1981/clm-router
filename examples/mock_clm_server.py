"""Fake clm-serve for offline testing: python examples/mock_clm_server.py [port]

Answers are keyword-driven so the example requests give deterministic routes.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


def answer(state: str, questions: dict) -> dict:
    s = state.lower()
    out = {}
    for name, q in questions.items():
        if q["type"] == "choice":
            keys = list(q["criteria"])
            pick = keys[0]
            if "allow this app to make changes" in s:
                pick = "ask_user" if "ask_user" in keys else pick
            if "8-s" in s:
                pick = "local_edit"
            out[name] = {"choice": pick, "probabilities": {k: (0.9 if k == pick else 0.1 / max(1, len(keys) - 1)) for k in keys},
                         "confidence": 0.9}
        else:
            p = 0.1
            if name == "risky" and "make changes" in s:
                p = 0.85
            if name == "text_fault" and "8-s" in s:
                p = 0.9
            if name == "region:headline" and "8-s" in s:
                p = 0.95
            if name == "last_action_ok":
                p = 0.9
            out[name] = {"noul": p}
    return out


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.startswith("/parse"):  # fake OmniParser
            out = {"parsed_content_list": [{"type": "icon", "bbox": [0.1, 0.1, 0.2, 0.2], "interactivity": True, "content": "Install button"}]}
        elif self.path.endswith("/chat/completions"):  # fake OpenRouter
            text = '<think>x</think>Button "Install" @(100,200)\nSTATE: installer'
            out = {"choices": [{"message": {"content": text}}]}
        else:
            out = {"answers": answer(body["state"], body["questions"])}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8700), H).serve_forever()
