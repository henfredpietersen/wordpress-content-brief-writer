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
    "@media (max-width:520px){.mrow{grid-template-columns:110px 1fr 62px}}"
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

  // ------------------------------------------------------------- render
  var EX = D.example;
  var steps = [["s1", "Watch it work"], ["s2", "Catch a fake source"], ["s3", "Real models"], ["s4", "A real website"], ["s5", "Where it runs"]];
  var html = "<style>" + CSS + "</style><div class='wt'><div class='wrap'>";
  html += "<p class='eyebrow'>Case study · AI agents</p>" +
    "<h1>An AI researcher<br><span class='grad'>that can only cite what it read.</span></h1>" +
    "<p class='lede'>Give it a topic and a WordPress website. It searches the site, decides which posts to read, and writes a content brief: " +
    "an outline, existing pages to link to, and facts the site has already published. A final check rejects any link to a page it never opened.</p>" +
    "<div class='tags'><span class='tag'><b>●</b> Fictional demo site + real runs</span><span class='tag'>" + D.test_count + " automated tests</span>" +
    "<span class='tag'>Built AI-assisted under my direction</span><a class='tag' href='" + REPO + "' target='_blank' rel='noopener'>Code on GitHub ↗</a></div>";
  html += "<nav class='nav' aria-label='Steps'>" + steps.map(function (s, i) {
    return "<a href='#" + s[0] + "' data-go='" + s[0] + "'><span>" + (i + 1) + "</span>" + s[1] + "</a>";
  }).join("") + "</nav>";

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
    "<li>Steps 1 and 2 are replayed from the repository's own code, run for this page; nothing is re-calculated in your browser.</li>" +
    "<li>Steps 3 and 4 report recorded live runs from the repository's README and examples folder.</li>" +
    "<li>Seven test topics on a fictional site is a health check, not a benchmark. It reads blog posts only, not other page types.</li></ul>" +
    "<a class='btn cta' href='" + REPO + "' target='_blank' rel='noopener'>See the code, tests and README ↗</a>" +
    "<p style='margin-top:18px;font-size:.85rem'>Henfred Pietersen · <a href='https://outview.co.za/'>Outview</a>, Cape Town</p></div>";
  html += "</div></div>";
  root.innerHTML = html;

  // ------------------------------------------------------------- behaviour
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
