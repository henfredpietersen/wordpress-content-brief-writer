"""Model access.

Every provider implements the same two methods, so the graph does not know which one it uses:
- research_turn() sends the tool definitions and returns any tool calls.
- stream_text() streams the final brief token by token.

The graph keeps its message history in Anthropic's format (content blocks with tool_use and
tool_result). AnthropicLLM sends that as-is. OpenAICompatibleLLM translates it to and from
the OpenAI chat format, which Groq (and OpenAI itself) accept.

AnthropicLLM calls the Anthropic Messages API directly (no LangChain wrapper).

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
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
PROVIDERS = ("anthropic", "groq")


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
    def __init__(self, model: str | None = None, max_tokens: int = 4000, client=None):
        import anthropic  # imported here so offline runs do not need a key

        # `or` (not a getenv default) so an empty ANTHROPIC_MODEL still falls back.
        self.model = model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.provider = "anthropic"
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
            final = stream.get_final_message()
            # "max_tokens" means the brief was cut off; the graph reports it instead of hiding it.
            self.last_stop_reason = final.stop_reason or ""
            return stream.get_final_text()


class OpenAICompatibleLLM:
    """Any OpenAI-compatible chat API. Used here for Groq (free plan available)."""

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 4000,
        client=None,
        provider: str = "openai",
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.provider = provider
        if client is None:
            import openai  # imported here so offline runs do not need it configured

            # Extra retries: free plans rate-limit (HTTP 429) and the SDK backs off on each.
            client = openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=5)
        self.client = client

    @staticmethod
    def to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
        """Translate the graph's Anthropic-format history into OpenAI chat messages."""
        out: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                out.append({"role": msg["role"], "content": content})
                continue
            if msg["role"] == "assistant":
                text = "".join(b["text"] for b in content if b.get("type") == "text")
                calls = [
                    {
                        "id": b["id"],
                        "type": "function",
                        "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
                    }
                    for b in content
                    if b.get("type") == "tool_use"
                ]
                item: dict = {"role": "assistant", "content": text or None}
                if calls:
                    item["tool_calls"] = calls
                out.append(item)
            else:  # user turn carrying tool results
                for b in content:
                    if b.get("type") == "tool_result":
                        out.append(
                            {
                                "role": "tool",
                                "tool_call_id": b["tool_use_id"],
                                "content": b["content"],
                            }
                        )
                    elif b.get("type") == "text":
                        out.append({"role": "user", "content": b["text"]})
        return out

    @staticmethod
    def to_openai_tools(tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    def research_turn(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=self.to_openai_messages(system, messages),
            tools=self.to_openai_tools(tools),
        )
        choice = resp.choices[0]
        message = choice.message
        content: list[dict] = []
        calls: list[ToolCall] = []
        if message.content:
            content.append({"type": "text", "text": message.content})
        for tc in message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                # Malformed arguments go to the tool as-is; execute_tool returns the error
                # to the model instead of crashing the run.
                args = {"_raw": tc.function.arguments}
            content.append(
                {"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args}
            )
            calls.append(ToolCall(tc.id, tc.function.name, args))
        return Turn(content=content, tool_calls=calls, stop_reason=choice.finish_reason or "")

    def stream_text(self, system: str, prompt: str, on_token: Callable[[str], None]) -> str:
        stream = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            stream=True,
        )
        parts: list[str] = []
        self.last_stop_reason = ""
        for chunk in stream:
            if not chunk.choices:
                continue
            finish = getattr(chunk.choices[0], "finish_reason", None)
            if finish:
                self.last_stop_reason = finish  # "length" means the brief was cut off
            delta = chunk.choices[0].delta.content
            if delta:
                parts.append(delta)
                on_token(delta)
        return "".join(parts)


def make_llm(provider: str | None = None) -> AnthropicLLM | OpenAICompatibleLLM:
    """Build the live model for a provider. Reads keys and model overrides from the environment."""
    provider = (provider or os.getenv("LLM_PROVIDER") or "anthropic").lower()
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "groq":
        return OpenAICompatibleLLM(
            model=os.getenv("GROQ_MODEL") or GROQ_DEFAULT_MODEL,
            base_url=GROQ_BASE_URL,
            api_key=os.getenv("GROQ_API_KEY"),
            provider="groq",
        )
    raise ValueError(f"Unknown provider {provider!r}. Choose one of: {', '.join(PROVIDERS)}.")


def required_key(provider: str) -> str:
    return {"anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY"}[provider]


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
