# Google Workspace: briefs from a Sheet into Docs

An Apps Script that turns a Google Sheet into a queue for the brief agent. A content team adds
topics to the Sheet. The script sends each new row to the deployed API (`POST /brief`), writes the
brief into its own Google Doc, and writes the Doc link back to the row with the grounding result,
the number of posts read and the model used.

```
Sheet row (topic, optional site) -> POST /brief on the live service -> new Google Doc
                                                          \-> row: Done, Doc link, Grounded, Posts read, Model
```

| Column | Filled by | Meaning |
|---|---|---|
| Topic | you | What the new article is about |
| Site URL (optional) | you | A public WordPress site. Blank means the fictional demo site |
| Status | script | `Working...`, `Done`, or an error in plain English |
| Doc | script | Link to the brief |
| Grounded | script | `yes` if the brief only cites pages the agent read; `NO` if not (the Doc also says which URL) |
| Posts read, Model, Updated | script | What the agent read, which model ran, when |

## Set it up (about 5 minutes, no code to write)

1. Create a new Google Sheet.
2. **Extensions > Apps Script.** Replace the contents of `Code.gs` with this folder's `Code.gs`.
3. In Apps Script, **Project Settings > Show "appsscript.json" manifest file**, then replace that
   file's contents with this folder's `appsscript.json`. It limits the script to this one Sheet,
   creating Docs, calling the API, its own menu and its own hourly trigger.
4. Save, go back to the Sheet and reload it. A **Brief agent** menu appears.
5. **Brief agent > Set up this sheet.** Google asks you to approve the permissions above.
6. **Brief agent > Set API token** and paste the server's `API_TOKEN` (token only, no "Bearer").
   It is kept in your own Apps Script user properties, not in the Sheet or the code.
7. **Brief agent > Generate briefs for new rows.**

Optional: **Brief agent > Run every hour** checks for new rows hourly; **Stop hourly run** turns
it off.

## Design choices

- **Token kept out of the code and the Sheet.** Anyone with the Sheet can't read it.
- **Narrow permissions.** The manifest lists exactly what the script may do, rather than the
  broad default Google would otherwise ask for.
- **Wakes the service first.** The free host sleeps when idle, so the script polls `/health`
  before the slow live call.
- **At most 3 rows per run.** Apps Script stops any run after 6 minutes, and a live brief can take
  a minute; remaining rows are picked up on the next run.
- **Stops on errors that would repeat** (wrong token, hourly cap reached, server not configured)
  instead of failing every row. A failure on one site doesn't stop the next row, and a failed row
  is retried next run.
- **One run at a time.** A lock stops the hourly trigger and a manual run overlapping.

## Tested

`node --test workspace/test/*.test.js` (12 tests, runs in CI). The helpers are tested directly,
and the full run is tested against fake Sheet, Docs, HTTP and properties services: rows already
done are skipped, the token is sent as a bearer header, the row is filled in, an ungrounded brief
is flagged, a wrong token stops the run, one bad site doesn't stop the rest, and the per-run cap
holds. These tests don't prove Google's own services behave as faked; a run in a real Sheet does.

**Real run, 25 Oct 2026:** in a Google account, row "cold brew" went to the live API and came back
as a Google Doc (title, angle, outline, posts read). The row was filled in as Done, Grounded: yes,
1 post read, model Groq `openai/gpt-oss-120b`. Two things the real run showed that the fakes
could not:

- The **Set API token** box counts against Apps Script's 6-minute limit while it waits. Copy the
  token *before* opening the box, or the run times out and nothing is saved.
- A wrong token comes back as `Error: token rejected` in the Status column and stops the run, as
  designed. Re-setting the token and running again picks the row up, because it has no Doc yet.
