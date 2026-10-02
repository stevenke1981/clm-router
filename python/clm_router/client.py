"""Minimal stdlib HTTP client for the clm-serve API (no pip dependency)."""
from __future__ import annotations

import json
import math
import os
import urllib.request


class CLMResponseError(ValueError):
    """The backend response cannot be used to make a decision."""


def validate_answers(answers: object, questions: dict) -> dict:
    if not isinstance(answers, dict):
        raise CLMResponseError("CLM response must contain an answers object")
    for name, question in questions.items():
        answer = answers.get(name)
        if not isinstance(answer, dict):
            raise CLMResponseError(f"CLM response is missing answer {name!r}")
        if question.get("type") == "noul":
            value = answer.get("noul")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise CLMResponseError(f"CLM answer {name!r} must contain a finite noul probability in [0, 1]")
    return answers


def post_json(url: str, body: dict, headers: dict | None = None, timeout: float = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class CLM:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base = (base_url or os.getenv("CLM_URL", "http://127.0.0.1:8700")).rstrip("/")
        self.timeout = float(timeout if timeout is not None else os.getenv("CLM_TIMEOUT", "60"))
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("CLM_TIMEOUT must be a positive finite number of seconds")

    def rank(self, context: str, answers: list, question: str = "") -> list:
        """Rank concrete candidates against a state: [{rank, candidate, prob}] best first (POST /v1/rank, CLM's native use)."""
        return post_json(f"{self.base}/v1/rank", {"context": context, "question": question, "answers": answers}, timeout=self.timeout)["ranked"]

    def system_one(self, state: str, questions: dict, temperature: float = 1.0) -> dict:
        r = post_json(
            f"{self.base}/v1/systemone",
            {"state": state, "questions": questions, "model": "clm-latest", "temperature": temperature},
            timeout=self.timeout,
        )
        return validate_answers(r.get("answers") if isinstance(r, dict) else None, questions)
