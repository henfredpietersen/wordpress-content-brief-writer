"""Tiny eval for wp-brief-agent, run against the fictional fixture site.

    python eval/run_eval.py            # offline: scripted stand-in model, no key needed
    python eval/run_eval.py --live     # real Claude via the Anthropic API (needs ANTHROPIC_API_KEY)

Per case it checks:
- retrieval: did the agent read the post a good researcher should read? (cases with
  expect_read = null have no relevant post and are skipped for this metric)
- grounded:  does the brief cite only URLs the agent actually read?
- finished:  did the model stop on its own before the step limit?

Offline numbers come from a scripted stand-in, so they test the plumbing, not quality.
Only --live numbers say anything about the model.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wp_brief_agent.__main__ import _load_dotenv  # noqa: E402
from wp_brief_agent.graph import run  # noqa: E402
from wp_brief_agent.llm import AnthropicLLM, ScriptedLLM  # noqa: E402
from wp_brief_agent.wp_client import FixtureWPClient  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--max-steps", type=int, default=6)
    p.add_argument("--summary-md", help="Also write a markdown results table to this path.")
    args = p.parse_args()
    _load_dotenv(ROOT / ".env")

    wp = FixtureWPClient(ROOT / "fixtures" / "demo_site.json")
    cases = json.loads((ROOT / "eval" / "cases.json").read_text())
    mode = "live" if args.live else "offline"

    rows = []
    for case in cases:
        llm = AnthropicLLM() if args.live else ScriptedLLM()
        start = time.perf_counter()
        state = run(case["topic"], wp.site, llm, wp, max_steps=args.max_steps)
        read_ids = sorted(p["id"] for p in state["fetched"].values())
        rows.append(
            {
                "topic": case["topic"],
                "expect_read": case["expect_read"],
                "read_ids": read_ids,
                "retrieval_hit": None
                if case["expect_read"] is None
                else case["expect_read"] in read_ids,
                "grounded": state["uncited_urls"] == [],
                "uncited_urls": state["uncited_urls"],
                "finished": state["stopped_reason"] == "model_finished",
                "research_turns": state["steps"],
                "seconds": round(time.perf_counter() - start, 2),
                "brief": state["brief"],
            }
        )

    scored = [r for r in rows if r["retrieval_hit"] is not None]
    summary = {
        "mode": mode,
        "model": llm.model if args.live else "scripted stand-in",
        "cases": len(rows),
        "retrieval_hit_rate": round(sum(r["retrieval_hit"] for r in scored) / len(scored), 2),
        "grounded_rate": round(sum(r["grounded"] for r in rows) / len(rows), 2),
        "finished_rate": round(sum(r["finished"] for r in rows) / len(rows), 2),
        "avg_research_turns": round(sum(r["research_turns"] for r in rows) / len(rows), 2),
    }

    print(f"{'topic':45} {'expect':>6} {'read':14} {'hit':>5} {'grounded':>8} {'turns':>5}")
    for r in rows:
        hit = "-" if r["retrieval_hit"] is None else ("yes" if r["retrieval_hit"] else "NO")
        print(
            f"{r['topic'][:45]:45} {str(r['expect_read']):>6} {str(r['read_ids']):14} "
            f"{hit:>5} {('yes' if r['grounded'] else 'NO'):>8} {r['research_turns']:>5}"
        )
    print(json.dumps(summary, indent=2))

    out = ROOT / "eval" / "results"
    out.mkdir(exist_ok=True)
    (out / f"{mode}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    if args.summary_md:
        Path(args.summary_md).write_text(to_markdown(summary, rows), encoding="utf-8")
    # Fail CI if any brief cites a page that was never read.
    return 0 if summary["grounded_rate"] == 1.0 else 1


def to_markdown(summary: dict, rows: list[dict]) -> str:
    lines = [
        f"## Eval results ({summary['mode']}, model: {summary['model']})",
        "",
        "| Retrieval hit rate | Grounded | Finished on its own | Avg research turns |",
        "|---|---|---|---|",
        f"| {summary['retrieval_hit_rate']} | {summary['grounded_rate']} "
        f"| {summary['finished_rate']} | {summary['avg_research_turns']} |",
        "",
        "| Topic | Expected post | Posts read | Hit | Grounded | Turns | Seconds |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        hit = "-" if r["retrieval_hit"] is None else ("yes" if r["retrieval_hit"] else "NO")
        lines.append(
            f"| {r['topic']} | {r['expect_read']} | {r['read_ids']} | {hit} "
            f"| {'yes' if r['grounded'] else 'NO'} | {r['research_turns']} | {r['seconds']} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
