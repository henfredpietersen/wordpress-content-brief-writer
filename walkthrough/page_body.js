  // ------------------------------------------------------------ extra styles
  CSS += "\n" + [
    ".grad{background:linear-gradient(90deg,#ffffff 0%,#ffb27a 45%,var(--orange) 100%);-webkit-background-clip:text;background-clip:text;color:transparent}",
    ".posts{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;margin-top:12px}",
    ".post{padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--panel2);font-size:.82rem;transition:border-color .3s,background .3s}",
    ".post small{display:block;color:var(--dim);font-size:.72rem;margin-bottom:3px}",
    ".post.found{border-color:rgba(79,209,255,.6);background:rgba(79,209,255,.08)}",
    ".post.read{border-color:rgba(52,211,153,.7);background:rgba(52,211,153,.12)}",
    ".post.expect{box-shadow:inset 0 0 0 1px rgba(255,178,122,.7)}",
    ".log{display:grid;gap:8px;margin-top:14px}",
    ".ev{display:grid;grid-template-columns:30px 1fr;gap:10px;align-items:start;padding:10px 12px;border-radius:10px;background:var(--panel2);border:1px solid var(--line);font-size:.88rem}",
    ".ev .ic{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.8rem}",
    ".ev b{color:var(--text)}.ev span{color:var(--dim)}",
    "pre.brief{white-space:pre-wrap;word-break:break-word;font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#d6dbe6;",
    "background:#0b0f19;border:1px solid var(--line);border-radius:10px;padding:12px;margin:0;max-height:300px;overflow:auto}",
    ".added{font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:rgba(255,178,122,.1);border:1px dashed rgba(255,178,122,.5);",
    "border-radius:8px;padding:8px 10px;color:#ffd7b8;word-break:break-all;margin-top:10px}",
    ".tbl2{display:grid;gap:8px;margin-top:12px}",
    ".lrun{padding:12px;border-radius:12px;background:var(--panel2);border:1px solid var(--line)}",
    ".lrun h3{font-size:.92rem;margin:0 0 8px}",
    ".mrow{display:grid;grid-template-columns:150px 1fr 70px;gap:10px;align-items:center;font-size:.82rem;margin:5px 0}",
    ".mrow .track{height:10px;border-radius:5px;background:rgba(255,255,255,.06);overflow:hidden}",
    ".mrow .fill{height:100%;border-radius:5px}",
    ".bugs{display:grid;gap:8px;margin-top:10px}",
    ".bug{display:grid;grid-template-columns:24px 1fr;gap:10px;font-size:.88rem;padding:10px 12px;border-radius:10px;background:var(--panel2)}",
    ".bug i{font-style:normal;font-weight:800;color:var(--warn)}",
    ".grid2{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));margin-top:12px}",
    ".where{padding:14px;border-radius:12px;background:var(--panel2);border:1px solid var(--line)}",
    ".where h3{margin:0 0 6px;font-size:.95rem}.where p{font-size:.86rem;margin:0}",
    "ol.outl{margin:8px 0 0;padding-left:20px;color:var(--text);font-size:.88rem}ol.outl li{margin:3px 0}",
    ".try{border:1px solid rgba(255,122,69,.45);background:linear-gradient(180deg,rgba(255,122,69,.08),rgba(255,255,255,.03))}",
    ".form{display:grid;gap:10px;grid-template-columns:1fr 1fr auto;align-items:end}",
    ".form label{display:grid;gap:5px;font-size:.8rem;color:var(--dim)}",
    ".form input{font:inherit;font-size:.95rem;color:var(--text);background:#0b0f19;border:1px solid var(--line);border-radius:10px;padding:10px 12px;min-width:0}",
    ".form input:focus{outline:2px solid rgba(79,209,255,.5);border-color:transparent}",
    ".status{font-size:.82rem;color:var(--dim);margin-top:10px;display:flex;gap:8px;align-items:baseline}",
    ".dot{width:8px;height:8px;border-radius:50%;background:var(--dim);display:inline-block;flex:none}",
    ".dot.on{background:var(--ok)}.dot.wait{background:var(--warn);animation:pulse 1s infinite}.dot.off{background:var(--bad)}",
    "@keyframes pulse{50%{opacity:.3}}",
    ".msg{margin-top:12px;padding:12px 14px;border-radius:12px;font-size:.88rem;background:var(--panel2);border:1px solid var(--line)}",
    ".msg.bad{background:rgba(248,113,113,.1);border-color:rgba(248,113,113,.45)}",
    ".fine{font-size:.78rem;color:var(--dim);margin:12px 0 0}",
    "@media (max-width:520px){.mrow{grid-template-columns:110px 1fr 62px}}",
    "@media (max-width:720px){.form{grid-template-columns:1fr}.form .btn{width:100%}}"
  ].join("\n");

  var REPO = "https://github.com/henfredpietersen/wordpress-content-brief-writer";
  var EXAMPLE = REPO + "/blob/main/examples/blacksmith-ai-conversions.md";
  var postsById = {};
  D.posts.forEach(function (p) { postsById[p.id] = p; });
  function short(u) { return String(u).replace(D.site, ""); }

  // ------------------------------------------------------------- step 1
  var cIdx = D.cases.findIndex(function (c) { return c.topic === "making cold brew at home"; });
  if (cIdx < 0) cIdx = 0;
  var shown = 0; // how many timeline events are revealed

  function events(c) {
    var ev = [];
    c.steps.forEach(function (s) {
      if (s.kind === "search") ev.push({ t: "search", s: s });
      else if (s.kind === "read") ev.push({ t: "read", s: s });
      else if (s.kind === "done") ev.push({ t: "done", s: s });
    });
    ev.push({ t: "write" }, { t: "check" });
    return ev;
  }
  function postGrid(c, upto) {
    var found = {}, read = {};
    events(c).slice(0, upto).forEach(function (e) {
      if (e.t === "search") (e.s.results || []).forEach(function (r) { found[r.id] = true; });
      if (e.t === "read") read[e.s.post_id] = true;
    });
    return "<div class='posts'>" + D.posts.map(function (p) {
      var cls = read[p.id] ? " read" : found[p.id] ? " found" : "";
      return "<div class='post" + cls + (c.expect_read === p.id ? " expect" : "") + "'><small>Post " + p.id +
        (c.expect_read === p.id ? " · the one to read" : "") + "</small>" + esc(p.title) + "</div>";
    }).join("") + "</div>";
  }
  function eventHTML(c, e) {
    if (e.t === "search") {
      return "<div class='ev'><div class='ic' style='background:rgba(79,209,255,.15);color:var(--cyan)'>S</div><div><b>Search the site</b> <span>for “" +
        esc(e.s.query) + "”</span><br><span>" + (e.s.results || []).length + ((e.s.results || []).length === 1 ? " result: " : " results: ") +
        (e.s.results || []).map(function (r) { return esc(r.title); }).join(" · ") + "</span></div></div>";
    }
    if (e.t === "read") {
      return "<div class='ev'><div class='ic' style='background:rgba(52,211,153,.15);color:var(--ok)'>R</div><div><b>Read post " + e.s.post_id +
        "</b> <span>“" + esc(e.s.title || (postsById[e.s.post_id] || {}).title) + "”</span></div></div>";
    }
    if (e.t === "done") {
      return "<div class='ev'><div class='ic' style='background:var(--panel);color:var(--dim)'>✓</div><div><b>Stops researching on its own</b> <span>after " +
        c.research_turns + " turns (limit 6)</span></div></div>";
    }
    if (e.t === "write") {
      return "<div class='ev'><div class='ic' style='background:rgba(255,122,69,.15);color:var(--orange)'>W</div><div><b>Write the brief</b> <span>from the " +
        c.read_ids.length + (c.read_ids.length === 1 ? " post" : " posts") + " it read, and nothing else</span><pre class='brief' style='margin-top:8px'>" + esc(c.brief) + "</pre></div></div>";
    }
    var ok = c.uncited.length === 0;
    return "<div class='ev'><div class='ic' style='background:" + (ok ? "rgba(52,211,153,.15);color:var(--ok)" : "rgba(248,113,113,.15);color:var(--bad)") +
      "'>" + (ok ? "✓" : "✕") + "</div><div><b>Check every link in the brief</b> <span>" +
      (ok ? "Grounded: every link points to a post it read." : "Not grounded: " + c.uncited.map(esc).join(", ")) + "</span></div></div>";
  }
  function runHTML() {
    var c = D.cases[cIdx], ev = events(c);
    var h = postGrid(c, shown) + "<div class='legend' style='margin-top:8px'><span><i class='sw' style='background:rgba(79,209,255,.6)'></i>Came up in search</span>" +
      "<span><i class='sw' style='background:rgba(52,211,153,.7)'></i>Read in full</span><span><i class='sw' style='background:rgba(255,178,122,.7)'></i>The post a good researcher would read</span></div>";
    h += "<div class='log'>" + ev.slice(0, shown).map(function (e) { return eventHTML(c, e); }).join("") + "</div>";
    if (shown >= ev.length) {
      var verdict = c.expect_read === null
        ? "The site has no post on this. The stand-in still read “" + esc((postsById[c.read_ids[0]] || {}).title) +
          "” because the word “recipe” matched. That's why the offline run only proves the plumbing; judging relevance needs a real model."
        : c.hit ? "It read post " + c.expect_read + ", the one a good researcher would read." : "It missed post " + c.expect_read + ".";
      h += "<div class='outcome'>" + verdict + "</div>";
    }
    return h;
  }

  // ------------------------------------------------------------- step 2
  var gIdx = 1;
  function groundHTML() {
    var g = D.grounding[gIdx];
    var ok = g.uncited.length === 0;
    return (g.added ? "<div class='added'>Added to the brief: " + esc(g.added) + "</div>" : "<p style='font-size:.88rem;margin:10px 0 0'>The brief exactly as the agent wrote it.</p>") +
      "<div class='verdict " + (ok ? "ok" : "bad") + "'>" + (ok ? "✓ Grounded. Every link points to a post the agent read." :
        "✕ Flagged. Never read: " + g.uncited.map(function (u) { return esc(short(u)); }).join(", ") + ". The command line run fails with an error.") + "</div>";
  }

  // ------------------------------------------------------------- step 3
  function pctOf(cell) { var m = String(cell).match(/^([\d.]+)/); return m ? parseFloat(m[1]) : 0; }
  var liveRows = D.live_table.filter(function (r) { return r.run.indexOf("Live") === 0; });
  var offRow = D.live_table.filter(function (r) { return r.run.indexOf("Offline") === 0; })[0];
  function metric(label, cell, color) {
    var v = pctOf(cell);
    return "<div class='mrow'><span>" + label + "</span><div class='track'><div class='fill' style='width:" + (v * 100).toFixed(0) +
      "%;background:" + color + "'></div></div><span style='text-align:right;font-variant-numeric:tabular-nums'>" + esc(String(cell).replace("*", "")) + "</span></div>";
  }

  // ------------------------------------------------------------- try it live
  var API = "https://wp-brief-agent.onrender.com";
  var tryState = { enabled: false, busy: false };

  function setStatus(kind, text) {
    $("[data-tstatus]").innerHTML = "<i class='dot " + kind + "'></i><span>" + text + "</span>";
  }
  function timeout(ms) {
    if (window.AbortController) { var c = new AbortController(); setTimeout(function () { c.abort(); }, ms); return c.signal; }
    return undefined;
  }
  function loadStatus(attempt) {
    attempt = attempt || 0;
    if (attempt === 0) setStatus("wait", "Checking the server…");
    fetch(API + "/try/status", { signal: timeout(attempt === 0 ? 8000 : 70000) })
      .then(function (r) { return r.json(); })
      .then(function (s) {
        tryState.enabled = s.enabled && s.runs_left_today > 0;
        if (!s.enabled) setStatus("off", "Live runs are switched off right now. The walkthrough below still works.");
        else if (s.runs_left_today <= 0) setStatus("off", "Today's " + s.runs_per_day + " public runs are used up. Please try again tomorrow.");
        else setStatus("on", "Server awake · " + s.runs_left_today + " of " + s.runs_per_day + " public runs left today · " +
          s.per_visitor_per_hour + " per visitor per hour");
        $("[data-trun]").disabled = !tryState.enabled || tryState.busy;
      })
      .catch(function () {
        if (attempt < 1) {
          setStatus("wait", "Waking the server. It's on free hosting that sleeps when idle, so this can take up to a minute…");
          loadStatus(attempt + 1);
        } else {
          setStatus("off", "Couldn't reach the server. It may be restarting; try reloading in a minute.");
        }
      });
  }
  function normSite(v) {
    v = String(v || "").trim();
    if (v && !/^https?:\/\//i.test(v)) v = "https://" + v;
    return v.replace(/\/+$/, "");
  }
  function addLog(html) {
    var d = document.createElement("div");
    d.innerHTML = html;
    $("[data-tlog]").appendChild(d.firstChild);
  }
  function liveEvent(kind, d) {
    if (kind === "search") {
      var n = (d.found || []).length;
      addLog("<div class='ev'><div class='ic' style='background:rgba(79,209,255,.15);color:var(--cyan)'>S</div><div><b>Searched the site</b> <span>for “" +
        esc(d.query) + "”</span><br><span>" + (d.error ? esc(d.error) : n + (n === 1 ? " result" : " results") +
        (n ? ": " + d.found.map(esc).join(" · ") : "")) + "</span></div></div>");
    } else if (kind === "read") {
      addLog("<div class='ev'><div class='ic' style='background:rgba(52,211,153,.15);color:var(--ok)'>R</div><div><b>Read post " + esc(d.post_id) +
        "</b> <span>" + (d.error ? esc(d.error) : d.title ? "“" + esc(d.title) + "”" : "not found") + "</span></div></div>");
    }
  }
  function finish(d) {
    var posts = d.posts_read || [];
    var h = "";
    if (!posts.length) {
      h += "<div class='msg bad'><b>It couldn't read any posts.</b> Either the site isn't WordPress, its public posts API is switched off, " +
        "a firewall blocked the request, or nothing matched the topic. That's why the brief below has no sources, and the check marks the run as weak.</div>";
    }
    var ok = d.grounded && posts.length > 0;
    h += "<div class='verdict " + (ok ? "ok" : "bad") + "'>" + (d.grounded
      ? (posts.length ? "✓ Grounded. Every link in the brief points to one of the " + posts.length + (posts.length === 1 ? " post" : " posts") + " it read." : "No links to check: nothing was read.")
      : "✕ Flagged. It linked to pages it never read: " + (d.uncited_urls || []).map(esc).join(", ")) + "</div>";
    if (posts.length) {
      h += "<p style='font-size:.84rem;margin:12px 0 4px'>Posts it read:</p>" + posts.map(function (p) {
        return "<div style='font-size:.86rem;margin:3px 0'>· <a href='" + esc(p.url) + "' target='_blank' rel='noopener nofollow'>" + esc(p.title) + "</a></div>";
      }).join("");
    }
    h += "<p class='fine'>" + esc(d.model) + " · " + esc(d.research_turns) + " research turns · " +
      (d.stopped_reason === "step_limit" ? "stopped by the 6-turn limit, then wrote from what it had" : "stopped researching on its own") +
      (d.truncated ? " · the brief was cut off at the length limit" : "") + "</p>";
    $("[data-tresult]").innerHTML = h;
  }
  function fail(text) {
    $("[data-tresult]").innerHTML = "<div class='msg bad'>" + esc(text) + "</div>";
  }
  function runLive(ev) {
    ev.preventDefault();
    if (tryState.busy || !tryState.enabled) return;
    var site = normSite($("[data-tsite]").value), topic = String($("[data-ttopic]").value || "").trim();
    if (!/^https:\/\/[^\s/]+\.[^\s]+$/i.test(site)) { fail("Enter a public website address, for example https://yourblog.com."); return; }
    if (topic.length < 2) { fail("Enter a topic of at least two characters."); return; }
    tryState.busy = true;
    $("[data-trun]").disabled = true;
    $("[data-trun]").textContent = "Running…";
    $("[data-tlog]").innerHTML = "";
    $("[data-tresult]").innerHTML = "";
    $("[data-tbrief]").textContent = "";
    $("[data-tbrief]").style.display = "none";
    $("[data-tout]").style.display = "block";
    var gotDone = false;
    fetch(API + "/try/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: topic.slice(0, 120), site_url: site })
    }).then(function (r) {
      if (!r.ok) {
        return r.json().then(function (j) {
          var det = j && j.detail;
          if (Array.isArray(det)) det = "Check the website address and topic.";
          throw new Error(det || "The server said no (" + r.status + ").");
        }, function () { throw new Error("The server said no (" + r.status + ")."); });
      }
      if (!r.body || !r.body.getReader) throw new Error("This browser can't show a live stream. Try a recent Chrome, Edge, Firefox or Safari.");
      var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
      function pump() {
        return reader.read().then(function (chunk) {
          if (chunk.done) return;
          buf += dec.decode(chunk.value, { stream: true });
          var parts = buf.split("\n\n");
          buf = parts.pop();
          parts.forEach(function (block) {
            var m = block.match(/^event: (\w+)\ndata: ([\s\S]*)$/);
            if (!m) return;
            var data = JSON.parse(m[2]);
            if (m[1] === "token") {
              var pre = $("[data-tbrief]");
              pre.style.display = "block";
              pre.textContent += data;
              pre.scrollTop = pre.scrollHeight;
            } else if (m[1] === "done") { gotDone = true; finish(data); }
            else if (m[1] === "error") { gotDone = true; fail(data.error || "The run stopped."); }
            else liveEvent(m[1], data);
          });
          return pump();
        });
      }
      return pump();
    }).then(function () {
      if (!gotDone) fail("The connection closed before the run finished. Please try again.");
    }).catch(function (e) {
      fail(e && e.message ? e.message : "Something went wrong. Please try again.");
    }).then(function () {
      tryState.busy = false;
      $("[data-trun]").textContent = "Run it live";
      loadStatus();
    });
  }

  // ------------------------------------------------------------- render
  var EX = D.example;
  var steps = [["try", "Try it live"], ["s1", "Watch it work"], ["s2", "Catch a fake source"], ["s3", "Real models"], ["s4", "A real website"], ["s5", "Where it runs"]];
  var html = "<style>" + CSS + "</style><div class='wt'><div class='wrap'>";
  html += "<p class='eyebrow'>Case study · AI agents</p>" +
    "<h1>An AI researcher<br><span class='grad'>that can only cite what it read.</span></h1>" +
    "<p class='lede'>Give it a topic and a WordPress website. It searches the site, decides which posts to read, and writes a content brief: " +
    "an outline, existing pages to link to, and facts the site has already published. A final check rejects any link to a page it never opened.</p>" +
    "<div class='tags'><span class='tag'><b>●</b> Fictional demo site + real runs</span><span class='tag'>" + D.test_count + " automated tests</span>" +
    "<span class='tag'>Built AI-assisted under my direction</span><a class='tag' href='" + REPO + "' target='_blank' rel='noopener'>Code on GitHub ↗</a></div>";
  html += "<nav class='nav' aria-label='Steps'>" + steps.map(function (s, i) {
    return "<a href='#" + s[0] + "' data-go='" + s[0] + "'><span>" + (i ? i : "▶") + "</span>" + s[1] + "</a>";
  }).join("") + "</nav>";

  html += "<section class='step' id='try'><div class='num'>▶</div><h2>Try it on any WordPress site</h2>" +
    "<p>Enter a public WordPress website and a topic. The agent searches that site's posts, reads the ones it chooses, and writes a brief while you watch. " +
    "This is a real model, not the scripted stand-in used further down.</p>" +
    "<div class='card try'><form class='form' data-tform novalidate>" +
    "<label>WordPress website<input data-tsite type='url' inputmode='url' autocomplete='url' placeholder='https://yourblog.com' maxlength='300' required></label>" +
    "<label>Topic for a new post<input data-ttopic type='text' placeholder='e.g. how to choose a coffee grinder' maxlength='120' required></label>" +
    "<button class='btn' data-trun type='submit' disabled>Run it live</button></form>" +
    "<div class='status' data-tstatus></div>" +
    "<div data-tout style='display:none'><div class='log' data-tlog></div>" +
    "<pre class='brief' data-tbrief style='display:none;margin-top:10px;max-height:420px'></pre><div data-tresult></div></div>" +
    "<p class='fine'>Runs on Groq <code>openai/gpt-oss-120b</code>. It only reads public posts through the site's standard WordPress API and never writes anything. " +
    "Nothing you enter is stored, but the site address and topic are sent to the model provider, so don't enter anything private. " +
    "A run takes about 20 to 60 seconds. Runs are capped per visitor and per day to keep costs fixed.</p></div></section>";

  html += "<section class='step' id='s1'><div class='num'>1</div><h2>Watch it work</h2>" +
    "<p>Pick one of the " + D.cases.length + " test topics and step through a run on a fictional coffee-roaster site with " + D.posts.length +
    " posts. This run uses the repository's scripted stand-in, so it shows the steps the agent takes, not how clever a real model is.</p>" +
    "<div class='card'><div class='chips' data-topics>" + D.cases.map(function (c, i) {
      return "<button class='ghost" + (i === cIdx ? " on" : "") + "' data-c='" + i + "'>" + esc(c.topic) + "</button>";
    }).join("") + "</div><div data-run>" + runHTML() + "</div>" +
    "<div class='row' style='margin-top:12px'><button class='btn' data-next>Next step</button><button class='ghost' data-all>Show all</button><button class='ghost' data-restart>Restart</button></div></div></section>";

  html += "<section class='step' id='s2'><div class='num'>2</div><h2>Catch a made-up source</h2>" +
    "<p>AI models sometimes cite pages that don't exist, or that they never looked at. The last step lists every link in the brief and compares it with the pages actually read. " +
    "Try adding links to the cold brew brief; each result below comes from the repository's own check.</p><div class='card'><div class='chips'>" +
    D.grounding.map(function (g, i) {
      return "<button class='ghost" + (i === gIdx ? " on" : "") + "' data-g='" + i + "'>" + esc(g.label) + "</button>";
    }).join("") + "</div><div data-ground>" + groundHTML() + "</div>" +
    "<p style='font-size:.84rem;margin:12px 0 0'>The full-width bracket case is a real bug the first live run found: one model wraps citations in 【 】, " +
    "and the check counted the bracket as part of the address, flagging a page that had been read. It was fixed, and a test now covers it.</p></div></section>";

  html += "<section class='step' id='s3'><div class='num'>3</div><h2>On real models</h2>" +
    "<p>The same " + D.cases.length + " topics, run against real AI models. Live runs need paid API keys, so they aren't replayed here; " +
    "these are the results recorded in the repository's README.</p><div class='tbl2'>" +
    liveRows.map(function (r) {
      return "<div class='lrun'><h3>" + esc(r.run.replace(/^Live:\s*/, "")) + "</h3>" +
        metric("Read the right post", r.retrieval, "var(--cyan)") +
        metric("Cited only what it read", r.grounded, "var(--ok)") +
        metric("Finished on its own", r.finished, pctOf(r.finished) < 0.75 ? "var(--warn)" : "var(--ok)") +
        "<div class='mrow'><span>Research turns (avg)</span><div></div><span style='text-align:right'>" + esc(r.turns) + "</span></div></div>";
    }).join("") + "</div>" +
    "<div class='outcome'><strong>What this shows:</strong> both models read the right post every time it existed, and neither cited a page it hadn't read. " +
    "Groq's one failed grounding result in run 1 was a bug in the check, not the model. " +
    "Groq often hit the 6-turn research limit; Claude finished on its own in all 7 runs with fewer turns. With only 7 cases on a fictional site, " +
    "this is a health check, not a benchmark." + (offRow ? " (The offline stand-in scores " + esc(offRow.retrieval) + " across the board by design.)" : "") + "</div></section>";

  html += "<section class='step' id='s4'><div class='num'>4</div><h2>On a real website</h2>" +
    "<p>It was then pointed at a real agency blog with 218 posts. The first two runs read nothing, and that exposed three real problems:</p>" +
    "<div class='card'><div class='bugs'>" +
    "<div class='bug'><i>1</i><span><b>Search results came back newest first</b>, not most relevant. Fixed: it now asks WordPress to rank by relevance.</span></div>" +
    "<div class='bug'><i>2</i><span><b>The site's firewall blocked it</b> because of the default Python user agent. Fixed: it sends an honest, named user agent. It doesn't pretend to be a browser.</span></div>" +
    "<div class='bug'><i>3</i><span><b>Worst: it still reported a pass</b> with nothing read. Fixed: a run that reads no posts now fails with a warning.</span></div></div>" +
    "<h3 style='margin-top:18px'>The rerun, unedited</h3><p style='font-size:.88rem'>" + esc(EX.run_note) + "</p>" +
    "<div class='detail'><p class='q'>" + esc(EX.title) + "</p><p style='font-size:.84rem;margin:0'>Outline:</p><ol class='outl'>" +
    EX.outline.map(function (o) { return "<li>" + esc(o.replace(/^\d+\.\s*/, "")) + "</li>"; }).join("") + "</ol>" +
    "<p style='font-size:.84rem;margin:12px 0 4px'>Read and linked (" + EX.links.length + " posts), plus " + EX.facts_count + " facts reused from them:</p>" +
    EX.links.map(function (l) { return "<div style='font-size:.86rem;margin:3px 0'>· <a href='" + esc(l.url) + "' target='_blank' rel='noopener'>" + esc(l.title) + "</a></div>"; }).join("") +
    "</div><div class='outcome'><strong>Spot check:</strong> one fact was compared with its source post and matched, but the brief dropped the post's “up to” " +
    "from “up to 20–30%”. Grounded links don't guarantee exact wording, so a person still reviews the facts. " +
    "<a href='" + EXAMPLE + "' target='_blank' rel='noopener'>Read the full brief ↗</a></div></div></section>";

  html += "<section class='step' id='s5'><div class='num'>5</div><h2>Where it runs</h2><div class='grid2'>" +
    "<div class='where'><h3>Command line</h3><p>One command with a topic and a site. Exits with an error if the brief isn't grounded or was cut off.</p></div>" +
    "<div class='where'><h3>Web service</h3><p>A small API with a free demo route and token-protected live routes, rate-limited. Checked end to end on 13 Oct 2026.</p></div>" +
    "<div class='where'><h3>Google Sheet to Google Doc</h3><p>List topics in a Sheet, click a menu item, get each brief as its own Doc. Run in a real Google account on 25 Oct 2026.</p></div>" +
    "<div class='where'><h3>Figma</h3><p>Give it a page design and the outline is shaped to the design's sections. Run live on 26 Oct 2026; that run also caught a brief cut off mid-section, now flagged.</p></div>" +
    "</div></section>";

  html += "<div class='foot'><h2>How this was built, and its limits</h2>" +
    "<p>I wrote the specification and the rules: read-only access to the site, cite only what was read, a hard limit on research steps, " +
    "everything testable without an API key, and one workflow for any model provider. Claude, an AI coding assistant, wrote the code. I reviewed it, ran the tests and the evaluations, and directed the fixes.</p><ul>" +
    "<li>The live box at the top calls the real service; it has its own daily budget, separate from my own usage, and only accepts requests from this page.</li>" +
    "<li>Steps 1 and 2 are replayed from the repository's own code, run for this page; nothing is re-calculated in your browser.</li>" +
    "<li>Steps 3 and 4 report recorded live runs from the repository's README and examples folder.</li>" +
    "<li>Seven test topics on a fictional site is a health check, not a benchmark. It reads blog posts only, not other page types.</li></ul>" +
    "<a class='btn cta' href='" + REPO + "' target='_blank' rel='noopener'>See the code, tests and README ↗</a>" +
    "<p style='margin-top:18px;font-size:.85rem'>Henfred Pietersen · <a href='https://outview.co.za/'>Outview</a>, Cape Town</p></div>";
  html += "</div></div>";
  root.innerHTML = html;

  // ------------------------------------------------------------- behaviour
  $("[data-tform]").addEventListener("submit", runLive);
  loadStatus();

  function total() { return events(D.cases[cIdx]).length; }
  function redraw() {
    $("[data-run]").innerHTML = runHTML();
    $("[data-next]").textContent = shown >= total() ? "Done" : "Next step";
  }
  $$("[data-c]").forEach(function (b) {
    b.addEventListener("click", function () {
      cIdx = parseInt(b.getAttribute("data-c"), 10); shown = 0;
      $$("[data-c]").forEach(function (x) { x.classList.toggle("on", x === b); });
      redraw();
    });
  });
  $("[data-next]").addEventListener("click", function () { if (shown < total()) { shown++; redraw(); } });
  $("[data-all]").addEventListener("click", function () { shown = total(); redraw(); });
  $("[data-restart]").addEventListener("click", function () { shown = 0; redraw(); });

  $$("[data-g]").forEach(function (b) {
    b.addEventListener("click", function () {
      gIdx = parseInt(b.getAttribute("data-g"), 10);
      $$("[data-g]").forEach(function (x) { x.classList.toggle("on", x === b); });
      $("[data-ground]").innerHTML = groundHTML();
    });
  });

  $$("[data-go]").forEach(function (a) {
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      var t = root.getElementById(a.getAttribute("data-go"));
      if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) $$("[data-go]").forEach(function (a) { a.classList.toggle("on", a.getAttribute("data-go") === en.target.id); });
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    $$("section.step").forEach(function (s) { io.observe(s); });
  }
