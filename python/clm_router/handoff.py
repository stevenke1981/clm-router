"""Forward the CLM verdict + original context to the main model.

Provider is chosen by env so any model name works (Sonnet, GPT, ...):
  MAIN_PROVIDER = anthropic | openai   (openai = any OpenAI-compatible /chat/completions)
  MAIN_MODEL, MAIN_BASE_URL (optional), ANTHROPIC_API_KEY / OPENAI_API_KEY
"""
from __future__ import annotations

import json
import os

from .client import post_json


def _check(r: dict) -> dict:
    if "error" in r:
        e = r["error"]
        raise RuntimeError(f"main model error: {e.get('message', e) if isinstance(e, dict) else e}")
    return r

SYSTEM = (
    "You are the main agent. A fast contrastive pre-screener (CLM) already judged the "
    "current state. Treat its verdict as a strong hint, not an order: if route=fast, "
    "just execute the suggested action; if route=review, re-check the evidence first. "
    "For image_review local_edit, decision.targets is the single most suspicious region and details.region_scores ranks "
    "all regions (the true defect was in the top 2 in 15 of 16 calibration cases): verify before editing. "
    "Reply with the concrete next step as JSON."
)


def build_payload(req: dict, decision: dict, answers: dict) -> dict:
    return {"mode": req["mode"], "task": req.get("task"), "clm_decision": decision,
            "clm_raw": answers, "context": {k: v for k, v in req.items() if k != "mode"}}


def forward(payload: dict) -> str:
    provider = os.getenv("MAIN_PROVIDER", "anthropic")
    model = os.environ["MAIN_MODEL"]
    user = json.dumps(payload, ensure_ascii=False)
    if provider == "anthropic":
        base = os.getenv("MAIN_BASE_URL", "https://api.anthropic.com")
        r = post_json(
            f"{base}/v1/messages",
            {"model": model, "max_tokens": 1024, "system": SYSTEM,
             "messages": [{"role": "user", "content": user}]},
            {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
            timeout=120,
        )
        return "".join(b.get("text", "") for b in _check(r)["content"])
    base = os.getenv("MAIN_BASE_URL", "https://api.openai.com/v1")
    r = post_json(
        f"{base}/chat/completions",
        {"model": model, "messages": [{"role": "system", "content": SYSTEM},
                                      {"role": "user", "content": user}]},
        {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
        timeout=120,
    )
    return _check(r)["choices"][0]["message"]["content"]
