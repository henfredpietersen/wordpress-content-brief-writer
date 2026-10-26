"""Read-only Figma REST client: turns a design file into a content map the brief can follow.

    python -m wp_brief_agent.figma https://www.figma.com/design/<KEY>/<name>   # needs FIGMA_TOKEN

For each top-level frame on each page, it collects the text layers in reading order (top to
bottom, then left to right) and picks the largest-font text as the section heading. The writer
gets this as layout context, so the brief's outline can line up with the design's sections.
Design text is never treated as a source of facts, and Figma URLs are never cited.
"""

from __future__ import annotations

import re

import httpx

API = "https://api.figma.com"
MAX_TEXTS_PER_SECTION = 8
MAX_TEXT_CHARS = 200

_KEY_RE = re.compile(r"figma\.com/(?:design|file|proto|board)/([A-Za-z0-9]+)")


class FigmaError(RuntimeError):
    pass


def parse_file_key(url_or_key: str) -> str:
    """Accept a Figma share URL or a bare file key."""
    value = url_or_key.strip()
    match = _KEY_RE.search(value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9]{10,}", value):
        return value
    raise FigmaError("That doesn't look like a Figma file URL or key.")


class FigmaClient:
    """GET only. Authenticates with a personal access token in the X-Figma-Token header."""

    def __init__(self, token: str, client: httpx.Client | None = None):
        if not token:
            raise FigmaError("FIGMA_TOKEN is not set.")
        self.http = client or httpx.Client(timeout=30)
        self.headers = {"X-Figma-Token": token}

    def get_file(self, key: str) -> dict:
        r = self.http.get(f"{API}/v1/files/{key}", headers=self.headers)
        if r.status_code in (401, 403):
            raise FigmaError("Figma refused the token, or it has no access to this file.")
        if r.status_code == 404:
            raise FigmaError("Figma file not found. Check the URL or key.")
        r.raise_for_status()
        return r.json()


def _texts(node: dict, out: list[dict]) -> None:
    if node.get("visible") is False:
        return
    if node.get("type") == "TEXT" and node.get("characters", "").strip():
        box = node.get("absoluteBoundingBox") or {}
        out.append({
            "text": " ".join(node["characters"].split())[:MAX_TEXT_CHARS],
            "size": (node.get("style") or {}).get("fontSize", 0),
            "y": box.get("y", 0),
            "x": box.get("x", 0),
        })
    for child in node.get("children", []):
        _texts(child, out)


def extract_sections(file_json: dict, max_sections: int = 12) -> list[dict]:
    """One entry per top-level frame with text: page, frame, heading, texts in reading order."""
    sections: list[dict] = []
    for page in file_json.get("document", {}).get("children", []):
        if page.get("type") != "CANVAS":
            continue
        for frame in page.get("children", []):
            if frame.get("type") not in ("FRAME", "SECTION", "COMPONENT"):
                continue
            if frame.get("visible") is False:
                continue
            found: list[dict] = []
            _texts(frame, found)
            if not found:
                continue
            found.sort(key=lambda t: (round(t["y"]), t["x"]))
            heading = max(found, key=lambda t: t["size"])["text"]
            sections.append({
                "page": page.get("name", ""),
                "frame": frame.get("name", ""),
                "heading": heading,
                "texts": [t["text"] for t in found[:MAX_TEXTS_PER_SECTION]],
            })
            if len(sections) >= max_sections:
                return sections
    return sections


def load_design(url_or_key: str, token: str, client: httpx.Client | None = None) -> dict:
    """Fetch a file and return {"name", "key", "sections"}."""
    key = parse_file_key(url_or_key)
    data = FigmaClient(token, client).get_file(key)
    return {"name": data.get("name", ""), "key": key, "sections": extract_sections(data)}
