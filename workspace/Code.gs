/**
 * wp-brief-agent for Google Workspace (Apps Script, bound to a Google Sheet).
 *
 * The Sheet is a queue: one row per topic. "Brief agent > Generate briefs for new rows" sends
 * each new row to the deployed wp-brief-agent API (POST /brief), writes the returned brief into a
 * new Google Doc, and writes the Doc link, the grounding result and the posts read back to the row.
 *
 * The API token is never stored in this file. Each user sets it once through the menu, and it is
 * kept in that user's Apps Script user properties.
 *
 * Built AI-assisted under the direction of Henfred Pietersen.
 */

var DEFAULT_BASE_URL = 'https://wp-brief-agent.onrender.com';
var SHEET_NAME = 'Briefs';
var HEADERS = ['Topic', 'Site URL (optional)', 'Status', 'Doc', 'Grounded', 'Posts read', 'Model', 'Updated'];
var COL = { TOPIC: 0, SITE: 1, STATUS: 2, DOC: 3, GROUNDED: 4, POSTS: 5, MODEL: 6, UPDATED: 7 };
var MAX_PER_RUN = 3; // Apps Script stops a run after 6 minutes; one live brief can take a minute.
var TOKEN_KEY = 'WP_BRIEF_API_TOKEN';

// ---------------------------------------------------------------------------------------------
// Pure helpers (no Google services). These are what the Node tests in workspace/test cover.
// ---------------------------------------------------------------------------------------------

/** Row indexes (0-based, excluding the header) that have a topic and no Doc yet. */
function rowsToProcess(rows) {
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var topic = String(rows[i][COL.TOPIC] || '').trim();
    var doc = String(rows[i][COL.DOC] || '').trim();
    if (topic && !doc) out.push(i);
  }
  return out;
}

/** The JSON body for POST /brief. A blank site means the API's fictional demo site. */
function buildPayload(topic, siteUrl) {
  var payload = { topic: String(topic).trim() };
  var site = String(siteUrl || '').trim();
  if (site) payload.site_url = site;
  return payload;
}

/** Plain-English status for an HTTP result; `stop` means later rows would fail the same way. */
function describeStatus(code, body) {
  var detail = '';
  try {
    detail = JSON.parse(body).detail || '';
  } catch (e) {
    detail = '';
  }
  if (code === 200) return { ok: true, stop: false, text: 'Done' };
  if (code === 401) return { ok: false, stop: true, text: 'Error: token rejected. Use Brief agent > Set API token.' };
  if (code === 429) return { ok: false, stop: true, text: 'Error: hourly limit reached. It will retry on the next run.' };
  if (code === 503) return { ok: false, stop: true, text: 'Error: server not configured. ' + detail };
  if (code === 422) return { ok: false, stop: false, text: 'Error: request refused. ' + detail };
  if (code === 502) return { ok: false, stop: false, text: 'Error: model or site failed. ' + detail };
  return { ok: false, stop: false, text: 'Error: HTTP ' + code + '. ' + detail };
}

/** Strip inline markdown: **bold**, *italic*, `code`, [text](url) -> text (url). */
function cleanInline(text) {
  return String(text)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '$1 ($2)')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1$2')
    .trim();
}

/**
 * Turn the brief's markdown into simple blocks a Google Doc can show:
 * {type: 'h1'|'h2'|'h3'|'bullet'|'numbered'|'para', text, level}.
 */
function markdownToBlocks(md) {
  var blocks = [];
  var lines = String(md || '').replace(/\r\n/g, '\n').split('\n');
  for (var i = 0; i < lines.length; i++) {
    var raw = lines[i];
    if (!raw.trim() || /^\s*(-{3,}|\*{3,})\s*$/.test(raw)) continue;
    var indent = raw.match(/^\s*/)[0].length;
    var level = Math.min(Math.floor(indent / 2), 3);
    var line = raw.trim();
    var m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      var depth = Math.min(m[1].length, 3);
      blocks.push({ type: 'h' + depth, text: cleanInline(m[2]), level: 0 });
    } else if ((m = line.match(/^[-*+]\s+(.*)$/))) {
      blocks.push({ type: 'bullet', text: cleanInline(m[1]), level: level });
    } else if ((m = line.match(/^\d+[.)]\s+(.*)$/))) {
      blocks.push({ type: 'numbered', text: cleanInline(m[1]), level: level });
    } else {
      blocks.push({ type: 'para', text: cleanInline(line), level: 0 });
    }
  }
  return blocks;
}

