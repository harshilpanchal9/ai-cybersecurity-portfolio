# Sentinel AI Triage Copilot — script version

A lightweight AI triage workflow for Microsoft Sentinel, built to run with the
permissions available in a locked-down lab tenant (where Logic App playbook
creation is blocked). It does the same job as the planned Logic App playbook:

**New incident → Gemini triage draft → comment posted back on the incident for
analyst validation.**

## Setup (once)

1. Install **Python 3.9+** and the **Azure CLI**.
2. Sign in with your lab account (the one that can create incidents):
   `az login`
3. Get a Gemini API key at https://aistudio.google.com (free tier, no credit card).
   Set it as an environment variable so it never lives in the script:
   - Windows PowerShell: `$env:GEMINI_API_KEY="paste-key-here"`
   - macOS/Linux: `export GEMINI_API_KEY="paste-key-here"`
   (Or just paste it when the script asks — input is hidden.)

## Run

```bash
# 1. Dry run first: drafts triage summaries, posts nothing
python sentinel_triage_copilot.py --dry-run

# 2. Real run: posts the AI triage comment to each NEW incident
python sentinel_triage_copilot.py

# 3. Optional: keep watching for new incidents every 120 seconds
python sentinel_triage_copilot.py --watch 120
```

## Test it end to end

1. Create a test incident via the Sentinel REST API "Try It" page
   (Incidents - Create Or Update, severity `High`, status `New`).
2. Run the script.
3. Open the incident in the Defender portal → **Comments** — the AI triage
   summary should be there. Screenshot the incident, the comment, and the
   script output for the GitHub writeup.

The script records triaged incidents in `seen.json` (same folder), so
re-running it never double-comments an incident.

## Optional: automation rule in Sentinel (portal, no playbook needed)

Sentinel → Configuration → Automation → Create → Automation rule:

- Name: `Tag new High incidents for AI triage`
- Trigger: When incident is created
- Condition: Severity equals High
- Action: Add tag `ai-triage`

This is the part of the triage workflow that *does* work natively in the lab
tenant, and it complements the script.

## Troubleshooting

- `Could not get an Azure token` → run `az login` with your lab account first.
- `Listing incidents failed (HTTP 401/403)` → wrong account, or the account
  lacks Sentinel read permission on this workspace.
- `Found 0 incidents` → check the subscription / resource group / workspace
  at the top of the script match the workspace holding your test incidents.
- `Gemini call failed (HTTP 400)` → the request body is malformed; check the
  prompt text. `HTTP 429` → free-tier rate limit; wait a minute and retry.
- `Comment failed (HTTP 403)` → the account can create incidents but not
  comments; that permission gap ends the script path too — fall back to the
  own-Azure-account plan.
