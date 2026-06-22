/**
 * NGS Daily Digest — Google Sheet control menu.
 *
 * Adds an "NGS Digest" menu so non-technical collaborators can do, from inside
 * the sheet, the things that used to be terminal commands:
 *   • send a test to the test channel
 *   • send an update (resend tomorrow with new info)
 *   • send a chosen day
 *   • pause / resume the automated evening digest
 *   • run the formatting clean-up (lint + safe fixes)
 *
 * It does NOT reimplement the digest. "Send"/"Check formatting" trigger the
 * existing GitHub Actions workflow (which runs the Python). Pause/Resume just
 * flip a flag (named range DIGEST_PAUSED) that the scheduled run reads.
 *
 * ── One-time setup (an admin with GitHub access, e.g. Oona) ──────────────────
 * Extensions ▸ Apps Script ▸ paste this file, then run "NGS Digest ▸ Setup…"
 * once and provide:
 *   GITHUB_REPO   e.g. "EosLightmedia/ngs-daily-digest"
 *   GITHUB_TOKEN  a fine-grained PAT for that repo with:
 *                   Actions = Read and write, Contents = Read, Metadata = Read
 * The token is stored in Script Properties (per-script, not visible to viewers)
 * and is never shown in the sheet. Collaborators only click menu items.
 */

var WORKFLOW_FILE = 'daily-digest.yml';   // the workflow we dispatch
var PAUSE_RANGE = 'DIGEST_PAUSED';        // must match config.PAUSE_NAMED_RANGE
var CONTROLS_SHEET = 'Controls';

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('NGS Digest')
    .addItem('Send test to test channel', 'menuSendTest')
    .addItem('Send update (resend tomorrow)', 'menuSendUpdate')
    .addItem('Send a chosen day…', 'menuSendChosenDay')
    .addSeparator()
    .addItem('Pause automated digest', 'menuPause')
    .addItem('Resume automated digest', 'menuResume')
    .addItem('Show digest status', 'menuStatus')
    .addSeparator()
    .addItem('Sort by time (within each day)', 'menuSortByTime')
    .addItem('Hide past days', 'menuHidePast')
    .addItem('Show all days', 'menuShowAll')
    .addItem('Check formatting', 'menuCheckFormatting')
    .addSeparator()
    .addItem('Setup… (admin)', 'menuSetup')
    .addToUi();
}

/* ── Menu handlers ──────────────────────────────────────────────────────── */

function menuSendTest() {
  dispatch_('test', '');
  toast_('Test send triggered — it will post to the test channel in ~1 min.');
}

function menuSendUpdate() {
  dispatch_('update', '');
  toast_("Update triggered — tomorrow's schedule will repost (marked UPDATED) in ~1 min.");
}

function menuSendChosenDay() {
  var html = HtmlService.createHtmlOutputFromFile('DatePicker')
    .setWidth(320).setHeight(180);
  SpreadsheetApp.getUi().showModalDialog(html, 'Send a chosen day');
}

/** Called from the DatePicker dialog. date is "YYYY-MM-DD"; toTest routes the
 *  post to the test channel (the 'test' action) instead of the live channel. */
function dispatchChosenDay(date, toTest) {
  dispatch_(toTest ? 'test' : 'send', date || '');
  var where = toTest ? 'the test channel' : 'the live channel';
  toast_('Send triggered for ' + (date || 'tomorrow') + ' to ' + where + ' — posts in ~1 min.');
}

function menuCheckFormatting() {
  dispatch_('check_formatting', '');
  toast_('Formatting check triggered — results land in the "Formatting Report" tab in ~1 min.');
}

/* ── Smart sort: order rows by Start time WITHIN each day block ──────────────
 * Google's built-in sort treats the day-banner rows as data and scrambles the
 * schedule. This sorts only the rows between banners, leaving the banners as
 * fixed dividers, and runs entirely in the sheet (no GitHub token needed).
 *
 * It sorts each block NATIVELY (Range.sort), so rows physically move with all
 * their values, number formats and dropdowns intact. We never read time cells
 * into JS and write them back — that round-trip turns times into Date objects
 * and corrupts time-only cells (an End of 10:00 AM collapsing to "12/30/1899").
 * We only write a numeric sort key into a scratch column, sort by it, then drop
 * that column. Time logic mirrors schedule_reader.parse_time. */