/** Doc title, e.g. "Brief: cold brew (2026-10-13)". */
function docTitle(topic, date) {
  var d = date || new Date();
  var iso = d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  return 'Brief: ' + String(topic).trim() + ' (' + iso + ')';
}

// ---------------------------------------------------------------------------------------------
// Google Workspace side.
// ---------------------------------------------------------------------------------------------

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Brief agent')
    .addItem('Generate briefs for new rows', 'generateBriefs')
    .addSeparator()
    .addItem('Set up this sheet', 'setUpSheet')
    .addItem('Set API token', 'setApiToken')
    .addItem('Run every hour', 'turnOnHourlyRun')
    .addItem('Stop hourly run', 'turnOffHourlyRun')
    .addToUi();
}

function setUpSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
  sheet.setFrozenRows(1);
  if (sheet.getLastRow() < 2) {
    sheet.getRange(2, 1, 1, 2).setValues([['cold brew', '']]);
  }
  return sheet;
}

function setApiToken() {
  var ui = SpreadsheetApp.getUi();
  var res = ui.prompt(
    'Set API token',
    'Paste the API_TOKEN from the server settings (the token only, without "Bearer").',
    ui.ButtonSet.OK_CANCEL
  );
  if (res.getSelectedButton() !== ui.Button.OK) return;
  var token = res.getResponseText().trim().replace(/^bearer\s+/i, '');
  if (!token) return;
  PropertiesService.getUserProperties().setProperty(TOKEN_KEY, token);
  ui.alert('Token saved for your account. It is not stored in the sheet or the script code.');
}

function baseUrl() {
  var custom = PropertiesService.getScriptProperties().getProperty('WP_BRIEF_BASE_URL');
  return (custom || DEFAULT_BASE_URL).replace(/\/+$/, '');
}

/** The free host sleeps when idle; poll /health until it answers before the slow live call. */
function wakeService(url) {
  for (var attempt = 0; attempt < 6; attempt++) {
    try {
      var r = UrlFetchApp.fetch(url + '/health', { muteHttpExceptions: true });
      if (r.getResponseCode() === 200) return true;
    } catch (e) {
      // still waking up
    }
    Utilities.sleep(10000);
  }
  return false;
}

function writeDoc(topic, site, result) {
  var doc = DocumentApp.create(docTitle(topic));
  var body = doc.getBody();
  body.appendParagraph(docTitle(topic)).setHeading(DocumentApp.ParagraphHeading.TITLE);
  body.appendParagraph(
    'Site: ' + result.site + '  |  Model: ' + result.model + '  |  Grounded: ' +
      (result.grounded ? 'yes' : 'NO') + '  |  Research turns: ' + result.research_turns +
      ' (' + result.stopped_reason + ')'
  ).setItalic(true);

  var blocks = markdownToBlocks(result.brief);
  var headingFor = {
    h1: DocumentApp.ParagraphHeading.HEADING1,
    h2: DocumentApp.ParagraphHeading.HEADING2,
    h3: DocumentApp.ParagraphHeading.HEADING3,
  };
  for (var i = 0; i < blocks.length; i++) {
    var b = blocks[i];
    if (headingFor[b.type]) {
      body.appendParagraph(b.text).setHeading(headingFor[b.type]);
    } else if (b.type === 'bullet' || b.type === 'numbered') {
      var item = body.appendListItem(b.text).setNestingLevel(b.level);
      item.setGlyphType(b.type === 'bullet' ? DocumentApp.GlyphType.BULLET : DocumentApp.GlyphType.NUMBER);
    } else {
      body.appendParagraph(b.text);
    }
  }

  body.appendParagraph('Posts the agent read').setHeading(DocumentApp.ParagraphHeading.HEADING2);
  for (var j = 0; j < result.posts_read.length; j++) {
    var p = result.posts_read[j];
    body.appendListItem(p.title).setLinkUrl(p.url);
  }
  if (!result.grounded) {
    body.appendParagraph('Warning: the brief cites pages the agent never read: ' + result.uncited_urls.join(', '));
  }
  body.appendParagraph('Generated by wp-brief-agent (github.com/henfredpietersen/wp-brief-agent).').setItalic(true);
  doc.saveAndClose();
  return doc.getUrl();
}

