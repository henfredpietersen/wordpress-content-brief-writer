"""Read-only access to a WordPress site.

Two implementations share one interface:
- WPClient talks to a live site through the public REST API (/wp-json/wp/v2/posts).
- FixtureWPClient reads a saved JSON file, so tests and the offline eval need no network.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Protocol

import httpx

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z0-9]+")

# Longest page text handed to the model, so one huge page cannot flood the context.
MAX_CONTENT_CHARS = 4000


def html_to_text(raw: str) -> str:
    """Strip tags and decode entities (WordPress titles often contain &#8217; and similar)."""
    text = _TAG_RE.sub(" ", raw or "")
    text = html.unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def _summary(post: dict) -> dict:
    return {
        "id": post["id"],
        "title": html_to_text(post["title"]["rendered"]),
        "url": post["link"],
        "excerpt": html_to_text(post.get("excerpt", {}).get("rendered", "")),
    }


def _full(post: dict) -> dict:
    out = _summary(post)
    out["content"] = html_to_text(post.get("content", {}).get("rendered", ""))[:MAX_CONTENT_CHARS]
    return out


class WordPressSource(Protocol):
    def search_posts(self, query: str, limit: int = 5) -> list[dict]: ...

    def get_post(self, post_id: int) -> dict | None: ...


class WPClient:
    """Live WordPress site. Only reads public posts; never writes."""

    def __init__(self, site_url: str, timeout: float = 15.0, client: httpx.Client | None = None):
        self.base = site_url.rstrip("/") + "/wp-json/wp/v2"
        self._http = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def search_posts(self, query: str, limit: int = 5) -> list[dict]:
        resp = self._http.get(
            f"{self.base}/posts",
            params={
                "search": query,
                "per_page": max(1, min(limit, 10)),
                "_fields": "id,title,link,excerpt",
            },
        )
        resp.raise_for_status()
        return [_summary(p) for p in resp.json()]

    def get_post(self, post_id: int) -> dict | None:
        resp = self._http.get(
            f"{self.base}/posts/{int(post_id)}",
            params={"_fields": "id,title,link,excerpt,content"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _full(resp.json())


class FixtureWPClient:
    """Offline stand-in for a WordPress site.

    Search is simplified: posts are ranked by how many query words appear in the
    title, excerpt and content (title matches count double). Real WordPress search
    differs, so offline results only test the plumbing, not search quality.
    """

    def __init__(self, path: str | Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.site = data["site"]
        self._posts = {p["id"]: p for p in data["posts"]}

    def search_posts(self, query: str, limit: int = 5) -> list[dict]:
        terms = set(_WORD_RE.findall(query.lower())) - _STOPWORDS
        scored = []
        for post in self._posts.values():
            title = set(_WORD_RE.findall(html_to_text(post["title"]["rendered"]).lower()))
            body = set(
                _WORD_RE.findall(
                    (
                        html_to_text(post["excerpt"]["rendered"])
                        + " "
                        + html_to_text(post["content"]["rendered"])
                    ).lower()
                )
            )
            score = 2 * len(terms & title) + len(terms & body)
            if score:
                scored.append((score, post["id"]))
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [_summary(self._posts[pid]) for _, pid in scored[:limit]]

    def get_post(self, post_id: int) -> dict | None:
        post = self._posts.get(int(post_id))
        return _full(post) if post else None


_STOPWORDS = {
    "a", "an", "and", "the", "to", "of", "for", "in", "on", "how", "what", "is", "are",
    "with", "your", "you", "do", "i", "my", "about", "guide", "write", "brief", "post",
}
