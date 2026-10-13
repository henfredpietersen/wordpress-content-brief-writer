# wp-brief-agent

A small agent that researches an existing WordPress site and writes a content brief for a new
article. It finds what the site already says on the topic, reads the most relevant posts, and
produces a brief with an outline, internal links and facts to reuse. The brief may only cite
pages the agent actually read, and a final check enforces this.

Built to show four things in one place: an agent workflow in **LangGraph**, direct use of the
**Anthropic Messages API** (tool use and streaming, no wrapper library), a provider layer that
runs the same graph on **Groq** through its OpenAI-compatible API, and a **WordPress REST**
integration.

> **How this was built:** AI-assisted, under my direction. I wrote the spec and the rules
> (read-only access, cite only what was read, a hard step limit, everything testable without a
> key, one graph for any model provider). Claude generated the code. I reviewed it, ran the
> tests and eval, and can walk through every decision. I did not hand-type it.

## How it works

```
START -> research --(tool calls, under step limit)--> tools -> research
research --(model done, or step limit hit)--> write -> check -> END
```

| Node | What it does |
|---|---|
| `research` | Calls the model with two tools. The model decides what to search and which posts to read, or stops. |
| `tools` | Runs the calls against WordPress: `wp_search_posts` (search) and `wp_get_post` (read one post in full). Errors go back to the model as data, so one bad call doesn't end the run. |
| `write` | Streams the brief token by token. It is given **only** the posts that were read, not the whole conversation. |
| `check` | Lists any URL in the brief that was never read. Empty means grounded. The CLI exits with code 2 if it isn't. |

**Providers.** The graph keeps its history in Anthropic's format (`tool_use` / `tool_result`
blocks). `AnthropicLLM` sends it as-is. `OpenAICompatibleLLM` translates it to and from the
OpenAI chat format (`tool_calls` / `tool` messages), which is what Groq accepts. The graph
itself never knows which provider it is talking to.

Guardrails:
- **Read-only.** The WordPress client only makes GET requests to public posts.
- **Step limit.** Research stops after `--max-steps` turns (default 6), so a model that keeps calling tools can't loop forever.
- **Grounding check.** Any invented URL is caught and reported.
- **Bounded input.** Each post is cut to 4,000 characters before it reaches the model.
- **Malformed tool arguments** from a model are passed back to it as an error, not a crash.

## Run it

Requires Python 3.11+.

```bash
pip install -r requirements.txt
cp .env.example .env        # then add ANTHROPIC_API_KEY and/or GROQ_API_KEY

# Claude against any public WordPress site
python -m wp_brief_agent "cold brew" --site https://your-wordpress-site.com

# Same, on Groq (free plan available)
python -m wp_brief_agent "cold brew" --site https://your-wordpress-site.com --provider groq

# No key needed: scripted stand-in model against a fictional fixture site
python -m wp_brief_agent "cold brew" --offline
```

Defaults: `claude-sonnet-5-5` on Anthropic, `openai/gpt-oss-120b` on Groq. Override with
`ANTHROPIC_MODEL` or `GROQ_MODEL` in `.env`.

## Web API and deployment