function generateBriefs() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return 'Another run is in progress.';
  try {
    var token = PropertiesService.getUserProperties().getProperty(TOKEN_KEY);
    if (!token) return notify('No API token yet. Use Brief agent > Set API token first.');

    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
    if (!sheet) return notify('No "' + SHEET_NAME + '" sheet. Use Brief agent > Set up this sheet.');
    var last = sheet.getLastRow();
    if (last < 2) return notify('No topics yet. Add one in column A.');

    var rows = sheet.getRange(2, 1, last - 1, HEADERS.length).getValues();
    var todo = rowsToProcess(rows).slice(0, MAX_PER_RUN);
    if (!todo.length) return notify('Nothing new: every topic already has a Doc.');

    var url = baseUrl();
    if (!wakeService(url)) return notify('The brief service did not wake up. Try again in a minute.');

    var done = 0;
    for (var k = 0; k < todo.length; k++) {
      var i = todo[k];
      var rowNum = i + 2;
      var topic = rows[i][COL.TOPIC];
      var site = rows[i][COL.SITE];
      sheet.getRange(rowNum, COL.STATUS + 1).setValue('Working...');
      SpreadsheetApp.flush();

      var res = UrlFetchApp.fetch(url + '/brief', {
        method: 'post',
        contentType: 'application/json',
        headers: { Authorization: 'Bearer ' + token },
        payload: JSON.stringify(buildPayload(topic, site)),
        muteHttpExceptions: true,
      });
      var status = describeStatus(res.getResponseCode(), res.getContentText());
      var now = new Date();
      if (!status.ok) {
        sheet.getRange(rowNum, COL.STATUS + 1).setValue(status.text);
        sheet.getRange(rowNum, COL.UPDATED + 1).setValue(now);
        if (status.stop) break;
        continue;
      }
      var result = JSON.parse(res.getContentText());
      var docUrl = writeDoc(topic, result.site, result);
      sheet.getRange(rowNum, COL.STATUS + 1, 1, 6).setValues([[
        'Done',
        docUrl,
        result.grounded ? 'yes' : 'NO',
        result.posts_read.length,
        result.model,
        now,
      ]]);
      done++;
    }
    var left = rowsToProcess(sheet.getRange(2, 1, last - 1, HEADERS.length).getValues()).length;
    return notify(done + ' brief(s) written.' + (left ? ' ' + left + ' row(s) still waiting; run again.' : ''));
  } finally {
    lock.releaseLock();
  }
}

/** Toast when a person is looking at the sheet; plain log line when run by the hourly trigger. */
function notify(message) {
  try {
    SpreadsheetApp.getActiveSpreadsheet().toast(message, 'Brief agent', 8);
  } catch (e) {
    console.log(message);
  }
  return message;
}

function turnOnHourlyRun() {
  turnOffHourlyRun();
  ScriptApp.newTrigger('generateBriefs').timeBased().everyHours(1).create();
  notify('Hourly run is on. New rows get a brief within the hour.');
}

function turnOffHourlyRun() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'generateBriefs') ScriptApp.deleteTrigger(triggers[i]);
  }
}

// Lets the Node tests load this file. Apps Script has no `module`, so this line does nothing there.
if (typeof module !== 'undefined') {
  module.exports = {
    rowsToProcess: rowsToProcess,
    buildPayload: buildPayload,
    describeStatus: describeStatus,
    cleanInline: cleanInline,
    markdownToBlocks: markdownToBlocks,
    docTitle: docTitle,
    generateBriefs: generateBriefs,
    COL: COL,
    HEADERS: HEADERS,
    MAX_PER_RUN: MAX_PER_RUN,
  };
}
