"""Model access.

AnthropicLLM calls the Anthropic Messages API directly (no LangChain wrapper):
- research_turn() sends the tool definitions and returns any tool_use blocks.
- stream_text() streams the final brief token by token.

ScriptedLLM is a deterministic stand-in with the same interface. It lets the tests and the
offline eval run with no API key. It does not reason; it follows a fixed script
(search with the topic, read the top results, write a templated brief). Results from it
test the graph, tools and checks, not model quality.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

DEFAULT_MODEL = "claude-sonnet-5-5"


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Turn:
    """One assistant turn, normalised. `content` is ready to append to the message list."""

    content: list[dict]
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"


class LLM(Protocol):
    def research_turn(self, system: str, messages: list[dict], tools: list[dict]) -> Turn: ...

    def stream_text(self, system: str, prompt: str, on_token: Callable[[str], None]) -> str: ...


class AnthropicLLM:
    def __init__(self, model: str | None = None, max_tokens: int = 2000, client=None):
        import anthropic  # imported here so offline runs do not need a key

        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        # The SDK reads ANTHROPIC_API_KEY and retries transient errors (2 retries by default).
        self.client = client or anthropic.Anthropic()

    def research_turn(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
        content: list[dict] = []
        calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
                calls.append(ToolCall(block.id, block.name, dict(block.input)))
        return Turn(content=content, tool_calls=calls, stop_reason=resp.stop_reason or "")

    def stream_text(self, system: str, prompt: str, on_token: Callable[[str], None]) -> str:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                on_token(text)
            return stream.get_final_text()


# --------------------------------------------------------------------------------------
# Offline stand-in
# --------------------------------------------------------------------------------------

_TOPIC_RE = re.compile(r"^Topic:\s*(.+)$", re.MULTILINE)
_SOURCES_RE = re.compile(r"<sources>(.*?)</sources>", re.DOTALL)


class ScriptedLLM:
    """Deterministic stand-in. See module docstring for what it does and does not test.

    reads: how many posts to read in full before stopping.
    invent_url: if True, the brief cites a URL the agent never read (used to prove the
                grounding check catches it).
    """

    def __init__(self, reads: int = 2, invent_url: bool = False):
        self.reads = reads
        self.invent_url = invent_url
        self._n = 0

    def _id(self) -> str:
        self._n += 1
        return f"toolu_scripted_{self._n}"

    def research_turn(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        topic = _TOPIC_RE.search(messages[0]["content"]).group(1).strip()
        searched = False
        candidates: list[int] = []
        read: set[int] = set()
        for msg in messages:
            if msg["role"] == "assistant":
                for block in msg["content"]:
                    if block.get("type") == "tool_use":
                        if block["name"] == "wp_search_posts":
                            searched = True
                        elif block["name"] == "wp_get_post":
                            read.add(int(block["input"]["post_id"]))
            elif msg["role"] == "user" and isinstance(msg["content"], list):
                for block in msg["content"]:
                    if block.get("type") == "tool_result":
                        data = json.loads(block["content"])
                        candidates += [r["id"] for r in data.get("results", [])]

        if not searched:
            call = ToolCall(self._id(), "wp_search_posts", {"query": topic, "limit": 5})
        else:
            todo = [c for c in candidates if c not in read]
            if len(read) >= self.reads or not todo:
                return Turn(content=[{"type": "text", "text": "Research done."}])
            call = ToolCall(self._id(), "wp_get_post", {"post_id": todo[0]})
        block = {"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}
        return Turn(content=[block], tool_calls=[call], stop_reason="tool_use")

    def stream_text(self, system: str, prompt: str, on_token: Callable[[str], None]) -> str:
        topic = _TOPIC_RE.search(prompt).group(1).strip()
        sources = json.loads(_SOURCES_RE.search(prompt).group(1))
        lines = [f"## Working title\n{topic.capitalize()}", "## Existing posts to link"]
        lines += [f"- {s['title']}: {s['url']}" for s in sources] or ["- None found."]
        if self.invent_url:
            lines.append("- Extra reading: https://demo-roastery.test/this-page-was-never-read/")
        lines.append("## Outline\n- Introduction\n- Main points\n- Next steps")
        text = "\n".join(lines) + "\n"
        for word in re.split(r"(\s+)", text):
            if word:
                on_token(word)
        return text
