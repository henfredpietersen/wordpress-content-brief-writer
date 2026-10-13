"""The two tools the model may call, in Anthropic tool-use format, and their executor."""

from __future__ import annotations

import json

from .wp_client import WordPressSource

TOOLS = [
    {
        "name": "wp_search_posts",
        "description": (
            "Search the WordPress site's published posts. Returns up to `limit` results with "
            "id, title, url and a short excerpt. Use short keyword queries (1-3 words) and "
            "try another query if the first returns nothing useful."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to search for."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "wp_get_post",
        "description": (
            "Fetch one post's full text by id (ids come from wp_search_posts). Only posts "
            "fetched with this tool may be cited in the final brief."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"post_id": {"type": "integer"}},
            "required": ["post_id"],
        },
    },
]


def execute_tool(name: str, args: dict, wp: WordPressSource, fetched: dict[str, dict]) -> str:
    """Run one tool call and return its result as a JSON string for the model.

    `fetched` maps url -> post for every post read in full; it is updated in place. The
    writing step only sees these posts, and the final check rejects any other URL.
    Errors are returned to the model as data rather than raised, so one bad call does
    not end the run.
    """
    try:
        if name == "wp_search_posts":
            results = wp.search_posts(str(args.get("query", "")), int(args.get("limit", 5)))
            return json.dumps({"results": results})
        if name == "wp_get_post":
            post = wp.get_post(int(args["post_id"]))
            if post is None:
                return json.dumps({"error": f"No post with id {args['post_id']}."})
            fetched[post["url"]] = post
            return json.dumps(post)
        return json.dumps({"error": f"Unknown tool {name!r}."})
    except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed silently
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
