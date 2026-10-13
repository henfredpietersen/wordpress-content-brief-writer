"""The LangGraph workflow.

    START -> research --(tool calls, under step limit)--> tools -> research
    research --(done, or step limit hit)--> write -> check -> END

research: the model decides which tool to call next (or stops).
tools:    runs the requested tools against WordPress and returns results to the model.
write:    streams the brief, given only the posts that were actually read.
check:    lists any URL in the brief that was not read (should be empty).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .llm import LLM
from .tools import TOOLS, execute_tool
from .wp_client import WordPressSource

RESEARCH_SYSTEM = """You research an existing WordPress site before a new article is written.
Goal: find what the site already publishes on the topic, so the new article links to it,
reuses its facts and avoids repeating it.
Use wp_search_posts with short keyword queries, then wp_get_post to read the most relevant
results in full. Read between 2 and 4 posts. When you have enough, reply with one short
sentence and no tool call."""

WRITE_SYSTEM = """You write content briefs for a writer at a web agency.
Rules:
- Use only the facts in <sources>. If the sources do not cover something, say it is a gap.
- Cite only URLs listed in <sources>. Never invent or guess a URL.
- Plain English, short lines, markdown headings."""

WRITE_TEMPLATE = """Topic: {topic}
Site: {site}

<sources>{sources}</sources>

Write the brief with these sections:
## Working title
## Angle (one sentence on what the new article adds)
## Outline (H2s with one line each)
## Existing posts to link (title and URL, only from sources)
## Facts already on the site (each with its source URL)
## Gaps the new article should fill"""

# Only characters that are valid unescaped in a URL. A looser "anything but whitespace"
# pattern swallowed a model's full-width citation bracket (】) into the URL and flagged a
# page that had been read. Brackets, parentheses and quotes are left out on purpose: they
# wrap URLs in markdown and citations far more often than they appear inside them.
_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#@!$&*+,;=%]+")


class BriefState(TypedDict, total=False):
    topic: str
    site: str
    messages: list[dict]
    fetched: dict[str, dict]
    steps: int
    stopped_reason: str
    brief: str
    uncited_urls: list[str]


def _norm(url: str) -> str:
    return url.rstrip(".,;:").rstrip("/")


def find_uncited_urls(brief: str, fetched: dict[str, dict]) -> list[str]:
    """URLs in the brief that the agent never read. An empty list means the brief is grounded."""
    allowed = {_norm(u) for u in fetched}
    seen: list[str] = []
    for url in _URL_RE.findall(brief):
        if _norm(url) not in allowed and _norm(url) not in seen:
            seen.append(_norm(url))
    return seen


def build_graph(
    llm: LLM,
    wp: WordPressSource,
    max_steps: int = 6,
    on_token: Callable[[str], None] | None = None,
):
    """Compile the graph. max_steps caps research turns so a confused model cannot loop forever."""
    emit = on_token or (lambda _t: None)

    def research(state: BriefState) -> BriefState:
        turn = llm.research_turn(RESEARCH_SYSTEM, state["messages"], TOOLS)
        return {
            "messages": state["messages"] + [{"role": "assistant", "content": turn.content}],
            "steps": state.get("steps", 0) + 1,
        }

    def pending_calls(state: BriefState) -> list[dict]:
        last = state["messages"][-1]
        if last["role"] != "assistant":
            return []
        return [b for b in last["content"] if b.get("type") == "tool_use"]

    def route(state: BriefState) -> str:
        if not pending_calls(state):
            return "write"
        if state["steps"] >= max_steps:
            return "write"
        return "tools"

    def tools(state: BriefState) -> BriefState:
        fetched = dict(state.get("fetched", {}))
        results = [
            {
                "type": "tool_result",
                "tool_use_id": call["id"],
                "content": execute_tool(call["name"], call["input"], wp, fetched),
            }
            for call in pending_calls(state)
        ]
        return {
            "messages": state["messages"] + [{"role": "user", "content": results}],
            "fetched": fetched,
        }

    def write(state: BriefState) -> BriefState:
        fetched = state.get("fetched", {})
        stopped = "step_limit" if pending_calls(state) else "model_finished"
        sources = [
            {"title": p["title"], "url": url, "content": p.get("content", "")}
            for url, p in fetched.items()
        ]
        prompt = WRITE_TEMPLATE.format(
            topic=state["topic"], site=state["site"], sources=json.dumps(sources, indent=1)
        )
        brief = llm.stream_text(WRITE_SYSTEM, prompt, emit)
        return {"brief": brief, "stopped_reason": stopped}

    def check(state: BriefState) -> BriefState:
        return {"uncited_urls": find_uncited_urls(state["brief"], state.get("fetched", {}))}

    g = StateGraph(BriefState)
    g.add_node("research", research)
    g.add_node("tools", tools)
    g.add_node("write", write)
    g.add_node("check", check)
    g.add_edge(START, "research")
    g.add_conditional_edges("research", route, {"tools": "tools", "write": "write"})
    g.add_edge("tools", "research")
    g.add_edge("write", "check")
    g.add_edge("check", END)
    return g.compile()


def run(
    topic: str,
    site: str,
    llm: LLM,
    wp: WordPressSource,
    max_steps: int = 6,
    on_token: Callable[[str], None] | None = None,
) -> BriefState:
    graph = build_graph(llm, wp, max_steps=max_steps, on_token=on_token)
    first = {"role": "user", "content": f"Topic: {topic}\nSite: {site}"}
    # recursion_limit counts graph steps; research+tools is 2 per turn, plus write and check.
    return graph.invoke(
        {"topic": topic, "site": site, "messages": [first], "fetched": {}, "steps": 0},
        config={"recursion_limit": 2 * max_steps + 5},
    )