**Live:** https://wp-brief-agent.onrender.com, deployed on Render's free plan from this repo
via `render.yaml`. Try the public demo at
[/demo?topic=cold brew](https://wp-brief-agent.onrender.com/demo?topic=cold%20brew), or the
interactive docs at [/docs](https://wp-brief-agent.onrender.com/docs). It sleeps when idle,
so the first request can take about a minute.

The same agent runs as a small FastAPI service (`wp_brief_agent/api.py`):

| Route | Access | What it does |
|---|---|---|
| `GET /health` | public | Liveness check |
| `GET /demo?topic=…` | public, free | Scripted stand-in on the fictional site: shows the flow at no cost |
| `POST /brief` | bearer token | Live model; returns the brief, the posts read and the grounding result as JSON |
| `POST /brief/stream` | bearer token | Same, streamed as server-sent events (`token` events, then `done`) |
| `GET /docs` | public | Interactive API docs |

Live routes spend model quota, so they are off unless `API_TOKEN` is set, they compare the
token in constant time, they cap live calls per hour (`LIVE_REQUESTS_PER_HOUR`, default 30), and
`site_url` must be a public `https://` domain, not localhost, a private name or an IP address.

Run locally: `uvicorn wp_brief_agent.api:app --reload`, then open `http://127.0.0.1:8000/docs`.

**Deploy on Render (free plan):** `render.yaml` is a Render Blueprint. In Render, choose
**New > Blueprint**, pick this repo, and enter `GROQ_API_KEY` (and/or `ANTHROPIC_API_KEY`) when
asked. Render generates `API_TOKEN` itself, so no secret lives in the repo. Free services sleep
after 15 minutes without traffic, so the first request after that takes about a minute.
A `Dockerfile` is included for any other container host.

## What was tested

**Unit and integration tests** (`pytest`, 41 tests, no key or network needed):
- WordPress client: HTML and entity cleanup, the REST request it sends (via a mocked HTTP transport), 404 handling.
- Tools: reading a post is recorded, searching is not, and bad input returns an error to the model instead of crashing.
- Graph: a full offline run; the grounding check catches an invented URL; a model that never stops calling tools is cut off at the step limit.
- Anthropic wrapper (fake client): tools are sent, `tool_use` blocks are parsed, streamed tokens arrive in order.
- OpenAI-compatible wrapper (fake client): history and tools are translated correctly, tool calls are parsed, malformed arguments don't crash, streaming works, and a full graph run completes through it.
- Web API: the public demo works and is grounded; live routes are closed without a configured token, reject a missing or wrong token, enforce the hourly cap, report a missing provider key, refuse non-public `site_url`s, and the stream sends token events that add up to the final brief. The docs page declares the token as a bearer login (a plain `Authorization` header parameter is silently dropped by Swagger UI), and its example body is a valid request.

**Eval** (`eval/run_eval.py`, 7 cases on the fixture site) measures retrieval (did it read the post a good researcher would read), grounding (only cites what it read) and whether the model stopped on its own.

| Run | Retrieval hit rate | Grounded | Finished on its own | Avg research turns |
|---|---|---|---|---|
| Offline (scripted stand-in) | 1.00 | 1.00 | 1.00 | 3.86 |
| Live: Groq `openai/gpt-oss-120b`, run 1 (13 Oct 2026) | 1.00 (6/6) | 0.86 (6/7)* | 0.57 (4/7) | 5.29 |
| Live: Groq `openai/gpt-oss-120b`, run 2, after checker fix | 1.00 (6/6) | 1.00 (7/7) | 0.43 (3/7) | 5.71 |
| Live: Claude | not run yet (needs API credit) | | | |

\* A false positive in the grounding check, not a model error. See below.

**What the live Groq runs showed:**
- **Retrieval held up.** In both runs the model read the post a good researcher would read for all 6 topics that have one.
- **It didn't invent sources.** For the topic the site doesn't cover ("matcha latte recipe"), it read nothing and cited nothing.
- **Run 1 exposed a bug in the grounding check itself.** One brief cited a page the agent *had* read, but wrapped it as `【https://…】`, a citation style this model uses. The URL pattern treated the full-width bracket as part of the URL, so a correct citation was flagged as unread. The fix restricts matching to valid URL characters. A regression test covers this bracket, markdown links and other wrappers, and still catches a genuinely unread URL. Run 2, with the fix, was 7/7 grounded.
- **The model often wants more than 6 research turns.** In run 2, 4 of 7 runs were stopped by the step limit rather than finishing on their own. The brief is still written from what was read, and stayed grounded, but this is the next thing to tune (the limit, or the research prompt).
- **Runs vary.** "Finished on its own" moved from 4/7 to 3/7 between runs. With 7 cases, small differences are noise, not a trend.

**Read the offline row carefully.** It comes from a scripted stand-in that follows a fixed
recipe on a fictional site built for this repo, so it only proves the plumbing works. It says
nothing about model quality. For example, on the "matcha latte" case, where the site has no
relevant post, the stand-in still read the cold brew recipe because the word "recipe" matched.
Only live runs measure real models:

```bash
python eval/run_eval.py --live                   # Claude
python eval/run_eval.py --live --provider groq   # Groq
```

In a **GitHub Codespace**, dependencies install automatically and Codespaces asks for
`ANTHROPIC_API_KEY` and `GROQ_API_KEY` when the codespace is created. Then run the commands
above in its terminal.

Or run it on GitHub with no local setup: add a repository secret (`ANTHROPIC_API_KEY` or
`GROQ_API_KEY`, under Settings > Secrets and variables > Actions), then open **Actions > Live
eval > Run workflow** and pick the provider. The results table appears on the run page, and the
full results, including each brief, can be downloaded. It only runs when started by hand, so it
never spends API credit on a normal push.

**CI** (GitHub Actions) runs lint, the tests, the offline eval (it fails if any brief cites a
page that was never read) and a CLI smoke test on every push.

## Known limits

- Reads posts only, not pages, products or custom post types.
- The fixture site's search is a simple keyword ranking, not real WordPress search.
- No retrieval index: the agent relies on WordPress search, so results are only as good as the site's own search.
- Claude has not been run live yet (the account needs API credit), so there are no Claude numbers. Groq has been run twice; see above.
- 7 eval cases on a fictional site is a smoke test, not a benchmark.
- The model often reaches the 6-turn research limit before stopping on its own.

## Layout

```
wp_brief_agent/
  graph.py       LangGraph workflow, prompts, grounding check
  llm.py         Anthropic and OpenAI-compatible (Groq) wrappers + offline stand-in
  tools.py       tool definitions and executor
  wp_client.py   WordPress REST client + fixture client
  api.py         FastAPI web service
  __main__.py    CLI
eval/            cases and eval runner
fixtures/        fictional WordPress site (REST-shaped JSON)
tests/           pytest suite
```
