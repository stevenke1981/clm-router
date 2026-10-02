import pytest

pytest.importorskip("mcp")
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402
from clm_router import mcp_server as s  # noqa: E402


class Fake:
    """CLM that answers a fixed set of yes/no probabilities for every question."""
    def __init__(self, **noul):
        self.noul, self.calls = noul, []

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        base = dict(risky=0.05, done=0.05, unexpected=0.05, small_failure=0.05, stuck=0.05, last_action_ok=0.9, meets=0.9, global_fault=0.05)
        base.update(self.noul)
        return {k: {"noul": base.get(k, 0.05)} for k in questions}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(s, "_clm", None)
    yield


def use(monkeypatch, fake):
    monkeypatch.setattr(s, "_clm", fake)
    return fake


def test_gate_stops_on_a_risky_screen(monkeypatch):
    use(monkeypatch, Fake(risky=0.9))
    r = s.clm_gate("Install 7-Zip", 'Window "User Account Control"' + chr(10) + 'Button "Yes"', ["run installer"], "run installer")
    assert r["action"] == "ask_user" and r["scores"]["risky"] == 0.9


def test_gate_continue_and_returns_scores(monkeypatch):
    use(monkeypatch, Fake())
    r = s.clm_gate("t", "Notepad editing")
    assert r["action"] == "continue" and set(r["scores"]) >= {"risky", "stuck", "done", "last_action_ok"}


def test_gate_never_observes_the_screen_itself(monkeypatch):
    fake = use(monkeypatch, Fake())
    monkeypatch.setattr("clm_router.observe.observe", lambda *a, **k: pytest.fail("the MCP tool must not capture the screen"))
    for bad in ("", "   "):
        with pytest.raises(ToolError):
            s.clm_gate("t", bad)
    assert fake.calls == []


def test_gate_loop_signal_uses_prev_screen(monkeypatch):
    use(monkeypatch, Fake())
    r = s.clm_gate("t", "same", ["click Install", "click Install", "click Install"], "click Install", prev_screen_text="same")
    assert r["action"] == "replan"


def test_review_image(monkeypatch):
    use(monkeypatch, Fake(meets=0.2, **{"region:headline": 0.8}))
    r = s.clm_review_image("poster", ["text reads OPEN"], "headline reads OPEN DAILY 8-S", [{"id": "headline", "description": "8-S"}, {"id": "cup", "description": "cup"}])
    assert r["action"] == "local_edit" and r["targets"] == ["headline"]
    with pytest.raises(ToolError):
        s.clm_review_image("poster", [], " ")


def test_unreachable_clm_gives_an_actionable_error(monkeypatch):
    import urllib.error

    class Down:
        def system_one(self, *a, **k):
            raise urllib.error.URLError("refused")

    use(monkeypatch, Down())
    with pytest.raises(ToolError, match="not reachable"):
        s.clm_gate("t", "x")


def test_both_tools_are_registered_read_only():
    import asyncio
    tools = asyncio.run(s.mcp.list_tools())
    names = {t.name: t for t in tools}
    assert set(names) == {"clm_gate", "clm_review_image"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_http_error_is_not_reported_as_connection_failure(monkeypatch):
    import urllib.error
    class Bad:
        def system_one(self, *a, **kw):
            raise urllib.error.HTTPError("http://localhost", 503, "Unavailable", {}, None)
    use(monkeypatch, Bad())
    with pytest.raises(ToolError, match="HTTP 503"):
        s.clm_gate("t", "screen")


def test_image_region_zero_is_scored(monkeypatch):
    use(monkeypatch, Fake(meets=0.2, **{"region:0": 0.9}))
    result = s.clm_review_image("poster", [], "bad headline", [{"id": 0, "description": "typo"}])
    assert result["targets"] == ["0"]
