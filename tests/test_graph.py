from pathlib import Path
from types import SimpleNamespace

from wp_brief_agent.graph import find_uncited_urls, run
from wp_brief_agent.llm import AnthropicLLM, ScriptedLLM, ToolCall, Turn
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
