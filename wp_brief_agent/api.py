"""Web API for wp-brief-agent.

    GET  /health        liveness check
    GET  /demo          public, free: scripted stand-in model on the fictional fixture site
    POST /brief         live model, returns the brief as JSON          (needs API token)
    POST /brief/stream  live model, streams the brief as server-sent events (needs API token)

Live endpoints spend the owner's model quota, so they are closed unless API_TOKEN is set,
and every request must send `Authorization: Bearer <API_TOKEN>`. A small hourly cap limits
the damage if the token leaks.

Run locally:  uvicorn wp_brief_agent.api:app --reload
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import queue
import threading
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .graph import run
from .llm import PROVIDERS, ScriptedLLM, make_llm, required_key
from .wp_client import FixtureWPClient, WPClient

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "demo_site.json"
LIVE_REQUESTS_PER_HOUR = int(os.getenv("LIVE_REQUESTS_PER_HOUR", "30"))
MAX_STEPS = 6

app = FastAPI(
    title="wp-brief-agent",
    description=(
        "Researches a WordPress site and writes a content brief that cites only pages it read. "
        "`/demo` is public and free. `/brief` and `/brief/stream` use a live model and need a "
        "bearer token. Built AI-assisted under the direction of Henfred Pietersen."
    ),
    version="1.0.0",
)

_live_calls: deque[float] = deque()
_live_lock = threading.Lock()


class BriefRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=200, examples=["cold brew"])
    site_url: str | None = Field(
        default=None,
        description="Public WordPress site (https). Leave empty to use the fictional demo site.",
        examples=[None],
    )
    provider: str | None = Field(
        default=None, description="anthropic or groq. Defaults to LLM_PROVIDER on the server."
    )


def _summary(state: dict) -> dict:
    return {
        "brief": state["brief"],
        "posts_read": [{"title": p["title"], "url": u} for u, p in state["fetched"].items()],
        "grounded": state["uncited_urls"] == [],
        "uncited_urls": state["uncited_urls"],
        "research_turns": state["steps"],
        "stopped_reason": state["stopped_reason"],
    }


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("API_TOKEN")
    if not expected:
        raise HTTPException(503, "Live endpoints are disabled: API_TOKEN is not configured.")
    sent = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(sent.encode(), expected.encode()):
        raise HTTPException(401, "Missing or wrong bearer token.")


def _check_rate() -> None:
    now = time.time()
    with _live_lock:
        while _live_calls and now - _live_calls[0] > 3600:
            _live_calls.popleft()
        if len(_live_calls) >= LIVE_REQUESTS_PER_HOUR:
            raise HTTPException(
                429, f"Live limit of {LIVE_REQUESTS_PER_HOUR} requests per hour reached."
            )
        _live_calls.append(now)


def validate_site_url(url: str) -> str:
    """Only public https sites. Stops the server being pointed at itself or a private network."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise HTTPException(422, "site_url must be a full https:// URL.")
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        raise HTTPException(422, "site_url must be a public site.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        # keep the path: some WordPress sites live in a subfolder
        return f"https://{parsed.netloc}{parsed.path.rstrip('/')}"
    raise HTTPException(422, "site_url must use a domain name, not an IP address.")


def _setup(req: BriefRequest):
    provider = (req.provider or os.getenv("LLM_PROVIDER") or "anthropic").lower()
    if provider not in PROVIDERS:
        raise HTTPException(422, f"provider must be one of: {', '.join(PROVIDERS)}.")
    if not os.getenv(required_key(provider)):
        raise HTTPException(503, f"{required_key(provider)} is not configured on the server.")
    if req.site_url:
        site = validate_site_url(req.site_url)
        wp = WPClient(site)
    else:
        wp = FixtureWPClient(FIXTURE)
        site = wp.site
    return make_llm(provider), wp, site


@app.get("/")
def root() -> dict:
    return {
        "name": "wp-brief-agent",
        "docs": "/docs",
        "demo": "/demo?topic=cold%20brew",
        "source": "https://github.com/henfredpietersen/wp-brief-agent",
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "live_enabled": bool(os.getenv("API_TOKEN"))}


@app.get("/demo")
def demo(topic: str = Query("cold brew", min_length=2, max_length=200)) -> dict:
    """Free and public: scripted stand-in on the fictional site. Shows the flow, not quality."""
    wp = FixtureWPClient(FIXTURE)
    state = run(topic, wp.site, ScriptedLLM(), wp, max_steps=MAX_STEPS)
    return {"mode": "demo (scripted stand-in, fictional site)", **_summary(state)}


@app.post("/brief", dependencies=[Depends(require_token)])
def brief(req: BriefRequest) -> dict:
    llm, wp, site = _setup(req)
    _check_rate()
    try:
        state = run(req.topic, site, llm, wp, max_steps=MAX_STEPS)
    except Exception as exc:  # noqa: BLE001 - model or site errors become a clean 502
        raise HTTPException(502, f"{type(exc).__name__}: {exc}") from exc
    return {"model": f"{llm.provider}: {llm.model}", "site": site, **_summary(state)}


@app.post("/brief/stream", dependencies=[Depends(require_token)])
def brief_stream(req: BriefRequest) -> StreamingResponse:
    """Server-sent events: `token` events while the brief is written, then one `done` event."""
    llm, wp, site = _setup(req)
    _check_rate()
    q: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            state = run(req.topic, site, llm, wp, max_steps=MAX_STEPS, on_token=q.put)
            q.put(("done", {"model": f"{llm.provider}: {llm.model}", **_summary(state)}))
        except Exception as exc:  # noqa: BLE001
            q.put(("error", {"error": f"{type(exc).__name__}: {exc}"}))

    threading.Thread(target=work, daemon=True).start()

    def events() -> Iterator[str]:
        while True:
            item = q.get()
            if isinstance(item, tuple):
                kind, payload = item
                yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
                return
            yield f"event: token\ndata: {json.dumps(item)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
