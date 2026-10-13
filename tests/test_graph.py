from pathlib import Path
from types import SimpleNamespace

from wp_brief_agent.graph import find_uncited_urls, run
from wp_brief_agent.llm import (
    AnthropicLLM,
    OpenAICompatibleLLM,
    ScriptedLLM,
    ToolCall,
    Turn,
    make_llm,
)
from wp_brief_agent.wp_client import FixtureWPClient

WP = FixtureWPClient(Path(__file__).resolve().parent.parent / "fixtures" / "demo_site.json")


def test_offline_run_reads_posts_and_writes_grounded_brief():
    tokens = []
    state = run("storing coffee beans", WP.site, ScriptedLLM(reads=2), WP, on_token=tokens.append)
    assert len(state["fetched"]) == 2
    assert "https://demo-roastery.test/storing-coffee-beans/" in state["fetched"]
    assert state["uncited_urls"] == []
    assert state["stopped_reason"] == "model_finished"
    # streaming: the tokens shown to the user add up to the stored brief
    assert "".join(tokens) == state["brief"]


def test_grounding_check_catches_an_invented_url():
    state = run("cold brew", WP.site, ScriptedLLM(invent_url=True), WP)
    assert state["uncited_urls"] == ["https://demo-roastery.test/this-page-was-never-read"]


def test_find_uncited_urls_handles_brackets_models_wrap_urls_in():
    """Regression: a live Groq run cited a read page as 【https://x.test/a/】 and the
    full-width bracket was treated as part of the URL, giving a false 'uncited' flag."""
    fetched = {"https://x.test/a/": {}}
    for brief in [
        "Source: 【https://x.test/a/】",
        "See [the guide](https://x.test/a/).",
        "<https://x.test/a/>",
        "(https://x.test/a/)",
        "\"https://x.test/a/\"",
    ]:
        assert find_uncited_urls(brief, fetched) == [], brief
    # and a genuinely unread page next to the bracket is still caught
    assert find_uncited_urls("【https://x.test/b/】", fetched) == ["https://x.test/b"]


def test_find_uncited_urls_ignores_trailing_slash_and_punctuation():
    fetched = {"https://x.test/a/": {}}
    assert find_uncited_urls("See https://x.test/a. Also https://x.test/b/", fetched) == [
        "https://x.test/b"
    ]


class LoopingLLM:
    """A model that never stops calling tools."""

    def __init__(self):
        self.calls = 0

    def research_turn(self, system, messages, tools):
        self.calls += 1
        call = ToolCall(f"t{self.calls}", "wp_search_posts", {"query": "coffee"})
        block = {"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}
        return Turn(content=[block], tool_calls=[call], stop_reason="tool_use")

    def stream_text(self, system, prompt, on_token):
        return "No sources."


def test_step_limit_stops_a_runaway_loop():
    llm = LoopingLLM()
    state = run("coffee", WP.site, llm, WP, max_steps=3)
    assert llm.calls == 3
    assert state["stopped_reason"] == "step_limit"


# --- The real Anthropic wrapper, with a fake client (no network) ----------------------


class FakeStream:
    text_stream = iter(["Hello ", "brief"])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_text(self):
        return "Hello brief"


class FakeMessages:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[
                SimpleNamespace(type="text", text="Searching."),
                SimpleNamespace(
                    type="tool_use", id="toolu_1", name="wp_search_posts", input={"query": "x"}
                ),
            ],
        )

    def stream(self, **kwargs):
        self.kwargs = kwargs
        return FakeStream()


def test_anthropic_wrapper_sends_tools_and_parses_tool_use():
    fake = SimpleNamespace(messages=FakeMessages())
    llm = AnthropicLLM(model="test-model", client=fake)
    turn = llm.research_turn("sys", [{"role": "user", "content": "hi"}], [{"name": "t"}])
    assert fake.messages.kwargs["tools"] == [{"name": "t"}]
    assert fake.messages.kwargs["model"] == "test-model"
    assert turn.tool_calls == [ToolCall("toolu_1", "wp_search_posts", {"query": "x"})]
    assert turn.content[1]["type"] == "tool_use"


