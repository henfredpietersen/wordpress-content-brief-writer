# WordPress Content Brief Writer

An AI helper that reads a WordPress website and writes a **content brief**: a plan for a new article, based on what the site already says.

> *Previously named `wp-brief-agent`.*

## In plain English

**The problem.** Before someone writes a new article for a website, they usually need a brief: an outline, a list of existing pages to link to, and facts the site has already published. Putting that together means reading through a lot of old posts.

**What this does.** You give it a topic (for example "cold brew") and a WordPress website address. The AI searches the site, reads the most relevant posts, and writes a brief that contains:

- an outline for the new article
- which existing pages to link to
- facts from the site that can be reused

**Why you can trust the sources.** The brief is only allowed to mention pages the AI actually read. A final check looks for any web address in the brief that the AI never opened, and flags it. This guards against the AI making up sources.

**It can only look, not change.** It reads the public pages of a site. It cannot edit, post or delete anything.

**Ways to use it**

- Type one command on a computer (needs some technical setup).
- Use the **live demo**, which runs on a made-up example website: https://wp-brief-agent.onrender.com/demo?topic=cold%20brew. It sleeps when idle, so the first visit can take about a minute.
- Use the included **Google Sheet add-on**: list topics in a spreadsheet, click a menu item, and a finished brief appears in its own Google Doc.

## Where things stand

