import json
from pathlib import Path

import httpx
import pytest

from wp_brief_agent import __main__ as cli
from wp_brief_agent.figma_client import (
    FigmaClient,
    FigmaError,
    extract_sections,
    load_design,
    parse_file_key,
)
from wp_brief_agent.graph import run
from wp_brief_agent.llm import ScriptedLLM
from wp_brief_agent.wp_client import FixtureWPClient

ROOT = Path(__file__).resolve().parent.parent
FIGMA = json.loads((ROOT / "fixtures" / "figma_landing.json").read_text())
SITE = ROOT / "fixtures" / "demo_site.json"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "value",
    [
        "https://www.figma.com/design/AbC123xyz789/Blog-template?node-id=0-1",
        "https://www.figma.com/file/AbC123xyz789/Blog-template",
        "AbC123xyz789",
    ],
)
def test_parse_file_key(value):
    assert parse_file_key(value) == "AbC123xyz789"


def test_parse_file_key_rejects_other_urls():
    with pytest.raises(FigmaError):
        parse_file_key("https://example.com/not-figma")


def test_sections_follow_reading_order_and_pick_the_largest_text_as_heading():
    sections = extract_sections(FIGMA)
    assert [s["frame"] for s in sections] == ["Hero", "Steps", "Newsletter CTA"]
    hero, steps, cta = sections
    assert hero["heading"] == "Article title goes here"
    assert hero["texts"] == ["Article title goes here", "Short intro under the title"]
    # nested groups are searched; top-to-bottom, then left-to-right
    assert steps["texts"] == ["How to do it", "Step 1", "Step 2"]
    assert cta["texts"] == ["Get fresh beans every month"]  # whitespace collapsed


def test_hidden_layers_and_frames_without_text_are_skipped():
    texts = [t for s in extract_sections(FIGMA) for t in s["texts"]]
    assert "Hidden draft note" not in texts and "Old title" not in texts


def test_client_sends_token_header_and_reads_the_file():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Figma-Token")
        return httpx.Response(200, json=FIGMA)

    design = load_design("https://www.figma.com/design/AbC123xyz789/x", "tok", _client(handler))
    assert seen == {"url": "https://api.figma.com/v1/files/AbC123xyz789", "token": "tok"}
    assert design["name"] == "Demo Roastery: blog post template"
    assert len(design["sections"]) == 3


@pytest.mark.parametrize("status,message", [(403, "refused the token"), (404, "not found")])
def test_client_errors_are_plain_english(status, message):
    client = FigmaClient("tok", _client(lambda r: httpx.Response(status)))
    with pytest.raises(FigmaError, match=message):
        client.get_file("AbC123xyz789")


def test_missing_token_is_reported():
    with pytest.raises(FigmaError, match="FIGMA_TOKEN"):
        FigmaClient("")


class PromptSpy(ScriptedLLM):
    def stream_text(self, system, prompt, on_token):
        self.prompt = prompt
        return super().stream_text(system, prompt, on_token)


def test_design_shapes_the_writer_prompt_and_grounding_still_holds():
    wp = FixtureWPClient(SITE)
    llm = PromptSpy()
    design = {"name": "Blog template", "sections": extract_sections(FIGMA)}
    state = run("cold brew", wp.site, llm, wp, design=design)
    assert "<design name=\"Blog template\">" in llm.prompt
    assert "Newsletter CTA" in llm.prompt and "Fit with the design" in llm.prompt
    assert "Do not take facts or URLs from it" in llm.prompt
    assert state["uncited_urls"] == []


def test_without_a_design_the_prompt_is_unchanged():
    wp = FixtureWPClient(SITE)
    llm = PromptSpy()
    run("cold brew", wp.site, llm, wp)
    assert "<design" not in llm.prompt and "Fit with the design" not in llm.prompt


def test_cli_passes_the_design_to_the_agent(monkeypatch, capsys):
    import wp_brief_agent.figma_client as fc

    fake = {"name": "Tpl", "key": "k", "sections": extract_sections(FIGMA)}
    monkeypatch.setattr(fc, "load_design", lambda url, token: fake)
    seen = {}
    real_run = cli.run

    def spy_run(*args, **kwargs):
        seen["design"] = kwargs.get("design")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(cli, "run", spy_run)
    assert cli.main(["cold brew", "--offline", "--figma", "AbC123xyz789"]) == 0
    assert seen["design"]["name"] == "Tpl"
    assert "Design: 'Tpl', 3 section(s) with text." in capsys.readouterr().out
