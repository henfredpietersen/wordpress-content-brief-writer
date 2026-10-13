from pathlib import Path

import httpx

from wp_brief_agent.wp_client import FixtureWPClient, WPClient, html_to_text

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "demo_site.json"


def test_html_to_text_strips_tags_and_decodes_entities():
    assert html_to_text("<p>Why It&#8217;s <b>Costing</b> You</p>") == "Why It’s Costing You"


def test_fixture_search_ranks_title_matches_first():
    wp = FixtureWPClient(FIXTURE)
    results = wp.search_posts("coffee grinder")
    assert results[0]["id"] == 101
    assert set(results[0]) == {"id", "title", "url", "excerpt"}


def test_fixture_get_post_missing_returns_none():
    assert FixtureWPClient(FIXTURE).get_post(999) is None


def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_live_client_calls_wordpress_rest_search():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["search"] = request.url.params["search"]
        return httpx.Response(
            200,
            json=[
                {
                    "id": 7,
                    "link": "https://site.test/a/",
                    "title": {"rendered": "A &amp; B"},
                    "excerpt": {"rendered": "<p>x</p>"},
                }
            ],
        )

    wp = WPClient("https://site.test/", client=_mock_client(handler))
    out = wp.search_posts("cold brew")
    assert seen == {"path": "/wp-json/wp/v2/posts", "search": "cold brew"}
    assert out == [{"id": 7, "title": "A & B", "url": "https://site.test/a/", "excerpt": "x"}]


def test_live_client_404_returns_none():
    wp = WPClient("https://site.test", client=_mock_client(lambda r: httpx.Response(404)))
    assert wp.get_post(5) is None
