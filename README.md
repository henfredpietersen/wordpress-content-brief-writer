# wp-brief-agent

A small agent that researches an existing WordPress site and writes a content brief for a new
article. It finds what the site already says on the topic, reads the most relevant posts, and
produces a brief with an outline, internal links and facts to reuse. The brief may only cite
pages the agent actually read, and a final check enforces this.

Built to show three things in one place: an agent workflow in **LangGraph**, direct use of the
**Anthropic Messages API** (tool use and streaming, no wrapper library), and a **WordPress REST**
integration.

> **How this was built:** AI-assisted, under my direction. I wrote the spec and the rules
> (read-only access, cite only what was read, a hard step limit, everything testable without a
> key). Claude generated the code. I reviewed it, ran the tests and eval, and can walk through
> every decision. I did not hand-type it.

## How it works

```
START -> research --(tool calls, under step limit)--> tools -> research
research --(model done, or step limit hit)--> write -> check -> END
```

| Node | What it does |
|---|---|
| `research` | Calls Claude with two tools. Claude decides what to search and which posts to read, or stops. |
| `tools` | Runs the calls against WordPress: `wp_search_posts` (search) and `wp_get_post` (read one post in full). Errors go back to the model as data, so one bad call doesn't end the run. |
| `write` | Streams the brief token by token. It is given **only** the posts that were read, not the whole conversation. |
| `check` | Lists any URL in the brief that was never read. Empty means grounded. The CLI exits with code 2 if it isn't. |

Guardrails:
- **Read-only.** The WordPress client only makes GET requests to public posts.
- **Step limit.** Research stops after `--max-steps` turns (default 6), so a model that keeps calling tools can't loop forever.
- **Grounding check.** Any invented URL is caught and reported.
- **Bounded input.** Each post is cut to 4,000 characters before it reaches the model.

## Run it

Requires Python 3.11+.

```bash
pip install -r requirements.txt
cp .env.example .env        # then add your ANTHROPIC_API_KEY

# Real Claude against any public WordPress site
python -m wp_brief_agent "cold brew" --site https://your-wordpress-site.com

# No key needed: scripted stand-in model against a fictional fixture site
python -m wp_brief_agent "cold brew" --offline
```

The model defaults to `claude-sonnet-5-5`. Set `ANTHROPIC_MODEL` in `.env` to change it.

## What was tested

**Unit and integration tests** (`pytest`, 15 tests, no key or network needed):
- WordPress client: HTML and entity cleanup, the REST request it sends (via a mocked HTTP transport), 404 handling.
- Tools: reading a post is recorded, searching is not, and bad input returns an error to the model instead of crashing.
- Graph: a full offline run; the grounding check catches an invented URL; a model that never stops calling tools is cut off at the step limit.
- Anthropic wrapper (with a fake client): tools are sent, `tool_use` blocks are parsed, streamed tokens arrive in order and add up to the final text.

**Eval** (`eval/run_eval.py`, 7 cases on the fixture site) measures retrieval (did it read the post a good researcher would read), grounding (only cites what it read) and whether the model stopped on its own.

| Mode | Retrieval hit rate | Grounded | Finished on its own | Avg research turns |
|---|---|---|---|---|
| Offline (scripted stand-in) | 1.00 | 1.00 | 1.00 | 3.86 |
| Live (Claude) | not run yet | | | |

**Read the offline row carefully.** It comes from a scripted stand-in that follows a fixed
recipe on a fictional site built for this repo, so it only proves the plumbing works. It says
nothing about model quality. For example, on the "matcha latte" case, where the site has no
relevant post, the stand-in still read the cold brew recipe because the word "recipe" matched.
Only a live run measures the real model:

```bash
python eval/run_eval.py --live
```

In a **GitHub Codespace**, dependencies install automatically and Codespaces asks for
`ANTHROPIC_API_KEY` when the codespace is created. Then run the command above in its terminal.

Or run it on GitHub with no local setup: add a repository secret named `ANTHROPIC_API_KEY`
(Settings > Secrets and variables > Actions), then open **Actions > Live eval > Run workflow**.
The results table appears on the run page, and the full results, including each brief, can be
downloaded as `live-eval-results`. It only runs when started by hand, so it never spends API
credit on a normal push.

**CI** (GitHub Actions) runs lint, the tests, the offline eval (it fails if any brief cites a
page that was never read) and a CLI smoke test on every push.

## Known limits

- Reads posts only, not pages, products or custom post types.
- The fixture site's search is a simple keyword ranking, not real WordPress search.
- No retrieval index: the agent relies on WordPress search, so results are only as good as the site's own search.
- The live eval has not been run yet, so there are no model-quality numbers.

## Layout

```
wp_brief_agent/
  graph.py       LangGraph workflow, prompts, grounding check
  llm.py         Anthropic API wrapper + offline scripted stand-in
  tools.py       tool definitions and executor
  wp_client.py   WordPress REST client + fixture client
  __main__.py    CLI
eval/            cases and eval runner
fixtures/        fictional WordPress site (REST-shaped JSON)
tests/           pytest suite
```
