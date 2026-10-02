from clm_router import observe, router


class FakeCLM:
    """Disagrees with the history rule on a poor observation (stuck p low), agrees once it sees more text."""
    def __init__(self):
        self.calls = []

    def system_one(self, state, questions):
        self.calls.append(state)
        stuck = 0.9 if "RICH" in state else 0.05
        return {k: {"noul": v} for k, v in dict(risky=0.1, done=0.1, unexpected=0.1, small_failure=0.1,
                                                 stuck=stuck, last_action_ok=0.9).items()}


def test_escalates_when_signals_disagree(monkeypatch):
    seen = []

    def fake_observe(req, start=0):
        seen.append(start)
        return ({"text": "x", "source": "a11y", "layer": 0, "tried": ["a11y"]} if start == 0
                else {"text": "RICH ocr text", "source": "ocr", "layer": 1, "tried": ["ocr"]})

    monkeypatch.setattr(observe, "observe", fake_observe)
    out = router.route({"mode": "computer_use", "task": "t", "history": ["a", "a", "a"]}, FakeCLM())
    assert seen == [0, 1] and out["decision"]["action"] == "replan"
    assert [s["source"] for s in out["observation_steps"]] == ["a11y", "ocr"]


def test_caller_text_is_never_re_observed(monkeypatch):
    monkeypatch.setattr(observe, "observe", lambda *a, **k: 1 / 0)
    out = router.route({"mode": "computer_use", "task": "t", "observation": {"text": "hi"}}, FakeCLM())
    assert out["observation_steps"][0]["source"] == "caller"


def test_vlm_needs_explicit_config(monkeypatch):
    monkeypatch.delenv("OBS_VLM", raising=False)
    assert observe.vlm_backend() is None
    monkeypatch.setenv("OBS_VLM", "online")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert observe.vlm_backend() == "online"


def test_parse_regions_skips_header_and_does_not_swallow_next_line():
    nl = chr(10)
    text = "Summary text." + nl + "[key regions]" + nl + "[red panda] A cute red panda." + nl + "  [bench] A wooden bench." + nl + "no bracket here"
    assert observe.parse_regions(text) == [{"id": "red panda", "description": "A cute red panda."},
                                           {"id": "bench", "description": "A wooden bench."}]
    assert observe.parse_regions("[0] A cartoon of a boy.") == []   # a numeric index is not a region name


def test_browser_without_document_needs_ocr():
    nl = chr(10)
    chrome_ui = 'Window "Google Flow - Google Chrome" @(0,0,10x10)' + nl + '  Button "x" @(1,1,1x1)'
    assert observe.browser_without_content(chrome_ui)
    empty_doc = chrome_ui + nl + '    Document "Flow" @(0,0,1x1)' + nl + '    Button "tab" @(0,0,1x1)'    # Document with no children yet
    assert observe.browser_without_content(empty_doc)
    full = chrome_ui + nl + '    Document "Flow" @(0,0,1x1)' + "".join(nl + '        Text "t%d" @(0,0,1x1)' % i for i in range(6))
    assert not observe.browser_without_content(full)
    assert not observe.browser_without_content('Window "Notepad" @(0,0,1x1)')


def test_trajectory_log_is_opt_in_and_records_what_clm_saw(monkeypatch, tmp_path):
    import json
    from clm_router import policy

    class Fake:
        def system_one(self, state, questions):
            return {k: {"noul": 0.1} for k in ("risky", "done", "unexpected", "small_failure", "stuck")} | {"last_action_ok": {"noul": 0.9}}

    req = {"mode": "computer_use", "task": "t", "history": ["a"], "observation": {"text": "Window x"}}
    monkeypatch.delenv("CLM_TRAJECTORY_LOG", raising=False)
    router.route(req, Fake())                       # no env var -> nothing written
    log = tmp_path / "traj.jsonl"
    monkeypatch.setenv("CLM_TRAJECTORY_LOG", str(log))
    router.route(req, Fake())
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert rec["state"] == policy.computer_use_state(req) and rec["label"] is None and rec["decision"]["action"] == "continue"