var WEEKDAYS_ = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
var SCHEDULE_SHEET_ = 'Schedule';
var OVERNIGHT_CUTOFF_MIN_ = 3 * 60;   // times before 3 AM are after-midnight -> sort to end of day
var TIME_RE_ = /(\d{1,2}):(\d{2})\s*([ap])\.?m\.?/i;

function menuSortByTime() {
  var ui = SpreadsheetApp.getUi();
  var ss = SpreadsheetApp.getActive();
  var sh = ss.getSheetByName(SCHEDULE_SHEET_) || ss.getActiveSheet();

  var lastRow = sh.getLastRow();
  var lastCol = sh.getLastColumn();
  if (lastRow < 2) { toast_('Nothing to sort.'); return; }

  var shown = sh.getRange(1, 1, lastRow, lastCol).getDisplayValues();  // for parsing only
  var headerRow = detectHeaderRow_(shown);                             // 0-based
  var header = shown[headerRow].map(function (c) { return String(c).trim().toLowerCase(); });
  var startCol = header.indexOf('start');                              // 0-based
  if (startCol < 0) { ui.alert('Could not find a "Start" column — nothing sorted.'); return; }

  var resp = ui.alert('Sort by time?',
    'This reorders the rows under each day banner by Start time (earliest first; ' +
    'blank/TBD last). Day banners stay put, and same-time rows keep their order. ' +
    'Colours, dropdowns and times are preserved.\n\nProceed?',
    ui.ButtonSet.YES_NO);
  if (resp !== ui.Button.YES) return;

  // Scratch column just past the data; ensure the grid has room for it.
  var keyCol = lastCol + 1;
  var insertedHelper = false;
  if (sh.getMaxColumns() < keyCol) {
    sh.insertColumnsAfter(sh.getMaxColumns(), keyCol - sh.getMaxColumns());
    insertedHelper = true;
  }

  var moved = 0;
  var runStart = null;  // 1-based sheet row where the current run begins

  function flush(runEndExclusive) {  // 1-based, exclusive
    if (runStart !== null && runEndExclusive - runStart >= 2) {
      var n = runEndExclusive - runStart;
      var keys = [];
      for (var i = 0; i < n; i++) {
        var mins = startMinutes_(shown[runStart - 1 + i][startCol]);  // Infinity for blank/TBD
        var base = (mins === Infinity ? 1e9 : mins);
        keys.push([base * 100000 + i]);  // +i keeps same-time rows in their original order
      }
      sh.getRange(runStart, keyCol, n, 1).setValues(keys);
      // Native sort: physically reorders the block's rows (all columns through
      // the key col) preserving every value/format. No value round-trip.
      sh.getRange(runStart, 1, n, keyCol).sort({ column: keyCol, ascending: true });
      moved += n;
    }
    runStart = null;
  }

  for (var r = headerRow + 2; r <= lastRow; r++) {  // first data row = headerRow+2 (1-based)
    var first = String(shown[r - 1][0] || '').trim();
    if (isBanner_(first)) { flush(r); continue; }
    if (runStart === null) runStart = r;
  }
  flush(lastRow + 1);

  // Remove the scratch column.
  if (insertedHelper) sh.deleteColumn(keyCol);
  else sh.getRange(1, keyCol, lastRow, 1).clearContent();

  toast_(moved ? 'Sorted rows by Start time within each day.'
               : 'Nothing needed reordering.');
}

/** Minutes since midnight for sorting; blank/TBD/unparseable -> Infinity (sorts
 *  last); times before 3 AM (and "(next day)") are pushed past 24h. */
