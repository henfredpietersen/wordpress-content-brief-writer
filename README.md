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

## What was tested

**Unit and integration tests** (`pytest`, 20 tests, no key or network needed):
- WordPress client: HTML and entity cleanup, the REST request it sends (via a mocked HTTP transport), 404 handling.
- Tools: reading a post is recorded, searching is not, and bad input returns an error to the model instead of crashing.
- Graph: a full offline run; the grounding check catches an invented URL; a model that never stops calling tools is cut off at the step limit.
- Anthropic wrapper (fake client): tools are sent, `tool_use` blocks are parsed, streamed tokens arrive in order.
- OpenAI-compatible wrapper (fake client): history and tools are translated correctly, tool calls are parsed, malformed arguments don't crash, streaming works, and a full graph run completes through it.

**Eval** (`eval/run_eval.py`, 7 cases on the fixture site) measures retrieval (did it read the post a good researcher would read), grounding (only cites what it read) and whether the model stopped on its own.

| Run | Retrieval hit rate | Grounded | Finished on its own | Avg research turns |
|---|---|---|---|---|
| Offline (scripted stand-in) | 1.00 | 1.00 | 1.00 | 3.86 |
| Live: Groq | not run yet | | | |
| Live: Claude | not run yet | | | |

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
- The live evals have not been run yet, so there are no model-quality numbers.

## Layout

```
wp_brief_agent/
  graph.py       LangGraph workflow, prompts, grounding check
  llm.py         Anthropic and OpenAI-compatible (Groq) wrappers + offline stand-in
  tools.py       tool definitions and executor
  wp_client.py   WordPress REST client + fixture client
  __main__.py    CLI
eval/            cases and eval runner
fixtures/        fictional WordPress site (REST-shaped JSON)
tests/           pytest suite
```
