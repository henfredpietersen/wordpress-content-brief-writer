"""Export what the interactive walkthrough shows, by running this repo's own code.

    python walkthrough/export.py

- The 7 eval cases are run through the real graph with the offline scripted stand-in
  on the fictional fixture site, and every search, read and write step is recorded.
- The grounding check examples are scored by the real find_uncited_urls().
- The live-model results and the Blacksmith example are read from README.md and
  examples/, so the page can't say anything the repo doesn't.
Tool-call ids and timings are left out so the export is identical on every run.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wp_brief_agent.graph import find_uncited_urls, run  # noqa: E402
from wp_brief_agent.llm import ScriptedLLM  # noqa: E402
from wp_brief_agent.wp_client import FixtureWPClient  # noqa: E402


def trace(state) -> list[dict]:
    steps = []
    for m in state["messages"][1:]:
        blocks = (
            m["content"]
            if isinstance(m["content"], list)
            else [{"type": "text", "text": m["content"]}]
        )
        for b in blocks:
            if b.get("type") == "tool_use" and b["name"] == "wp_search_posts":
                steps.append({"kind": "search", "query": b["input"].get("query", "")})
            elif b.get("type") == "tool_use" and b["name"] == "wp_get_post":
                steps.append({"kind": "read", "post_id": b["input"].get("post_id")})
            elif b.get("type") == "tool_result":
                data = json.loads(b["content"])
                last = steps[-1]
                if "error" in data:
                    last["error"] = data["error"]
                elif last["kind"] == "search":
                    last["results"] = [
                        {"id": r["id"], "title": r["title"]} for r in data.get("results", [])
                    ]
                else:
                    last["title"], last["url"] = data.get("title"), data.get("url")
            elif b.get("type") == "text" and m["role"] == "assistant":
                steps.append({"kind": "done", "text": b["text"]})
    return steps


def readme_live_table(readme: str) -> list[dict]:
    rows = []
    for line in readme.splitlines():
        if line.startswith("| Offline") or line.startswith("| Live:"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(
                {
                    "run": cells[0].replace("`", ""),
                    "retrieval": cells[1],
                    "grounded": cells[2],
                    "finished": cells[3],
                    "turns": cells[4],
                }
            )
    return rows


def example_brief(md: str) -> dict:
    header = re.search(r"<!--(.*?)-->", md, re.S).group(1).strip()
    title = re.search(r"## Working title\s*\n\*\*(.+?)\*\*", md).group(1)
    outline = re.findall(r"^\| \*\*(\d+\..+?)\*\* \|", md, re.M)
    link_section = md.split("## Existing posts to link", 1)[1].split("\n## ", 1)[0]
    links = re.findall(r"^\| ([^|]+?) \| (https://[^ |]+) \|$", link_section, re.M)
    facts = md.split("## Facts already on the site", 1)[1]
    fact_rows = [ln for ln in facts.splitlines() if ln.startswith("| ") and "https://" in ln]
    return {
        "run_note": header,
        "title": title,
        "outline": outline,
        "links": [{"title": t, "url": u} for t, u in links],
        "facts_count": len(fact_rows),
    }


def build() -> dict:
    wp = FixtureWPClient(ROOT / "fixtures" / "demo_site.json")
    site_posts = json.loads((ROOT / "fixtures" / "demo_site.json").read_text())
    posts = [
        {"id": int(p["id"]), "title": p["title"]["rendered"], "url": p["link"]}
        for p in site_posts["posts"]
    ]

    cases = []
    for case in json.loads((ROOT / "eval" / "cases.json").read_text()):
        st = run(case["topic"], wp.site, ScriptedLLM(), wp)
        read_ids = sorted(p["id"] for p in st["fetched"].values())
        cases.append(
            {
                "topic": case["topic"],
                "expect_read": case["expect_read"],
                "read_ids": read_ids,
                "hit": None if case["expect_read"] is None else case["expect_read"] in read_ids,
                "steps": trace(st),
                "research_turns": st["steps"],
                "stopped_reason": st["stopped_reason"],
                "brief": st["brief"],
                "uncited": st["uncited_urls"],
            }
        )

    base = next(c for c in cases if c["topic"] == "making cold brew at home")
    fetched = {u: {} for u in (s["url"] for s in base["steps"] if s["kind"] == "read")}
    read_url = next(iter(fetched))
    unread_url = next(p["url"] for p in posts if p["url"] not in fetched)
    variants = [
        ("As written", base["brief"]),
        (
            "A made-up link added",
            base["brief"] + f"\n- Further reading: {wp.site}/iced-coffee-guide/",
        ),
        (
            "A real link in a full-width bracket, the style that caused a false alarm",
            base["brief"] + f"\nSource: 【{read_url}】",
        ),
        ("A real link written as a markdown link", base["brief"] + f"\n[Read more]({read_url})"),
        (
            "A link to a real post on the site that the agent never opened",
            base["brief"] + f"\n- See also: {unread_url}",
        ),
    ]
    grounding = [
        {
            "label": label,
            "added": text[len(base["brief"]) :].strip(),
            "uncited": find_uncited_urls(text, fetched),
        }
        for label, text in variants
    ]

    readme = (ROOT / "README.md").read_text()
    tests = re.search(r"automated test suite of (\d+) tests", readme)
    return {
        "site": wp.site,
        "posts": posts,
        "cases": cases,
        "grounding": grounding,
        "live_table": readme_live_table(readme),
        "test_count": int(tests.group(1)) if tests else None,
        "example": example_brief((ROOT / "examples" / "blacksmith-ai-conversions.md").read_text()),
    }


if __name__ == "__main__":
    out = ROOT / "walkthrough" / "data.json"
    out.write_text(json.dumps(build(), indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"Wrote {out.relative_to(ROOT)}")