- It works, and it has been tested. There is an automated test suite of 65 tests, and the live version was checked end to end on 13 October 2026.
- The Google Sheet add-on was run for real on 25 October 2026: a topic typed into the Sheet came back as a finished Google Doc, marked as grounded.
- It was tested with a real AI model (Groq's `gpt-oss-120b`) on a made-up example site. The AI found the right post to read in all 6 cases where the site had one, and did not invent sources.
- It was also tested with Claude (`claude-sonnet-5-5`) on 26 October 2026: right post read in all 6 cases, no invented sources in all 7, and it finished every run on its own, in fewer steps than Groq.
- Only 7 test cases were run, on a fictional site. That is a quick health check, not a proper benchmark.
- It only reads blog posts, not other kinds of pages such as products.

## Plain-English glossary

| Term | What it means here |
|---|---|
| Content brief | A planning document for an article: outline, links and facts to reuse |
| AI agent | An AI that decides its own next steps (search, read a post, write) instead of answering once |
| Grounded | Every source the brief mentions was really read by the AI |
| API | A way for programs to talk to each other, such as a program asking an AI to do work |
| LangGraph | A tool for building multi-step AI workflows |
| Anthropic / Groq | Companies that provide the AI models this can use (Claude and others) |
| REST | The standard way a WordPress site shares its public content with programs |

*The Python package inside this repository is still called `wp_brief_agent`, so command examples below use that name.*

---

## For developers: technical documentation

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

### How it works

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

### Run it

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

### Web API and deployment

**Live:** https://wp-brief-agent.onrender.com, deployed on Render's free plan from this repo
via `render.yaml`. Try the public demo at
[/demo?topic=cold brew](https://wp-brief-agent.onrender.com/demo?topic=cold%20brew), or the
interactive docs at [/docs](https://wp-brief-agent.onrender.com/docs). It sleeps when idle,
so the first request can take about a minute.

**Checked end to end on 13 Oct 2026:** with a bearer token, the deployed service returned 200
on `POST /brief` (a full brief from Groq `openai/gpt-oss-120b`, with the posts it read) and on
`POST /brief/stream` (token events streamed as the brief was written), both against the
fictional demo site. Getting there surfaced four setup problems, each now either fixed in code or
reported by a clear error: the docs page dropping the token, a token pasted with "Bearer", a lost
docs login after reload, and stray whitespace in host settings.

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
asked. Render generates `API_TOKEN` itself, so no secret lives in the repo. Pushes only redeploy
automatically if Render's GitHub app has access to the repo; otherwise use **Manual Deploy >
Deploy latest commit** in Render. Free services sleep
after 15 minutes without traffic, so the first request after that takes about a minute.
A `Dockerfile` is included for any other container host.

### Google Workspace: a Sheet that writes briefs into Docs

`workspace/` holds an Apps Script for a Google Sheet. Each row is a topic (and optionally a
WordPress site). One menu click, or an hourly trigger, sends new rows to the live `/brief`
endpoint, writes each brief into its own Google Doc, and fills in the row with the Doc link,
the grounding result, the posts read and the model. The API token is kept in the user's Apps
Script properties, not in the Sheet or the code. Setup takes about 5 minutes and needs no code:
see [workspace/README.md](workspace/README.md).

**Run in a real Google account on 25 Oct 2026:** the topic "cold brew" went from the Sheet to the
live API and back as a Google Doc with title, angle, outline and the posts read. The row was
filled in as Done, Grounded: yes, 1 post read, Groq `openai/gpt-oss-120b`.

### Figma: shape the brief to a page design

Pass a Figma file and the brief's outline is written to fit the design's sections:

```bash
python -m wp_brief_agent "cold brew" --site https://your-wordpress-site.com --figma https://www.figma.com/design/<KEY>/<name>
python -m wp_brief_agent.figma https://www.figma.com/design/<KEY>/<name>   # just print the design's content map
```

`figma_client.py` reads the file through the Figma REST API (GET only, `X-Figma-Token` header,
token in `FIGMA_TOKEN`). For each top-level frame it collects the text layers in reading order
(top to bottom, then left to right), skips hidden layers, and takes the largest text as the
section heading. The writer receives this as a `<design>` block and adds a **Fit with the
design** section mapping each outline heading to a design section. Design text is layout
context only: the prompt forbids taking facts or URLs from it, so the grounding check is
unchanged. Tests use a recorded Figma-shaped file (`fixtures/figma_landing.json`), so no token is
needed for CI.

**Run live on 26 Oct 2026** (Claude `claude-sonnet-5-5`, a real Figma file, wordpress.org/news):
- The Figma API read worked first time: 7 frames with text from the "Figma basics" file.
- Claude read 3 real posts, the brief passed the grounding check, and the "Fit with the design"
  section said plainly that this practice file (a food-shop layout) is not an article template,
  marking each outline heading "new section" rather than forcing a fit.
- **The first attempt exposed a bug:** the brief stopped mid-section but still passed the URL
  check, because nothing looked at why the model stopped. Both wrappers now record the stop
  reason, a cut-off brief is flagged (`truncated`; the CLI exits 3), and the output limit was
  raised from 2,000 to 4,000 tokens. The rerun was complete.
- Reading outview.co.za from a Codespace failed at the connection level (the site refuses cloud
  servers), so the agent found no posts there and said so instead of inventing any.

### What was tested

**Unit and integration tests** (`pytest`, 65 tests, no key or network needed):
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
| Live: Claude `claude-sonnet-5-5` (26 Oct 2026) | 1.00 (6/6) | 1.00 (7/7) | 1.00 (7/7) | 3.14 |

\* A false positive in the grounding check, not a model error. See below.

**What the live Groq runs showed:**
- **Retrieval held up.** In both runs the model read the post a good researcher would read for all 6 topics that have one.
- **It didn't invent sources.** For the topic the site doesn't cover ("matcha latte recipe"), it read nothing and cited nothing.
- **Run 1 exposed a bug in the grounding check itself.** One brief cited a page the agent *had* read, but wrapped it as `【https://…】`, a citation style this model uses. The URL pattern treated the full-width bracket as part of the URL, so a correct citation was flagged as unread. The fix restricts matching to valid URL characters. A regression test covers this bracket, markdown links and other wrappers, and still catches a genuinely unread URL. Run 2, with the fix, was 7/7 grounded.
- **The model often wants more than 6 research turns.** In run 2, 4 of 7 runs were stopped by the step limit rather than finishing on their own. The brief is still written from what was read, and stayed grounded, but this is the next thing to tune (the limit, or the research prompt).
- **Runs vary.** "Finished on its own" moved from 4/7 to 3/7 between runs. With 7 cases, small differences are noise, not a trend.

**What the live Claude run showed:**
- **Same retrieval and grounding as Groq, and it stopped on its own every time.** All 7 runs finished before the 6-turn limit, averaging 3.14 research turns against Groq's 5.71. On this fixture site, the step-limit issue seen with Groq didn't appear with Claude.
- **On the topic the site doesn't cover ("matcha latte recipe"), it read two unrelated posts** before writing, where Groq read none. It still cited only what it read (grounded), so the check passed; whether reading those posts was useful is a judgment call, not a failure.
- **One run on 7 cases.** Treat it as a health check, not a benchmark comparison between models.

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

**Google Workspace script** (`node --test workspace/test/*.test.js`, 12 tests): helpers, plus the
full Sheet-to-Doc run against fake Google services. See [workspace/README.md](workspace/README.md).

**CI** (GitHub Actions) runs lint, the tests, the offline eval (it fails if any brief cites a
page that was never read), a CLI smoke test and the Workspace script tests on every push.

### Known limits

- Reads posts only, not pages, products or custom post types.
- The fixture site's search is a simple keyword ranking, not real WordPress search.
- No retrieval index: the agent relies on WordPress search, so results are only as good as the site's own search.
- Claude has been run live once and Groq twice, each on the same 7 cases; see above.
- 7 eval cases on a fictional site is a smoke test, not a benchmark.
- On Groq, the model often reaches the 6-turn research limit before stopping on its own (Claude did not, in its one run).

### Layout

```
wp_brief_agent/
  graph.py       LangGraph workflow, prompts, grounding check
  llm.py         Anthropic and OpenAI-compatible (Groq) wrappers + offline stand-in
  tools.py       tool definitions and executor
  wp_client.py   WordPress REST client + fixture client
  api.py         FastAPI web service
  __main__.py    CLI
workspace/       Google Apps Script: Sheet queue -> live API -> Google Docs (+ Node tests)
eval/            cases and eval runner
fixtures/        fictional WordPress site (REST-shaped JSON)
tests/           pytest suite
```
