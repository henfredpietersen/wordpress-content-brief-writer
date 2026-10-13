"""Command line entry point.

    python -m wp_brief_agent "cold brew" --site https://your-wordpress-site.com
    python -m wp_brief_agent "cold brew" --offline     # no key, fictional fixture site
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .graph import run
from .wp_client import FixtureWPClient, WPClient

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "demo_site.json"


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env loader so no extra dependency is needed. Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    p = argparse.ArgumentParser(prog="wp_brief_agent", description=__doc__)
    p.add_argument("topic", help="What the new article is about.")
    p.add_argument("--site", default=os.getenv("WP_SITE_URL"), help="WordPress site URL.")
    p.add_argument("--offline", action="store_true", help="Scripted model + fixture site.")
    p.add_argument("--max-steps", type=int, default=6)
    p.add_argument(
        "--provider",
        choices=["anthropic", "groq"],
        default=os.getenv("LLM_PROVIDER") or "anthropic",
        help="Which model API to use (default: anthropic).",
    )
    args = p.parse_args(argv)

    if args.offline:
        from .llm import ScriptedLLM

        wp = FixtureWPClient(FIXTURE)
        site, llm = wp.site, ScriptedLLM()
    else:
        from .llm import make_llm, required_key

        if not args.site:
            p.error("--site is required (or set WP_SITE_URL), unless --offline is used.")
        key = required_key(args.provider)
        if not os.getenv(key):
            p.error(f"{key} is not set. Copy .env.example to .env, or use --offline.")
        wp, site, llm = WPClient(args.site), args.site, make_llm(args.provider)

    def show(token: str) -> None:
        sys.stdout.write(token)
        sys.stdout.flush()

    state = run(args.topic, site, llm, wp, max_steps=args.max_steps, on_token=show)

    print("\n---")
    print(f"Research turns: {state['steps']} ({state['stopped_reason']})")
    print(f"Posts read: {len(state['fetched'])}")
    for url, post in state["fetched"].items():
        print(f"  - {post['title']}: {url}")
    if state["uncited_urls"]:
        print("WARNING: the brief cites URLs that were never read:")
        for url in state["uncited_urls"]:
            print(f"  - {url}")
        return 2
    print("Grounding check: every URL in the brief was read.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
