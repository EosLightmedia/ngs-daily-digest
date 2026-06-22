# NGS Daily Digest

A Slack digest of the NGS Museum of Exploration unveiling production schedule
(June 9–19, 2026). Each evening (~**4:17 PM ET**, see timing note below) it reads
the `Explorers_Fest_Production_Schedule` Google Sheet and posts **the next day's**
one-page schedule card to Slack:

- ⏱️ **Day span** — from the grey `Top/End of Day` marker rows
- 🔵 **Support** — the events that need the team on-site (time · location)
- 🟢 **Shows** — consecutive show rows collapsed into one entry with a combined summary
- 🧑‍🔧 **Crew Call** — per system (Q-Sys / Pixera / Network / Tech), who is on it and
  their day-span (first call → last out), with people **@-mentioned** and
  on-call/remote tagged. Spans are derived from the staffing columns across the
  whole day — there are no longer dedicated shift rows.
- 📋 a link back to the sheet for full detail

It's a *summary* — people open the sheet for the run-of-show.

## Collaborator controls (the **NGS Digest** menu in the sheet)

Everything that used to be a terminal command is now a menu item in the Google
Sheet (setup in *One-time setup ▸ 5*). Each "send" triggers the GitHub Actions
workflow and posts within ~1 minute.

| Menu item | What it does |
|-----------|--------------|
| **Send test to test channel** | Posts tomorrow's card to the **test** channel, marked `TEST`. Safe to use anytime. |
| **Send update (resend tomorrow)** | Re-posts tomorrow's card to the live channel marked `UPDATED` — use after the schedule changes. |
| **Send a chosen day…** | Pick any date and post that day's card to the live channel. |
| **Pause automated digest** | Stops the automatic evening send (sets the `DIGEST_PAUSED` flag). Manual sends above still work. |
| **Resume automated digest** | Turns the automatic evening send back on. |
| **Show digest status** | Tells you whether the automatic send is currently on or paused. |
| **Sort by time (within each day)** | Reorders rows under each day banner by Start time (blank/TBD last); banners stay put. Runs in the sheet (no GitHub token needed), preserves colours/dropdowns. |
| **Check formatting** | Runs the sheet linter: trims whitespace / fixes time formats automatically, and lists anything needing a human in a **Formatting Report** tab. |

## Timing

GitHub's scheduled runs have no guaranteed start time and are most delayed at the
top of the hour, so a literal 5:00 PM cron routinely landed ~5:45. The cron is
set to **20:17 UTC (~4:17 PM ET)** on purpose — firing early and off the top of
the hour means even GitHub's typical 15–45 min delay still lands by ~5:00 PM. It
posts the **next** day's schedule, so posting a little early is harmless.

## How it works

| File | Role |
|------|------|
| `digest.py` | CLI orchestrator: read sheet → build blocks → post (or dry-run) |
| `schedule_reader.py` | gspread read + day-block parsing + time/span/grouping helpers (header-name based) |
| `slack_digest.py` | Block Kit builders + staff @-mention resolution + posting |
| `make_digest_card.py` | renders the one-page PNG/PDF card (PIL) that gets posted |
| `config.py` | channels (main + test), sheet key, timezone, Type drivers, pause-flag name |
| `sheet_lint.py` | the "formatting clean up": validate the sheet + safe auto-fix + report |
| `apps_script/` | the **Google Sheet menu** collaborators use (Code.gs + DatePicker.html) |
| `staff_slack_ids.json` | first-name → Slack member ID map (member IDs are not secret) |
| `.github/workflows/daily-digest.yml` | the evening cron + manual `workflow_dispatch` (the menu's backend) |

The sheet's columns get reordered between sessions, so everything is resolved by
**header name**, never column letter.

## Local testing

```bash
pip install -r requirements.txt
# Dry run — prints Block Kit JSON, posts nothing, needs no Slack token:
python digest.py --date 2026-06-13 --dry-run
# Real post (needs SLACK_BOT_TOKEN in the env and the bot invited to the channel):
SLACK_BOT_TOKEN=xoxb-… python digest.py --date 2026-06-13
```

Locally, gspread uses the service-account key at
`~/.config/gspread/service_account.json`. (On macOS, run from `/tmp` if Python's
import scan hits a TCC permission error under `~/Desktop`.)

## One-time setup

### 1. Slack app
1. Create an app at <https://api.slack.com/apps> in the Eos Lightmedia workspace.
2. **OAuth & Permissions** → Bot Token Scopes: `chat:write`, `users:read`.
3. Install to the workspace → copy the **Bot User OAuth Token** (`xoxb-…`).
4. Invite the bot to the channel: `/invite @NGS Digest` in `#` (`C0B9YCS6ALR`).

### 2. Staff @-mentions
Fill `staff_slack_ids.json` with member IDs (Slack profile → **Copy member ID**).
Keys must match the names in the sheet's staffing columns exactly, including any
initial (e.g. `Liam H`, `Danny M`). Unmapped names post as bold text.

### 3. GitHub (EosLightmedia org, private repo)
```bash
gh repo create EosLightmedia/ngs-daily-digest --private --source=. --push
gh secret set SLACK_BOT_TOKEN          # paste the xoxb- token
gh secret set GSPREAD_SERVICE_ACCOUNT < ~/.config/gspread/service_account.json
# optional channel override (defaults to C0B9YCS6ALR):
gh variable set SLACK_CHANNEL_ID --body C0B9YCS6ALR
# the channel "Send test" posts to (keep this DIFFERENT from SLACK_CHANNEL_ID,
# otherwise test sends land in the live channel):
gh variable set TEST_CHANNEL_ID --body C0XXXXXXX
```

### 4. Test the cron path
Actions tab → **NGS Daily Digest** → **Run workflow** (optionally tick *dry run*).

### 5. The Google Sheet menu (for collaborators) — Apps Script
Lets non-technical collaborators run the digest from inside the sheet (no GitHub
access needed). One-time, by an admin with GitHub access:

1. **Create a fine-grained PAT** (<https://github.com/settings/tokens?type=beta>):
   repository access = **only `EosLightmedia/ngs-daily-digest`**; permissions:
   **Actions: Read and write**, **Contents: Read-only**, **Metadata: Read-only**.
2. In the sheet: **Extensions ▸ Apps Script**. Paste `apps_script/Code.gs` into
   `Code.gs`, then **+ ▸ HTML** a file named `DatePicker` and paste
   `apps_script/DatePicker.html`. Save.
3. Reload the sheet → an **NGS Digest** menu appears. Run **NGS Digest ▸ Setup…**
   once and enter the repo (`EosLightmedia/ngs-daily-digest`) and the PAT. The
   token is stored privately in Script Properties — collaborators never see it.

(If the repo isn't on the default branch `main`, set a `GITHUB_REF` Script
Property to the branch name.)

## Expanding later

Each section is an independent builder in `slack_digest.build_blocks`. Add a new
one (Needs Confirmation alerts, VIP movements, multi-day look-ahead, …) by
appending a builder and, if needed, a new Type constant in `config.py`.
