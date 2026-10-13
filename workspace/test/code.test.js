// Tests for workspace/Code.gs. Run with: node --test workspace/test
// The pure helpers are tested directly. generateBriefs is run end to end against fake Google
// services (Sheet, Docs, UrlFetch, properties), so no Google account or network is needed.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const gs = require(path.join(__dirname, '..', 'Code.gs'));
const { COL, HEADERS } = gs;

// ---------------------------------------------------------------- pure helpers

test('rowsToProcess picks rows with a topic and no Doc', () => {
  const rows = [
    ['cold brew', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''], // blank row
    ['espresso', '', 'Done', 'https://docs.google.com/x', 'yes', 2, 'm', ''], // already done
    ['  grinders  ', '', 'Error: HTTP 500', '', '', '', '', ''], // failed earlier: retry
  ];
  assert.deepEqual(gs.rowsToProcess(rows), [0, 3]);
});

test('buildPayload leaves out a blank site so the API uses its demo site', () => {
  assert.deepEqual(gs.buildPayload(' cold brew ', ''), { topic: 'cold brew' });
  assert.deepEqual(gs.buildPayload('cold brew', ' https://example.com '), {
    topic: 'cold brew',
    site_url: 'https://example.com',
  });
});

test('describeStatus explains each failure and stops on ones that would repeat', () => {
  assert.equal(gs.describeStatus(200, '{}').ok, true);
  const unauth = gs.describeStatus(401, '{"detail":"x"}');
  assert.equal(unauth.stop, true);
  assert.match(unauth.text, /Set API token/);
  assert.equal(gs.describeStatus(429, '').stop, true);
  const cfg = gs.describeStatus(503, '{"detail":"GROQ_API_KEY is not configured on the server."}');
  assert.equal(cfg.stop, true);
  assert.match(cfg.text, /GROQ_API_KEY/);
  assert.equal(gs.describeStatus(502, 'not json').stop, false); // one bad site shouldn't stop the rest
});

test('cleanInline strips markdown and keeps link targets', () => {
  assert.equal(
    gs.cleanInline('**Bold** and *it* with `code` and [Cold Brew](https://demo-roastery.test/cold-brew-recipe/)'),
    'Bold and it with code and Cold Brew (https://demo-roastery.test/cold-brew-recipe/)'
  );
});

test('markdownToBlocks maps headings, bullets, numbers and nesting', () => {
  const md = [
    '# Working title',
    '',
    '## Outline',
    '- **Intro**',
    '  - nested point',
    '1. First step',
    '---',
    'Plain paragraph.',
  ].join('\n');
  assert.deepEqual(gs.markdownToBlocks(md), [
    { type: 'h1', text: 'Working title', level: 0 },
    { type: 'h2', text: 'Outline', level: 0 },
    { type: 'bullet', text: 'Intro', level: 0 },
    { type: 'bullet', text: 'nested point', level: 1 },
    { type: 'numbered', text: 'First step', level: 0 },
    { type: 'para', text: 'Plain paragraph.', level: 0 },
  ]);
});

test('docTitle includes the topic and the date', () => {
  assert.equal(gs.docTitle(' cold brew ', new Date(2026, 9, 13)), 'Brief: cold brew (2026-10-13)');
});

// ---------------------------------------------------------------- fakes for Google services

function fakeWorld({ rows, responses, token = 'tok' }) {
  const grid = [HEADERS.slice(), ...rows.map((r) => r.slice())];
  const calls = { fetch: [], docs: [] };
  const userProps = new Map(token ? [['WP_BRIEF_API_TOKEN', token]] : []);

  const range = (r, c, nr = 1, nc = 1) => ({
    getValues: () => grid.slice(r - 1, r - 1 + nr).map((row) => row.slice(c - 1, c - 1 + nc)),
    setValues: (vals) => {
      vals.forEach((v, i) => v.forEach((x, j) => { grid[r - 1 + i][c - 1 + j] = x; }));
      return range(r, c, nr, nc);
    },
    setValue: (v) => { grid[r - 1][c - 1] = v; return range(r, c); },
  });
  const sheet = { getLastRow: () => grid.length, getRange: range };

  const para = () => ({ setHeading: () => para(), setItalic: () => para() });
  const listItem = () => ({ setNestingLevel: () => listItem(), setGlyphType: () => listItem(), setLinkUrl: () => listItem() });

  globalThis.LockService = { getScriptLock: () => ({ tryLock: () => true, releaseLock: () => {} }) };
  globalThis.PropertiesService = {
    getUserProperties: () => ({ getProperty: (k) => userProps.get(k) || null }),
    getScriptProperties: () => ({ getProperty: () => null }),
  };
  globalThis.SpreadsheetApp = {
    getActiveSpreadsheet: () => ({ getSheetByName: () => sheet, toast: () => {} }),
    flush: () => {},
  };
  globalThis.Utilities = { sleep: () => {} };
  globalThis.UrlFetchApp = {
    fetch: (url, opts = {}) => {
      calls.fetch.push({ url, opts });
      if (url.endsWith('/health')) return { getResponseCode: () => 200, getContentText: () => '{}' };
      const [code, body] = responses.shift();
      return { getResponseCode: () => code, getContentText: () => JSON.stringify(body) };
    },
  };
  globalThis.DocumentApp = {
    ParagraphHeading: { TITLE: 't', HEADING1: 1, HEADING2: 2, HEADING3: 3 },
    GlyphType: { BULLET: 'b', NUMBER: 'n' },
    create: (title) => {
      const n = calls.docs.length;
      calls.docs.push({ title, paragraphs: [], items: [] });
      return {
        getBody: () => ({
          appendParagraph: (t) => { calls.docs[n].paragraphs.push(t); return para(); },
          appendListItem: (t) => { calls.docs[n].items.push(t); return listItem(); },
        }),
        saveAndClose: () => {},
        getUrl: () => `https://docs.google.com/document/d/doc${n}`,
      };
    },
  };
  return { grid, calls };
}

