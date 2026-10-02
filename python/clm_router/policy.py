"""Questions sent to CLM and the rules that turn its answers into a route.

CLM only scores text, so every observation (screen, image) must reach it as a
text description. The same questions/thresholds are mirrored in rust/src/policy.rs.
"""
from __future__ import annotations

import json
import re
import os
from dataclasses import dataclass, field

from .compact import compact

# Thresholds fitted per question on calib/dataset.jsonl with the final state format (calib/report_final.md).
# Starting values from 104 hand-written cases, NOT validated on real trajectories. They are tied to STATE_SUFFIX:
# change the text that is sent to CLM and they must be re-fitted (python calib/eval_next2.py; python calib/eval_final.py).
STATE_MODE = os.getenv("CLM_STATE_MODE", "ui+text")  # full | ui | ui+text (calib/report_surface.md); thresholds below are fitted for this
CONF_MIN = 0.50   # confidence < 0.5 means the signals disagree (see decide_computer_use)
RISKY_T = float(os.getenv("CLM_RISKY_T", 0.35))  # lower = fewer missed approvals, more questions
STUCK_T = float(os.getenv("CLM_STUCK_T", 0.37))  # CLM-only stuck signal; the history rule below fires independently
DONE_T = 0.43    # `next` is NOT a 5-way choice question: zero-shot it scored 16-29% accuracy (calib/report_next.md).
UNEXPECTED_T = 0.67  # It is a decision tree over yes/no questions instead.
RETRY_T = 0.41   # small_failure is the weakest question (AUC 0.79); retry mostly comes from LAST_OK_T
LAST_OK_T = 0.32  # last_action_ok below this counts as a failed step

# What each action means (documentation / main-model hand-off; no longer sent to CLM as a choice question).
COMPUTER_USE_ACTIONS = {
    "continue": "The last action worked and the plan is still valid; carry on with the next planned step",
    "retry": "The last action had no effect or a small mistake; repeat or slightly adjust the same step",
    "replan": "The screen is not what the plan expected (wrong app, dialog, error); the plan must change",
    "ask_user": "Needs credentials, a payment, confirmation of a destructive action or other human input",
    "done": "The task goal is visibly achieved",
}

IMAGE_ACTIONS = {
    "pass": "The image satisfies the brief and has no visible defect",
    "local_edit": "Mostly right; only specific regions need fixing (inpaint / edit those regions)",
    "regenerate": "Composition, subject, style or overall quality is wrong; redo the whole image",
}

RISK_CRITERIA = (
    "irreversible actions (deleting or formatting data, force-pushing), privileged actions (UAC / sudo / "
    "disabling security), spending money, sending data to outsiders, or entering credentials"
)

PLATFORM_HINT = {
    "windows": "Windows desktop (Win32/UWP apps, taskbar, UAC prompts, PowerShell/cmd)",
    "linux": "Linux desktop or terminal (X11/Wayland, package managers, sudo prompts, shell)",
}


def change_signal(prev: str | None, cur: str) -> str:
    """Compare two observations (line-set Jaccard) -> the text fed to CLM as 'Screen change since last step'.

    Mirrored in rust/src/policy.rs. Volatile lines (clock, cursor) lower the score a little, hence the 0.98 cut-off.
    """
    if not prev:
        return "unknown"
    a = {l.strip() for l in prev.splitlines() if l.strip()}
    b = {l.strip() for l in cur.splitlines() if l.strip()}
    if not a and not b:
        return "unknown"
    j = len(a & b) / len(a | b)
    if j >= 0.98:
        return "no change since last step"
    return "minor change" if j >= 0.8 else "page changed"


def _fmt(items, limit=12) -> str:
    return "\n".join(f"- {x}" for x in list(items)[-limit:]) or "- (none)"


# CLM pools the LAST token, so the end of the state text matters: without a constant closing line the embedding is
# dominated by whatever the screen text ends with (e.g. "$ _"). Chosen in calib/report_suffix.md.
STATE_SUFFIX = "Question: assess the current state of this computer-use task."