function startMinutes_(raw) {
  var s = String(raw || '').trim();
  if (!s) return Infinity;
  var m = TIME_RE_.exec(s);
  if (!m) return Infinity;            // "TBD" and the like
  var hour = parseInt(m[1], 10), min = parseInt(m[2], 10);
  var pm = m[3].toLowerCase() === 'p';
  if (pm && hour !== 12) hour += 12;
  if (!pm && hour === 12) hour = 0;
  var mins = hour * 60 + min;
  if (/next day/i.test(s) || mins < OVERNIGHT_CUTOFF_MIN_) mins += 24 * 60;
  return mins;
}

function isBanner_(firstCell) {
  if (!firstCell) return false;
  var token = String(firstCell).trim().split(/[,\s]+/)[0].toLowerCase();
  return WEEKDAYS_.indexOf(token) !== -1;
}

/** Header row = the one carrying Date + Start + Type (mirrors schedule_reader). */
function detectHeaderRow_(rows) {
  for (var i = 0; i < rows.length; i++) {
    var set = {};
    rows[i].forEach(function (c) { set[String(c).trim().toLowerCase()] = true; });
    if (set['date'] && set['start'] && set['type']) return i;
  }
  return 2;  // fallback: row 3 (0-indexed 2)
}

/* ── Hide past days: collapse every day block (banner + its rows) dated before
 * today, keeping today and the future visible. The title/KEY/header rows are
 * never touched. Idempotent: it first reveals all day rows, then re-hides the
 * past, so running it each morning rolls the view forward. "today" is taken in
 * the event timezone to match the digest's day boundaries. */

var EVENT_TZ_ = 'America/New_York';
var MONTHS_ = {
  january: 0, february: 1, march: 2, april: 3, may: 4, june: 5,
  july: 6, august: 7, september: 8, october: 9, november: 10, december: 11
};

/** Date a banner refers to, using `year` (banners carry no year). null if none. */
function bannerDate_(text, year) {
  var m = /([A-Za-z]+)\s+(\d{1,2})/.exec(String(text || ''));
  while (m) {
    var mon = MONTHS_[m[1].toLowerCase()];
    if (mon !== undefined) return new Date(year, mon, parseInt(m[2], 10));
    m = /([A-Za-z]+)\s+(\d{1,2})/.exec(String(text).slice(m.index + m[1].length));
  }
  return null;
}

function dataBounds_() {
  var ss = SpreadsheetApp.getActive();
  var sh = ss.getSheetByName(SCHEDULE_SHEET_) || ss.getActiveSheet();
  var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
  var shown = lastRow ? sh.getRange(1, 1, lastRow, lastCol).getDisplayValues() : [];
  var headerRow = detectHeaderRow_(shown);   // 0-based
  return { sh: sh, lastRow: lastRow, shown: shown, firstData: headerRow + 2 };  // firstData 1-based
}

function menuHidePast() {
  var b = dataBounds_();
  if (b.lastRow < b.firstData) { toast_('Nothing to filter.'); return; }

  var t = Utilities.formatDate(new Date(), EVENT_TZ_, 'yyyy-MM-dd').split('-');
  var year = parseInt(t[0], 10);
  var today = new Date(year, parseInt(t[1], 10) - 1, parseInt(t[2], 10));

  // Collect the banner rows (1-based) and the date each one heads.
  var banners = [];
  for (var r = b.firstData; r <= b.lastRow; r++) {
    var first = String(b.shown[r - 1][0] || '').trim();
    if (isBanner_(first)) banners.push({ row: r, date: bannerDate_(first, year) });
  }
  if (!banners.length) { toast_('No day banners found — nothing to filter.'); return; }

  // Reset (reveal everything) so the result reflects only today's comparison.
  b.sh.showRows(b.firstData, b.lastRow - b.firstData + 1);

  var hidden = 0;
  for (var i = 0; i < banners.length; i++) {
    var start = banners[i].row;
    var end = (i + 1 < banners.length) ? banners[i + 1].row - 1 : b.lastRow;
    if (banners[i].date && banners[i].date.getTime() < today.getTime()) {
      b.sh.hideRows(start, end - start + 1);
      hidden++;
    }
  }
  toast_(hidden ? ('Hid ' + hidden + ' past day(s) — today and future remain.')
                : 'No past days to hide.');
}

