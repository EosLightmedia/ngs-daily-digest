# NGS Daily Digest

A morning Slack digest of the NGS Museum of Exploration unveiling production
schedule (June 9–19, 2026). Every morning at **7:00 AM ET** it reads the
`Explorers_Fest_Production_Schedule` Google Sheet and posts a summary to Slack:

- ⏱️ **Day span** — from the grey `Top/End of Day` marker rows
- 🔵 **Support Required** — the events that need the team on-site (time · location)
- 🟢 **Shows** — consecutive show rows collapsed into one entry with a combined summary
- 🟡 **On shift** — the day's Eos staff shifts, with people **@-mentioned**
- 📋 a link back to the sheet for full detail

It's a *summary* — people open the sheet for the run-of-show.

## How it works

| File | Role |
|------|------|
| `digest.py` | CLI orchestrator: read sheet → build blocks → post (or dry-run) |
| `schedule_reader.py` | gspread read + day-block parsing + time/span/grouping helpers (header-name based) |
| `slack_digest.py` | Block Kit builders + staff @-mention resolution + posting |
| `config.py` | channel, sheet key, timezone, the Type values that drive each section |
| `staff_slack_ids.json` | first-name → Slack member ID map (member IDs are not secret) |
| `.github/workflows/daily-digest.yml` | the 7 AM ET cron + manual `workflow_dispatch` |

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
Fill `staff_slack_ids.json` with member IDs (Slack profile → **Copy member ID**)
for: Oona, Danny, James, Rick, Benjamin. Unmapped names post as bold text.

### 3. GitHub (EosLightmedia org, private repo)
```bash
gh repo create EosLightmedia/ngs-daily-digest --private --source=. --push
gh secret set SLACK_BOT_TOKEN          # paste the xoxb- token
gh secret set GSPREAD_SERVICE_ACCOUNT < ~/.config/gspread/service_account.json
# optional channel override (defaults to C0B9YCS6ALR):
gh variable set SLACK_CHANNEL_ID --body C0B9YCS6ALR
```

### 4. Test the cron path
Actions tab → **NGS Daily Digest** → **Run workflow** (optionally tick *dry run*).

## Expanding later

Each section is an independent builder in `slack_digest.build_blocks`. Add a new
one (Needs Confirmation alerts, VIP movements, multi-day look-ahead, …) by
appending a builder and, if needed, a new Type constant in `config.py`.
