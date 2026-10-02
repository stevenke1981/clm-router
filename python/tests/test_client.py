import math

import pytest

from clm_router import client


@pytest.mark.parametrize("answers", [None, [], {}, {"risky": {}}, {"risky": {"noul": None}},
    *({"risky": {"noul": v}} for v in [True, "0.5", -0.1, 1.1, math.nan, math.inf])])
def test_rejects_incomplete_or_invalid_backend_answers(monkeypatch, answers):
    monkeypatch.setattr(client, "post_json", lambda *a, **kw: {"answers": answers})
    with pytest.raises(client.CLMResponseError):
        client.CLM().system_one("screen", {"risky": {"type": "noul"}})


def test_forwards_timeout_and_accepts_probability_boundaries(monkeypatch):
    seen = {}
    def post(url, body, **kwargs):
        seen.update(url=url, body=body, **kwargs)
        return {"answers": {"risky": {"noul": 0}, "done": {"noul": 1}}}
    monkeypatch.setattr(client, "post_json", post)
    monkeypatch.setenv("CLM_TIMEOUT", "12.5")
    answers = client.CLM("http://localhost:1234/").system_one("screen", {k: {"type": "noul"} for k in ("risky", "done")})
    assert answers["done"]["noul"] == 1
    assert seen["timeout"] == 12.5 and seen["url"] == "http://localhost:1234/v1/systemone"


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-2", "invalid"])
def test_timeout_must_be_positive_and_finite(monkeypatch, value):
    monkeypatch.setenv("CLM_TIMEOUT", value)
    with pytest.raises(ValueError):
        client.CLM()