function menuShowAll() {
  var b = dataBounds_();
  if (b.lastRow >= b.firstData) b.sh.showRows(b.firstData, b.lastRow - b.firstData + 1);
  toast_('All days shown.');
}

function menuPause() {
  setPause_(true);
  toast_('Automated digest PAUSED. The evening send will skip until you resume.');
}

function menuResume() {
  setPause_(false);
  toast_('Automated digest RESUMED. The evening send is back on.');
}

function menuStatus() {
  var paused = isPaused_();
  SpreadsheetApp.getUi().alert(
    'Automated digest is currently ' + (paused ? 'PAUSED ⏸' : 'ON ▶') + '.');
}

function menuSetup() {
  var ui = SpreadsheetApp.getUi();
  var props = PropertiesService.getScriptProperties();
  var repo = ui.prompt('Setup 1/2',
    'GitHub repo (owner/name), e.g. EosLightmedia/ngs-daily-digest:',
    ui.ButtonSet.OK_CANCEL);
  if (repo.getSelectedButton() !== ui.Button.OK) return;
  var token = ui.prompt('Setup 2/2',
    'GitHub fine-grained token (Actions: read/write, Contents: read). ' +
    'Stored privately in Script Properties:',
    ui.ButtonSet.OK_CANCEL);
  if (token.getSelectedButton() !== ui.Button.OK) return;
  props.setProperty('GITHUB_REPO', repo.getResponseText().trim());
  props.setProperty('GITHUB_TOKEN', token.getResponseText().trim());
  ui.alert('Saved. Try "NGS Digest ▸ Send test to test channel".');
}

/* ── GitHub dispatch ────────────────────────────────────────────────────── */

function dispatch_(action, date) {
  var props = PropertiesService.getScriptProperties();
  var repo = props.getProperty('GITHUB_REPO');
  var token = props.getProperty('GITHUB_TOKEN');
  if (!repo || !token) {
    SpreadsheetApp.getUi().alert('Not set up yet — run "NGS Digest ▸ Setup… (admin)" first.');
    throw new Error('missing GITHUB_REPO / GITHUB_TOKEN');
  }
  var ref = props.getProperty('GITHUB_REF') || 'main';
  var inputs = { action: action };
  if (date) inputs.date = date;

  var url = 'https://api.github.com/repos/' + repo + '/actions/workflows/' +
            WORKFLOW_FILE + '/dispatches';
  var resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: {
      'Authorization': 'Bearer ' + token,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    },
    payload: JSON.stringify({ ref: ref, inputs: inputs })
  });
  var code = resp.getResponseCode();
  if (code !== 204) {
    SpreadsheetApp.getUi().alert(
      'GitHub did not accept the request (HTTP ' + code + ').\n\n' +
      resp.getContentText() +
      '\n\nCheck the repo name, token scopes, and that the branch "' + ref + '" exists.');
    throw new Error('dispatch failed: ' + code);
  }
}

/* ── Pause flag (named range read by the scheduled run) ─────────────────── */

function getPauseRange_() {
  var ss = SpreadsheetApp.getActive();
  var rng = ss.getRangeByName(PAUSE_RANGE);
  if (rng) return rng;
  // First use: create a small (hidden) Controls sheet + the named range.
  var sh = ss.getSheetByName(CONTROLS_SHEET) || ss.insertSheet(CONTROLS_SHEET);
  sh.getRange('A1').setValue('Automated digest paused? (managed by the NGS Digest menu)');
  sh.getRange('B1').setValue(false);
  ss.setNamedRange(PAUSE_RANGE, sh.getRange('B1'));
  sh.hideSheet();
  return ss.getRangeByName(PAUSE_RANGE);
}

function setPause_(state) {
  getPauseRange_().setValue(state ? true : false);
}

function isPaused_() {
  var v = getPauseRange_().getValue();
  return v === true || String(v).trim().toLowerCase() === 'true';
}

/* ── Helpers ────────────────────────────────────────────────────────────── */

function toast_(msg) {
  SpreadsheetApp.getActive().toast(msg, 'NGS Digest', 8);
}