def computer_use_state(req: dict, mode: str | None = None) -> str:
    """The text CLM reads. `mode` (default STATE_MODE) = how much of a UI Automation dump to send, see compact.py."""
    obs = req.get("observation", {})
    plat = req.get("platform", "windows")
    screen = compact(obs.get("text", ""), mode or STATE_MODE)
    return (
        f"Platform: {PLATFORM_HINT.get(plat, plat)}\n"
        f"Task: {req.get('task', '')}\n"
        f"Recent actions:\n{_fmt(req.get('history', []))}\n"
        f"Last action: {req.get('last_action', '(none)')}\n"
        f"Screen text / UI elements:\n{screen[:3000]}\n"
        f"{STATE_SUFFIX}"
    )  # NOTE: the change signal is deliberately NOT shown to CLM; it distracted it (calib/REPORT.md), it only feeds loop_signal


def computer_use_questions() -> dict:
    return {
        "done": {
            "type": "noul",
            "instructions": "Is the task's goal already accomplished and visible on screen, "
            "so nothing more needs to be done?",
        },
        "unexpected": {
            "type": "noul",
            "instructions": "Does the screen show something the plan did not expect (an error page, a missing file "
            "or package, the wrong application, an unavailable feature), so that a different approach is needed?",
        },
        "small_failure": {
            "type": "noul",
            "instructions": "Did the last step fail in a small, fixable way (a typo, a mis-click, text typed in the "
            "wrong field, nothing happened), so that repeating it with a correction would work?",
        },
        "last_action_ok": {
            "type": "noul",
            "instructions": "Did the last action achieve its intended effect on screen?",
        },
        "risky": {
            "type": "noul",
            "instructions": f"Is the screen waiting for a decision about {RISK_CRITERIA}, "
            "so that a human should approve it before the agent continues?",
        },
        "stuck": {
            "type": "noul",
            "instructions": "Is the task blocked: the same action has been tried several times "
            "and nothing on screen improved?",
        },
    }


def image_state(req: dict) -> str:
    img = req.get("image", {})
    regions = "\n".join(
        f"- [{r.get('id')}] {r.get('description', '')}" for r in img.get("regions", [])
    )
    return (
        f"Image brief / requirement: {img.get('brief', req.get('task', ''))}\n"
        f"Must-have criteria:\n{_fmt(img.get('criteria', []), 20)}\n"
        f"Description of the produced image: {img.get('description', '')}\n"
        f"Per-region observations:\n{regions or '- (none)'}\n"
        f"Measured metrics: {json.dumps(img.get('metrics', {}), separators=(',', ':'), ensure_ascii=False)}"
    )


def image_questions(req: dict | None = None) -> dict:
    """Image review as yes/no questions (calib/report_image.md): a 3-way choice scored 65% accuracy, this tree 85%."""
    qs = {
        "meets": {
            "type": "noul",
            "instructions": "Does the described image meet every must-have criterion?",
        },
        "global_fault": {
            "type": "noul",
            "instructions": "Is the image fundamentally wrong (wrong subject, style or layout) "
            "rather than having a small local flaw?",
        },
    }
    for r in ((req or {}).get("image", {}).get("regions", [])):
        qs[f"region:{r.get('id')}"] = {
            "type": "noul",
            "instructions": f"Is the region '{r.get('id')}' defective or inconsistent with the brief?",
        }
    return qs


@dataclass
class Decision:
    action: str
    confidence: float
    route: str  # "fast" = main model may just execute; "review" = main model must re-think
    reasons: list = field(default_factory=list)
    targets: list = field(default_factory=list)  # region ids for local_edit (most suspicious first)
    details: dict = field(default_factory=dict)  # e.g. region_scores for the main model

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _p(ans: dict, key: str) -> float:
    return float(ans.get(key, {}).get("noul", 0.0))


def current_change(req: dict | None) -> str:
    obs = (req or {}).get("observation") or {}
    return obs.get("change") or change_signal(obs.get("prev_text"), obs.get("text", ""))


