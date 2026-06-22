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

/** Called from the DatePicker dialog. date is "YYYY-MM-DD". */
function dispatchChosenDay(date) {
  dispatch_('send', date || '');
  toast_('Send triggered for ' + (date || 'tomorrow') + ' — posts in ~1 min.');
}

function menuCheckFormatting() {
  dispatch_('check_formatting', '');
  toast_('Formatting check triggered — results land in the "Formatting Report" tab in ~1 min.');
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