def test_anthropic_wrapper_streams_tokens():
    fake = SimpleNamespace(messages=FakeMessages())
    tokens = []
    out = AnthropicLLM(model="m", client=fake).stream_text("sys", "prompt", tokens.append)
    assert tokens == ["Hello ", "brief"]
    assert out == "Hello brief"


# --- The OpenAI-compatible wrapper (used for Groq), with a fake client ------------------


def _ns(**kw):
    return SimpleNamespace(**kw)


class FakeChat:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.scripted.pop(0)


def _client(scripted):
    chat = FakeChat(scripted)
    return SimpleNamespace(chat=SimpleNamespace(completions=chat)), chat


def _tool_reply(call_id, name, args_json):
    fn = _ns(name=name, arguments=args_json)
    msg = _ns(content=None, tool_calls=[_ns(id=call_id, function=fn)])
    return _ns(choices=[_ns(message=msg, finish_reason="tool_calls")])


def _text_reply(text):
    return _ns(choices=[_ns(message=_ns(content=text, tool_calls=None), finish_reason="stop")])


def _stream(*parts):
    return iter([_ns(choices=[_ns(delta=_ns(content=p))]) for p in parts] + [_ns(choices=[])])


def test_openai_wrapper_translates_history_and_tools():
    history = [
        {"role": "user", "content": "Topic: x"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Searching."},
            {"type": "tool_use", "id": "c1", "name": "wp_search_posts", "input": {"query": "x"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "c1", "content": "{\"results\": []}"},
        ]},
    ]
    msgs = OpenAICompatibleLLM.to_openai_messages("sys", history)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    assert msgs[2]["tool_calls"][0]["function"] == {
        "name": "wp_search_posts", "arguments": "{\"query\": \"x\"}"
    }
    assert msgs[3] == {"role": "tool", "tool_call_id": "c1", "content": "{\"results\": []}"}
    tools = OpenAICompatibleLLM.to_openai_tools([{"name": "t", "description": "d",
                                                 "input_schema": {"type": "object"}}])
    assert tools[0]["function"]["parameters"] == {"type": "object"}


def test_openai_wrapper_parses_tool_calls_and_bad_arguments():
    client, _ = _client([
        _tool_reply("c1", "wp_get_post", "{\"post_id\": 103}"),
        _tool_reply("c2", "wp_get_post", "not json"),
    ])
    llm = OpenAICompatibleLLM(model="m", client=client)
    assert llm.research_turn("s", [{"role": "user", "content": "hi"}], []).tool_calls == [
        ToolCall("c1", "wp_get_post", {"post_id": 103})
    ]
    bad = llm.research_turn("s", [{"role": "user", "content": "hi"}], [])
    assert bad.tool_calls[0].input == {"_raw": "not json"}


def test_openai_wrapper_streams_tokens():
    client, chat = _client([_stream("Hello ", "brief")])
    tokens = []
    out = OpenAICompatibleLLM(model="m", client=client).stream_text("s", "p", tokens.append)
    assert tokens == ["Hello ", "brief"] and out == "Hello brief"
    assert chat.calls[0]["stream"] is True


def test_full_run_through_openai_wrapper():
    """The whole graph works with the OpenAI-format provider, not just the Anthropic one."""
    client, chat = _client([
        _tool_reply("c1", "wp_search_posts", "{\"query\": \"cold brew\"}"),
        _tool_reply("c2", "wp_get_post", "{\"post_id\": 107}"),
        _text_reply("Done."),
        _stream("See https://demo-roastery.test/cold-brew-recipe/ for the recipe."),
    ])
    state = run("cold brew", WP.site, OpenAICompatibleLLM(model="m", client=client), WP)
    assert list(state["fetched"]) == ["https://demo-roastery.test/cold-brew-recipe/"]
    assert state["uncited_urls"] == []
    # the second research call carried the first tool result back in OpenAI format
    assert chat.calls[1]["messages"][-1]["role"] == "tool"


def test_make_llm_picks_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    llm = make_llm("groq")
    assert llm.provider == "groq" and llm.model == "openai/gpt-oss-120b"
    import pytest

    with pytest.raises(ValueError):
        make_llm("nope")