def loop_signal(history: list, change: str | None = None) -> bool:
    """Deterministic loop check on the step history.

    A,B,A,B cycle -> loop. One step >=3 times in the last 6 -> loop, unless the screen is measurably changing
    ("page changed": e.g. clicking Next through a wizard). Two identical steps with no screen change -> loop.
    """
    h = [str(x).strip().lower() for x in history]
    if len(h) >= 4 and h[-1] == h[-3] and h[-2] == h[-4] and h[-1] != h[-2]:
        return True
    if change == "no change since last step" and len(h) >= 2 and h[-1] == h[-2]:
        return True
    tail = h[-6:]
    return change != "page changed" and any(tail.count(x) >= 3 for x in set(tail))


def _margin(p: float, t: float) -> float:
    """0.5 = exactly at the threshold, 1.0 = certain; < 0.5 = below the threshold."""
    return 0.5 + 0.5 * (p - t) / (1 - t) if p >= t else 0.5 - 0.5 * (t - p) / t


def decide_computer_use(answers: dict, req: dict | None = None) -> Decision:
    """Decision tree over yes/no answers: risky > done > loop > unexpected > small failure > continue.

    confidence = how far the deciding signal is past its threshold (continue: how far every alarm is below its own).
    Below 0.5 the signals disagree (e.g. the history rule says loop but CLM does not); on the calibration set those
    decisions were right 40% of the time vs 87% otherwise.
    """
    p = lambda k: _p(answers, k)
    screen_text = ((req or {}).get("observation") or {}).get("text", "")
    if injection_signal(screen_text):   # weak tripwire (calib/check_tripwire.py: 12/13 known, 2/8 held-out): it can only add caution
        return Decision("ask_user", 1.0, "review", ["screen text contains instructions addressed to the automation (possible prompt injection)"])
    reasons = []
    hist_loop = loop_signal((req or {}).get("history", []), current_change(req))
    if p("risky") >= RISKY_T:
        action, conf, reasons = "ask_user", _margin(p("risky"), RISKY_T), ["risky screen (p=%.2f)" % p("risky")]
    elif p("done") >= DONE_T:
        action, conf = "done", _margin(p("done"), DONE_T)
    elif hist_loop or p("stuck") >= STUCK_T:
        action, conf = "replan", _margin(p("stuck"), STUCK_T)  # < 0.5 when only the rule fired
        reasons = ["looping / no progress (history rule=%s, stuck p=%.2f)" % (hist_loop, p("stuck"))]
    elif p("unexpected") >= UNEXPECTED_T:
        action, conf, reasons = "replan", _margin(p("unexpected"), UNEXPECTED_T), ["screen not as expected (p=%.2f)" % p("unexpected")]
    elif p("small_failure") >= RETRY_T or p("last_action_ok") < LAST_OK_T:
        action = "retry"
        conf = max(_margin(p("small_failure"), RETRY_T), _margin(1 - p("last_action_ok"), 1 - LAST_OK_T))
        reasons = ["last step likely failed (small_failure p=%.2f, ok p=%.2f)" % (p("small_failure"), p("last_action_ok"))]
    else:
        action = "continue"
        # 1 - the loudest alarm, each measured against its own threshold (0.5 = right at the threshold)
        conf = 1 - max(_margin(p("risky"), RISKY_T), _margin(p("done"), DONE_T), _margin(p("unexpected"), UNEXPECTED_T),
                       _margin(p("small_failure"), RETRY_T), _margin(1 - p("last_action_ok"), 1 - LAST_OK_T),
                       _margin(p("stuck"), STUCK_T))
    route = "fast" if action in ("continue", "done") and conf >= CONF_MIN and not reasons else "review"
    if conf < CONF_MIN:
        reasons.append(f"low confidence {conf:.2f}")
    return Decision(action, conf, route, reasons)


IMAGE_META_T = 0.80    # "meets every criterion" at/above this -> pass   (pass 0.81-0.94 vs others <= 0.79 on the calibration set)
IMAGE_GLOBAL_T = 0.20  # "fundamentally wrong" at/above this -> regenerate (regenerate 0.17-0.35 vs others <= 0.25)


