import json
from pathlib import Path

from wp_brief_agent.tools import TOOLS, execute_tool
from wp_brief_agent.wp_client import FixtureWPClient

WP = FixtureWPClient(Path(__file__).resolve().parent.parent / "fixtures" / "demo_site.json")


def test_tool_schemas_have_required_fields():
    for tool in TOOLS:
        assert {"name", "description", "input_schema"} <= set(tool)


def test_get_post_records_what_was_read():
    fetched = {}
    out = json.loads(execute_tool("wp_get_post", {"post_id": 103}, WP, fetched))
    assert out["id"] == 103
    assert list(fetched) == ["https://demo-roastery.test/storing-coffee-beans/"]


def test_search_does_not_count_as_reading():
    fetched = {}
    execute_tool("wp_search_posts", {"query": "espresso"}, WP, fetched)
    assert fetched == {}


def test_errors_go_back_to_the_model_instead_of_crashing():
    fetched = {}
    assert "error" in json.loads(execute_tool("wp_get_post", {"post_id": 999}, WP, fetched))
    assert "error" in json.loads(execute_tool("wp_get_post", {}, WP, fetched))
    assert "error" in json.loads(execute_tool("delete_site", {}, WP, fetched))
