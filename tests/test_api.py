import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from wp_brief_agent import api
from wp_brief_agent.llm import ScriptedLLM

client = TestClient(api.app)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    api._live_calls.clear()
    for var in ("API_TOKEN", "LLM_PROVIDER", "GROQ_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def live(monkeypatch):
    """Live endpoints enabled, with the model swapped for the scripted stand-in (no network)."""
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("LLM_PROVIDER", "groq")

    def fake_make_llm(provider):
        llm = ScriptedLLM()
        llm.provider, llm.model = provider, "scripted"
        return llm

    monkeypatch.setattr(api, "make_llm", fake_make_llm)
    return {"Authorization": "Bearer test-token"}


def test_health_and_root():
    assert client.get("/health").json() == {"status": "ok", "live_enabled": False}
    assert client.get("/").json()["docs"] == "/docs"


def test_demo_is_public_and_grounded():
    body = client.get("/demo", params={"topic": "storing coffee beans"}).json()
    assert body["grounded"] is True
    assert any("storing-coffee-beans" in p["url"] for p in body["posts_read"])


def test_demo_rejects_oversized_topic():
    assert client.get("/demo", params={"topic": "x" * 201}).status_code == 422


def test_live_closed_when_no_token_configured():
    assert client.post("/brief", json={"topic": "cold brew"}).status_code == 503


def test_live_rejects_wrong_or_missing_token(live):
    assert client.post("/brief", json={"topic": "cold brew"}).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.post("/brief", json={"topic": "cold brew"}, headers=bad).status_code == 401


def test_live_brief_with_token(live):
    r = client.post("/brief", json={"topic": "cold brew"}, headers=live)
    assert r.status_code == 200
    assert r.json()["grounded"] is True and r.json()["model"] == "groq: scripted"


def test_stream_sends_tokens_then_done(live):
    with client.stream("POST", "/brief/stream", json={"topic": "cold brew"}, headers=live) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    events = [blk for blk in text.strip().split("\n\n")]
    assert events[0].startswith("event: token")
    assert events[-1].startswith("event: done")
    done = json.loads(events[-1].split("data: ", 1)[1])
    assert done["grounded"] is True
    streamed = "".join(json.loads(e.split("data: ", 1)[1]) for e in events[:-1])
    assert streamed == done["brief"]


def test_hourly_cap(live, monkeypatch):
    monkeypatch.setattr(api, "LIVE_REQUESTS_PER_HOUR", 2)
    codes = [
        client.post("/brief", json={"topic": "cold brew"}, headers=live).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


def test_missing_provider_key_is_reported(live, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    r = client.post("/brief", json={"topic": "cold brew"}, headers=live)
    assert r.status_code == 503 and "GROQ_API_KEY" in r.json()["detail"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",  # not https
        "https://localhost",
        "https://127.0.0.1",
        "https://10.0.0.5",
        "https://[::1]",
        "https://printer.local",
        "notaurl",
    ],
)
def test_site_url_must_be_public_https(url):
    with pytest.raises(HTTPException):
        api.validate_site_url(url)


def test_site_url_keeps_subfolder():
    assert api.validate_site_url("https://example.com/blog/") == "https://example.com/blog"
