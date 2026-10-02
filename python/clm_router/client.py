"""Minimal stdlib HTTP client for the clm-serve API (no pip dependency)."""
from __future__ import annotations

import json
import os
import urllib.request


def post_json(url: str, body: dict, headers: dict | None = None, timeout: float = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class CLM:
    def __init__(self, base_url: str | None = None):
        self.base = (base_url or os.getenv("CLM_URL", "http://127.0.0.1:8700")).rstrip("/")

    def rank(self, context: str, answers: list, question: str = "") -> list:
        """Rank concrete candidates against a state: [{rank, candidate, prob}] best first (POST /v1/rank, CLM's native use)."""
        return post_json(f"{self.base}/v1/rank", {"context": context, "question": question, "answers": answers})["ranked"]

    def system_one(self, state: str, questions: dict, temperature: float = 1.0) -> dict:
        r = post_json(
            f"{self.base}/v1/systemone",
            {"state": state, "questions": questions, "model": "clm-latest", "temperature": temperature},
        )
        return r["answers"]