const okBrief = (grounded = true) => ({
  model: 'groq: openai/gpt-oss-120b',
  site: 'https://demo-roastery.test',
  brief: '# Cold Brew 101\n## Outline\n- Ratio',
  posts_read: [{ title: 'Cold Brew Recipe for Summer', url: 'https://demo-roastery.test/cold-brew-recipe/' }],
  grounded,
  uncited_urls: grounded ? [] : ['https://made-up.test/'],
  research_turns: 4,
  stopped_reason: 'model_finished',
});

// ---------------------------------------------------------------- generateBriefs end to end

test('generateBriefs writes a Doc per new row and fills in the row', () => {
  const { grid, calls } = fakeWorld({
    rows: [
      ['cold brew', '', '', '', '', '', '', ''],
      ['espresso', '', 'Done', 'https://docs.google.com/old', 'yes', 1, 'm', ''],
    ],
    responses: [[200, okBrief()]],
  });
  const msg = gs.generateBriefs();
  assert.match(msg, /1 brief\(s\) written/);

  const live = calls.fetch.filter((c) => c.url.endsWith('/brief'));
  assert.equal(live.length, 1, 'the row that already has a Doc is skipped');
  assert.equal(live[0].opts.headers.Authorization, 'Bearer tok');
  assert.deepEqual(JSON.parse(live[0].opts.payload), { topic: 'cold brew' });

  const row = grid[1];
  assert.equal(row[COL.STATUS], 'Done');
  assert.equal(row[COL.DOC], 'https://docs.google.com/document/d/doc0');
  assert.equal(row[COL.GROUNDED], 'yes');
  assert.equal(row[COL.POSTS], 1);
  assert.equal(row[COL.MODEL], 'groq: openai/gpt-oss-120b');

  const doc = calls.docs[0];
  assert.ok(doc.paragraphs.includes('Cold Brew 101'));
  assert.ok(doc.items.includes('Cold Brew Recipe for Summer'));
});

test('an ungrounded brief is flagged in the row and warned about in the Doc', () => {
  const { grid, calls } = fakeWorld({
    rows: [['cold brew', '', '', '', '', '', '', '']],
    responses: [[200, okBrief(false)]],
  });
  gs.generateBriefs();
  assert.equal(grid[1][COL.GROUNDED], 'NO');
  assert.ok(calls.docs[0].paragraphs.some((p) => p.includes('https://made-up.test/')));
});

test('a rejected token stops the run instead of failing every row', () => {
  const { grid, calls } = fakeWorld({
    rows: [
      ['a', '', '', '', '', '', '', ''],
      ['b', '', '', '', '', '', '', ''],
    ],
    responses: [[401, { detail: 'A token was sent but it is wrong.' }]],
  });
  gs.generateBriefs();
  assert.equal(calls.fetch.filter((c) => c.url.endsWith('/brief')).length, 1);
  assert.match(grid[1][COL.STATUS], /token rejected/);
  assert.equal(grid[2][COL.STATUS], '', 'second row untouched');
  assert.equal(calls.docs.length, 0);
});

test('one failing site does not stop the next row', () => {
  const { grid } = fakeWorld({
    rows: [
      ['a', 'https://broken.example', '', '', '', '', '', ''],
      ['b', '', '', '', '', '', '', ''],
    ],
    responses: [[502, { detail: 'ConnectError' }], [200, okBrief()]],
  });
  gs.generateBriefs();
  assert.match(grid[1][COL.STATUS], /model or site failed/);
  assert.equal(grid[1][COL.DOC], '', 'failed row stays open for a retry');
  assert.equal(grid[2][COL.STATUS], 'Done');
});

test('at most MAX_PER_RUN rows per run, to stay under the 6-minute limit', () => {
  const rows = Array.from({ length: 5 }, (_, i) => [`t${i}`, '', '', '', '', '', '', '']);
  const { calls } = fakeWorld({ rows, responses: rows.map(() => [200, okBrief()]) });
  const msg = gs.generateBriefs();
  assert.equal(calls.docs.length, gs.MAX_PER_RUN);
  assert.match(msg, /2 row\(s\) still waiting/);
});

test('no token: nothing is called', () => {
  const { calls } = fakeWorld({ rows: [['a', '', '', '', '', '', '', '']], responses: [], token: null });
  assert.match(gs.generateBriefs(), /Set API token/);
  assert.equal(calls.fetch.length, 0);
});
