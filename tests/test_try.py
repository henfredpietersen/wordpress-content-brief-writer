"""The public /try route: off by default, Outview origins only, per-visitor and daily caps."""

import json

import pytest
from fastapi.testclient import TestClient

from wp_brief_agent import api
from wp_brief_agent.llm import ScriptedLLM
from wp_brief_agent.wp_client import FixtureWPClient

client = TestClient(api.app)
ORIGIN = {"Origin": "https://outview.co.za"}
BODY = {"topic": "cold brew", "site_url": "https://example.com"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    api._public_calls.clear()
    for var in ("PUBLIC_RUNS_PER_DAY", "PUBLIC_PER_IP_PER_HOUR", "PUBLIC_PROVIDER", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def public(monkeypatch):
    """Public route switched on, model and site swapped for offline stand-ins."""
    monkeypatch.setenv("PUBLIC_RUNS_PER_DAY", "50")
    monkeypatch.setenv("GROQ_API_KEY", "x")

    def fake_make_llm(provider):
        llm = ScriptedLLM()
        llm.provider, llm.model = provider, "scripted"
        return llm

    monkeypatch.setattr(api, "make_llm", fake_make_llm)
    monkeypatch.setattr(api, "WPClient", lambda site: FixtureWPClient(api.FIXTURE))


def _events(r) -> list[tuple[str, object]]:
    out = []
    for block in "".join(r.iter_text()).strip().split("\n\n"):
        kind = block.split("\n", 1)[0].removeprefix("event: ")
        out.append((kind, json.loads(block.split("data: ", 1)[1])))
    return out


def test_off_by_default():
    assert client.get("/try/status").json()["enabled"] is False
    assert client.post("/try/stream", json=BODY, headers=ORIGIN).status_code == 503


def test_status_counts_down(public):
    assert client.get("/try/status").json()["runs_left_today"] == 50
    with client.stream("POST", "/try/stream", json=BODY, headers=ORIGIN) as r:
        _events(r)
    assert client.get("/try/status").json()["runs_left_today"] == 49


def test_rejects_other_origins(public):
    assert client.post("/try/stream", json=BODY).status_code == 403
    evil = {"Origin": "https://evil.example"}
    assert client.post("/try/stream", json=BODY, headers=evil).status_code == 403


def test_rejects_private_sites(public):
    for url in ("http://example.com", "https://localhost", "https://10.0.0.1"):
        bad = {**BODY, "site_url": url}
        assert client.post("/try/stream", json=bad, headers=ORIGIN).status_code == 422


def test_stream_shows_research_then_brief(public):
    with client.stream("POST", "/try/stream", json=BODY, headers=ORIGIN) as r:
        assert r.status_code == 200
        events = _events(r)
    kinds = [k for k, _ in events]
    assert kinds[0] == "search" and "read" in kinds and "token" in kinds
    assert kinds[-1] == "done"
    done = events[-1][1]
    assert done["grounded"] is True and done["model"] == "groq: scripted"
    assert "".join(d for k, d in events if k == "token") == done["brief"]


def test_per_visitor_limit(public, monkeypatch):
    monkeypatch.setenv("PUBLIC_PER_IP_PER_HOUR", "2")
    a = {**ORIGIN, "X-Forwarded-For": "1.1.1.1, 10.0.0.1"}
    for _ in range(2):
        with client.stream("POST", "/try/stream", json=BODY, headers=a) as r:
            _events(r)
    assert client.post("/try/stream", json=BODY, headers=a).status_code == 429
    b = {**ORIGIN, "X-Forwarded-For": "2.2.2.2"}
    with client.stream("POST", "/try/stream", json=BODY, headers=b) as r:
        assert r.status_code == 200
        _events(r)


def test_daily_cap(public, monkeypatch):
    monkeypatch.setenv("PUBLIC_RUNS_PER_DAY", "1")
    with client.stream("POST", "/try/stream", json=BODY, headers=ORIGIN) as r:
        _events(r)
    other = {**ORIGIN, "X-Forwarded-For": "3.3.3.3"}
    assert client.post("/try/stream", json=BODY, headers=other).status_code == 429


def test_public_runs_do_not_use_the_token_budget(public):
    api._live_calls.clear()
    with client.stream("POST", "/try/stream", json=BODY, headers=ORIGIN) as r:
        _events(r)
    assert len(api._live_calls) == 0


def test_cors_preflight_allows_outview_only():
    ok = client.options(
        "/try/stream",
        headers={**ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "https://outview.co.za"
    bad = client.options(
        "/try/stream",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_site_errors_are_explained():
    class Resp:
        status_code = 403

    class Err(Exception):
        response = Resp()

    assert "firewall" in api._site_error(Err())
    assert "reach" in api._site_error(ValueError())
