from __future__ import annotations

import json
import os
import time

from . import observe as obs
from . import policy
from .client import CLM
from .handoff import build_payload, forward


def _low_conf(decision) -> bool:
    return any(r.startswith("low confidence") for r in decision.reasons)


def _computer_use(req: dict, clm: CLM):
    """Observe cheapest-first; re-observe with a richer layer while CLM is unsure."""
    given = (req.get("observation") or {}).get("text")
    start, steps = 0, []
    while True:
        if given:
            o = {"text": given, "source": "caller", "layer": len(obs.LAYERS) - 1, "tried": []}
        else:
            o = obs.observe(req, start)
        r = {**req, "observation": {**(req.get("observation") or {}), "text": o["text"]}}
        state = policy.computer_use_state(r)
        answers = clm.system_one(state, policy.computer_use_questions())
        decision = policy.decide_computer_use(answers, r)
        steps.append({"source": o["source"], "tried": o.get("tried"), "errors": o.get("errors"), "chars": len(o["text"])})
        if not (_low_conf(decision) and not given and o["layer"] + 1 < len(obs.LAYERS)):
            return decision, answers, steps, state
        start = o["layer"] + 1


def _image_review(req: dict, clm: CLM):
    img = req.get("image", {})
    if not img.get("description") and img.get("path") and obs.vlm_backend() == "online":
        req = {**req, "image": {**img, "description": obs.describe_online(img["path"], obs.IMAGE_PROMPT)}}
    state = policy.image_state(req)
    answers = clm.system_one(state, policy.image_questions(req))
    return policy.decide_image(answers, req), answers, [], state


def log_trajectory(req: dict, state: str, answers: dict, decision: dict) -> None:
    """Opt-in (CLM_TRAJECTORY_LOG=path.jsonl): one line per step with exactly what CLM saw and answered, `label` left empty for a human.
    This is the data fine-tuning needs (calib/ft_build.py shows the format). The state contains screen text: keep the file private."""
    path = os.getenv("CLM_TRAJECTORY_LOG")
    if not path:
        return
    rec = {"ts": round(time.time(), 3), "mode": req["mode"], "task": req.get("task"), "history": req.get("history", []),
           "last_action": req.get("last_action"), "state": state, "answers": answers, "decision": decision, "label": None}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def route(req: dict, clm: CLM | None = None, send: bool = False) -> dict:
    """req: see examples/*.json. Returns {decision, clm_raw, observation_steps, main_reply?}."""
    clm = clm or CLM()
    mode = req["mode"]
    if mode == "computer_use":
        decision, answers, steps, state = _computer_use(req, clm)
    elif mode == "image_review":
        decision, answers, steps, state = _image_review(req, clm)
    else:
        raise ValueError(f"unknown mode {mode!r}")
    out = {"decision": decision.to_dict(), "clm_raw": answers, "observation_steps": steps}
    log_trajectory(req, state, answers, out["decision"])
    if send:
        out["main_reply"] = forward(build_payload(req, out["decision"], answers))
    return out
