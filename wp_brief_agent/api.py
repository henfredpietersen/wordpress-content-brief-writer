"""Web API for wp-brief-agent.

    GET  /health        liveness check
    GET  /demo          public, free: scripted stand-in model on the fictional fixture site
    POST /brief         live model, returns the brief as JSON          (needs API token)
    POST /brief/stream  live model, streams the brief as server-sent events (needs API token)
    GET  /try/status    public: is the visitor "try it" route on, and how many runs are left today
    POST /try/stream    public, for the case-study page: a live run on any public WordPress site

Live endpoints spend the owner's model quota, so they are closed unless API_TOKEN is set,
and every request must send `Authorization: Bearer <API_TOKEN>`. A small hourly cap limits
the damage if the token leaks.

The public /try route has no token (a page can't keep one secret), so it is boxed in instead:
off unless PUBLIC_RUNS_PER_DAY is set, one fixed provider (PUBLIC_PROVIDER, default groq),
browser origins limited to PUBLIC_ORIGINS, a per-visitor hourly limit and a daily total.
Its budget is separate from the token routes, so visitors can't use up the owner's quota.

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
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from .graph import run
from .llm import PROVIDERS, ScriptedLLM, make_llm, required_key
from .wp_client import FixtureWPClient, WPClient

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "demo_site.json"
LIVE_REQUESTS_PER_HOUR = int(os.getenv("LIVE_REQUESTS_PER_HOUR", "30"))
MAX_STEPS = 6
DEFAULT_PUBLIC_ORIGINS = "https://outview.co.za,https://www.outview.co.za"


def public_origins() -> list[str]:
    raw = os.getenv("PUBLIC_ORIGINS", DEFAULT_PUBLIC_ORIGINS)
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

app = FastAPI(
    title="wp-brief-agent",
    description=(
        "Researches a WordPress site and writes a content brief that cites only pages it read. "
        "`/demo` is public and free. `/brief` and `/brief/stream` use a live model and need a "
        "bearer token. Built AI-assisted under the direction of Henfred Pietersen."
    ),
    version="1.0.0",
    # Keep the docs page's Authorize login across page reloads; without this, a refresh after
    # authorizing silently sends requests with no token.
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=public_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_live_calls: deque[float] = deque()
_live_lock = threading.Lock()
_public_calls: deque[tuple[float, str]] = deque()  # (time, visitor ip) for /try runs


class BriefRequest(BaseModel):
    # One whole-body example, so the docs page pre-fills a request that actually works.
    model_config = ConfigDict(json_schema_extra={"examples": [{"topic": "cold brew"}]})

    topic: str = Field(min_length=2, max_length=200)
    site_url: str | None = Field(
        default=None,
        description="Public WordPress site (https). Leave out to use the fictional demo site.",
    )
    provider: str | None = Field(
        default=None, description="anthropic or groq. Leave out to use the server default."
    )


def _summary(state: dict) -> dict:
    return {
        "brief": state["brief"],
        "posts_read": [{"title": p["title"], "url": u} for u, p in state["fetched"].items()],
        "grounded": state["uncited_urls"] == [],
        "uncited_urls": state["uncited_urls"],
        "research_turns": state["steps"],
        "stopped_reason": state["stopped_reason"],
        "truncated": bool(state.get("truncated")),
    }


# A declared bearer security scheme, not a plain `Authorization` header parameter: the docs
# page (Swagger UI) silently drops header parameters named Authorization, per the OpenAPI
# spec, but sends credentials entered through its Authorize button.
_bearer = HTTPBearer(auto_error=False, description="The API_TOKEN set on the server.")


def require_token(
    creds: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)] = None,
) -> None:
    # Strip stray spaces or a newline picked up when the value was pasted into the host's settings.
    expected = (os.getenv("API_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(503, "Live endpoints are disabled: API_TOKEN is not configured.")
    if creds is None:
        # Say plainly that nothing arrived; "missing or wrong" hid which problem it was.
        raise HTTPException(
            401,
            "No token was sent. In /docs, click Authorize (padlock, top right), paste the token, "
            "then Authorize and Close. If you reloaded the page, authorize again.",
        )
    sent = creds.credentials.strip()
    # Forgive the common slip of pasting "Bearer <token>" into the docs page's Authorize box,
    # which already adds "Bearer", so the server would otherwise see "Bearer Bearer <token>".
    if sent.lower().startswith("bearer "):
        sent = sent[7:].strip()
    if not hmac.compare_digest(sent.encode(), expected.encode()):
        raise HTTPException(
            401,
            "A token was sent but it is wrong. Copy API_TOKEN again from the server settings and "
            "paste the token only, without the word Bearer.",
        )


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
    # Forgive stray spaces, quotes and capitals in a value typed into the host's settings.
    raw = req.provider or os.getenv("LLM_PROVIDER") or "anthropic"
    provider = raw.strip().strip("\"'").strip().lower()
    if provider not in PROVIDERS:
        where = "the request's provider field" if req.provider else "LLM_PROVIDER on the server"
        # The bad value is not echoed back: it may be a secret pasted into the wrong setting.
        raise HTTPException(
            422, f"provider must be one of: {', '.join(PROVIDERS)}. Check {where}."
        )
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


# --------------------------------------------------------------------------- public /try route
class TryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"topic": "cold brew", "site_url": "https://example.com"}]}
    )

    topic: str = Field(min_length=2, max_length=120)
    site_url: str = Field(
        min_length=10, max_length=300, description="Public WordPress site (https)."
    )


def _public_limits() -> tuple[int, int]:
    return int(os.getenv("PUBLIC_RUNS_PER_DAY", "0")), int(os.getenv("PUBLIC_PER_IP_PER_HOUR", "3"))


def _visitor_ip(request: Request) -> str:
    # Render sits behind a proxy; the first X-Forwarded-For entry is the visitor.
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _public_used(now: float) -> int:
    while _public_calls and now - _public_calls[0][0] > 86400:
        _public_calls.popleft()
    return len(_public_calls)


def _public_provider() -> str:
    provider = os.getenv("PUBLIC_PROVIDER", "groq").strip().strip("\"'").strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(503, "The public demo is misconfigured: check PUBLIC_PROVIDER.")
    if not os.getenv(required_key(provider)):
        raise HTTPException(503, "The public demo is not available right now.")
    return provider


@app.get("/try/status")
def try_status() -> dict:
    per_day, per_ip = _public_limits()
    with _live_lock:
        used = _public_used(time.time())
    return {
        "enabled": per_day > 0,
        "runs_left_today": max(0, per_day - used),
        "runs_per_day": per_day,
        "per_visitor_per_hour": per_ip,
    }


def _check_public(request: Request) -> None:
    per_day, per_ip = _public_limits()
    if per_day <= 0:
        raise HTTPException(503, "The public demo is switched off.")
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin not in public_origins():
        raise HTTPException(403, "This demo only runs from the Outview case-study page.")
    ip, now = _visitor_ip(request), time.time()
    with _live_lock:
        used = _public_used(now)
        if used >= per_day:
            raise HTTPException(429, "Today's public runs are used up. Please try again tomorrow.")
        mine = sum(1 for t, who in _public_calls if who == ip and now - t <= 3600)
        if mine >= per_ip:
            raise HTTPException(
                429, f"You've used your {per_ip} runs for this hour. Please try again later."
            )
        _public_calls.append((now, ip))


class _ProgressWP:
    """Wraps the WordPress client to report each search and read as it happens."""

    def __init__(self, wp, emit):
        self._wp, self._emit = wp, emit

    def search_posts(self, query: str, limit: int = 5) -> list[dict]:
        try:
            results = self._wp.search_posts(query, limit)
        except Exception as exc:
            self._emit(("search", {"query": query, "found": [], "error": _site_error(exc)}))
            raise
        self._emit(("search", {"query": query, "found": [r.get("title") for r in results]}))
        return results

    def get_post(self, post_id: int) -> dict | None:
        try:
            post = self._wp.get_post(post_id)
        except Exception as exc:
            self._emit(("read", {"post_id": post_id, "title": None, "error": _site_error(exc)}))
            raise
        self._emit(("read", {"post_id": post_id, "title": (post or {}).get("title")}))
        return post


def _site_error(exc: Exception) -> str:
    """A short, visitor-friendly reason the site could not be read."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return f"The site refused the request ({status}); a firewall may block bots."
    if status == 404:
        return "No WordPress posts API at that address (404). Is it a WordPress site?"
    if status:
        return f"The site answered with an error ({status})."
    return f"Could not reach the site ({type(exc).__name__})."


@app.post("/try/stream")
def try_stream(req: TryRequest, request: Request) -> StreamingResponse:
    """Public live run for the case-study page: `search` and `read` events while it researches,
    `token` events while it writes, then one `done` (or `error`) event."""
    site = validate_site_url(req.site_url)
    provider = _public_provider()
    _check_public(request)
    llm = make_llm(provider)
    q: queue.Queue = queue.Queue()
    wp = _ProgressWP(WPClient(site), q.put)

    def work() -> None:
        try:
            state = run(req.topic, site, llm, wp, max_steps=MAX_STEPS, on_token=q.put)
            model = f"{llm.provider}: {llm.model}"
            q.put(("done", {"model": model, "site": site, **_summary(state)}))
        except Exception as exc:  # noqa: BLE001 - shown to the visitor as a clean error
            q.put(("error", {"error": f"The run stopped: {type(exc).__name__}."}))

    threading.Thread(target=work, daemon=True).start()

    def events() -> Iterator[str]:
        while True:
            item = q.get()
            if isinstance(item, tuple):
                kind, payload = item
                yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
                if kind in ("done", "error"):
                    return
            else:
                yield f"event: token\ndata: {json.dumps(item)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