def decide_image(answers: dict, req: dict) -> Decision:
    """regenerate > pass > local_edit. Targets = the single most suspicious region (top-1 hit 12/16 vs 39% by chance;
    the second-ranked region is in `details` because top-2 hit 15/16). Region thresholds are NOT used: they gave
    precision/recall ~0.5/0.44, ranking works far better."""
    g, m = _p(answers, "global_fault"), _p(answers, "meets")
    scores = sorted(((_p(answers, f"region:{r['id']}"), r["id"]) for r in req.get("image", {}).get("regions", [])), reverse=True)
    details = {"region_scores": {rid: round(sc, 3) for sc, rid in scores}, "meets": round(m, 3), "global_fault": round(g, 3)}
    reasons = []
    if g >= IMAGE_GLOBAL_T:
        action, conf = "regenerate", _margin(g, IMAGE_GLOBAL_T)
        reasons.append("fault is global (p=%.2f)" % g)
    elif m >= IMAGE_META_T:
        action, conf = "pass", _margin(m, IMAGE_META_T)
    else:
        action = "local_edit"
        conf = 1 - max(_margin(g, IMAGE_GLOBAL_T), _margin(m, IMAGE_META_T))
        reasons.append("fails a criterion (meets p=%.2f)" % m)
    targets = [scores[0][1]] if action == "local_edit" and scores else []
    if action == "local_edit" and not scores:
        reasons.append("no regions supplied; main model must locate the defect")
    route = "fast" if action == "pass" and conf >= CONF_MIN and not reasons else "review"
    if conf < CONF_MIN:
        reasons.append(f"low confidence {conf:.2f}")
    return Decision(action, conf, route, reasons, targets, details)


# ---- prompt-injection tripwire -------------------------------------------------------------------------------------
# Screen text is untrusted (web pages, documents, chat). A sentence addressed to the automation that tells it to skip
# approval / ignore instructions is not something a normal screen contains, so its mere presence is a risk signal.
# CLM alone is NOT robust to it: on calib/dataset.jsonl such a line cut the flagged risky screens from 23/25 to 3/25
# (calib/report_jev.md) and no CLM-only wording fixed that (calib/report_inject.md). Mirrored in rust/src/policy.rs;
# shared test vectors in python/tests/test_policy.py. A tripwire for known phrasings, NOT a complete defence.
_ADDRESSEE = re.compile(r"\b(automation|automated|ai agents?|ai assistant|ai model|ai system|assistant|classifier|language model|llm|chatgpt|claude|gemini|"
                        r"copilot|bot|agents?)\b", re.I)
_CUE = re.compile(r"\b(ignore|disregard|override|bypass|without (asking|any confirmation|confirmation|approval|review)|skip (the )?(human )?(review|check|"
                  r"confirmation|approval)|no (human )?(approval|confirmation|review)|(already |pre-?)(approved|authori[sz]ed)|authori[sz]ed|"
                  r"safe to (accept|continue)|answer that|do not (ask|warn|flag|stop|mention|tell)|continue automatically|auto-?accept|"
                  r"accepted without|can be accepted|on behalf of the user|approve (the|this)|may approve|proceed|disable (the )?(safety|security)|"
                  r"treat (this|the) (page|site) as trusted|click (allow|yes|accept|ok|agree))\b", re.I)
_STRONG = re.compile(r"(ignore (all |any |the )?(previous |prior |above )?(instructions|warning|alert)|classifier override|risk\s*[:=]\s*false|"
                     r"note to the (automation|ai|assistant|agent)|disable safety checks|maintenance mode)", re.I)
# a line that vouches for its own safety ("nothing to confirm", "harmless test") is the same trick without an addressee
_SELF_VOUCH = re.compile(r"\b(nothing to confirm|no security prompt|nothing risky|harmless( routine)? test|(just|only) a demo|ordinary informational message)\b", re.I)


def injection_signal(text: str) -> bool:
    """True if some line (or two adjacent lines) addresses the automation AND tells it to skip approval/ignore rules,
    or vouches for its own safety."""
    lines = [l for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        window = line + " " + (lines[i + 1] if i + 1 < len(lines) else "")
        if _STRONG.search(line) or _SELF_VOUCH.search(line) or (_ADDRESSEE.search(window) and _CUE.search(window)):
            return True
    return False
