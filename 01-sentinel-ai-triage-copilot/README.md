# Sentinel AI Triage Copilot

A SOAR playbook that auto-triages High-severity Microsoft Sentinel incidents
with an LLM and posts a validated summary back on the incident as a comment.

**Status: ✅ Verified end to end on 2026-11-08.** A real test incident
triggered the automation rule, the playbook ran successfully, Gemini wrote a
triage summary, and the summary appeared as a comment on the incident.
See [Test result](#test-result---verified-2026-11-08).

## What it does

1. A High-severity incident appears in Microsoft Sentinel.
2. An automation rule runs the playbook.
3. The playbook sends the incident to Gemini (LLM) for a triage summary.
4. The playbook posts that summary as a comment on the incident.
5. An analyst still validates it. The AI does not close anything, and it
   marks anything it is unsure about with `[UNVERIFIED]` instead of
   inventing details.

## How it works

| Step | What | Details |
|------|------|---------|
| Trigger | Microsoft Sentinel incident (preview trigger) | Fires when the automation rule runs the playbook for an incident |
| HTTP | POST to Gemini | `generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent` — incident title, severity, description and incident number are passed in the prompt; the prompt asks for what happened, severity justification, and three next investigation steps, and requires `[UNVERIFIED]` on anything unsure |
| Compose | Data Operations | Extracts the AI text from Gemini's reply: `body('HTTP')?['candidates'][0]?['content']?['parts'][0]?['text']` |
| Add comment to incident (V3) | Microsoft Sentinel connector | Posts the Compose output as a comment on the incident (Incident ARM ID from the trigger) |

Automation rule **"Run AI triage on new incidents"**: trigger *When incident
is created*, condition *Severity = High*, action *Run playbook
ai-triage-copilot*.

## Built on

- Azure free trial, subscription with spending cap ON, $20 budget alert
- Resource group: `rg-ai-soc-lab` (Canada Central)
- Log Analytics workspace: `law-ai-soc-lab` (Pay-as-you-go, Per GB 2018 tier)
- Microsoft Sentinel enabled on the workspace (31-day trial, 0 GB ingested)
- Playbook: `ai-triage-copilot` (Logic Apps Consumption plan, stateful)
- Gemini API key from Google AI Studio (free tier) — **never committed;
  the exported playbook uses `YOUR_GEMINI_API_KEY` as a placeholder**

## Cost

$0. No log ingestion, no data connectors, Logic Apps Consumption (first
4,000 actions free), Gemini free tier. The playbook only runs when a
High-severity incident is created.

## Test result — verified 2026-11-08

Test incident: **"Impossible travel sign-in detected"**, Severity High,
Status New, created by hand in the Azure portal (Sentinel → Incidents →
Create incident). The automation rule fired, the Logic App run history shows
the workflow ran successfully, and this comment appeared on the incident,
posted by `Playbook-ai-triage-copilot`:

> ### Incident Triage Summary
>
> **Incident Number:** [UNVERIFIED]
> **Title:** Impossible travel sign-in detected
> **Current Severity:** High
>
> ### 1) What Happened (Plain Language)
> A single user account [UNVERIFIED: username not provided] registered
> successful or attempted sign-ins from two different countries within a
> 30-minute span. Because it is physically impossible for a person to travel
> between two different countries in that timeframe, this pattern suggests
> that credentials may be compromised and used concurrently by an
> unauthorized party, or that an anonymizing network service (such as a VPN
> or proxy) is in use.
>
> ### 2) Severity Justification
> The **High** severity rating is justified because impossible travel is a
> primary indicator of credential compromise and active unauthorized account
> access. If an external attacker has valid credentials, they can bypass
> perimeter controls, access corporate data, or establish persistence.
> Immediate triage is required to confirm whether the account has been
> hijacked and to prevent potential lateral movement or data exfiltration.
>
> ### 3) Concrete Next Investigation Steps
> 1. **Identify and analyze the sign-in events:** Query the
>    identity/sign-in logs for the specific account to identify the two
>    source IP addresses, the specific countries, client applications,
>    device compliance status, and whether Multi-Factor Authentication (MFA)
>    was prompted and successfully satisfied.
> 2. **Evaluate IP reputation and connection context:** Perform IP
>    enrichment on both source addresses to determine if either originates
>    from a known commercial VPN, cloud hosting provider, corporate proxy,
>    or known malicious infrastructure.
> 3. **Contact the user out-of-band:** Reach out to the affected user
>    through a verified out-of-band channel (e.g. phone call) to confirm
>    their actual physical location and determine if they initiated both
>    sessions (for example, by using a personal VPN). If the activity is
>    unconfirmed, immediately revoke active sessions and reset the user's
>    credentials.

Note the `[UNVERIFIED]` marks: the model correctly refused to invent an
incident number or a username it was not given. That is the validation
behaviour the prompt was designed for.

Screenshots: see [`screenshots/`](screenshots/).

## Deploy it yourself

1. Create a resource group and a Log Analytics workspace; enable Microsoft
   Sentinel on the workspace.
2. Get a Gemini API key at https://aistudio.google.com (free tier).
3. Import the playbook from [`playbook/ai-triage-copilot.json`](playbook/)
   (Logic Apps Consumption), or rebuild it in the designer: Sentinel
   incident trigger → HTTP POST to Gemini → Compose → Add comment to
   incident (V3). Put your key in the HTTP URI where it says
   `YOUR_GEMINI_API_KEY`.
4. Create the automation rule in Sentinel: *When incident is created*,
   *Severity = High*, action *Run playbook ai-triage-copilot*.
5. Grant Sentinel permission to run the playbook: Sentinel → Settings →
   Playbook permissions → Configure permissions → check the resource group
   → Apply. This gives Sentinel's service account the **Microsoft Sentinel
   Automation Contributor** role on the resource group. (In this build the
   portal banner's Update button failed, and the role was granted manually
   in the resource group's Access control (IAM): Add role assignment →
   Microsoft Sentinel Automation Contributor → member "Azure Security
   Insights". Allow ~10 minutes for the role to take effect.)
6. Create a test incident (Sentinel → Incidents → Create incident, Severity
   High). Wait 2–5 minutes, then open the incident → Comments tab.

## Troubleshooting

- **No comment appears:** check the automation rule is on and the incident
  severity is High; then check the playbook's Run history for a failed run.
- **Playbook never runs:** Sentinel lacks the Automation Contributor role on
  the playbook's resource group — see step 5 above.
- **HTTP 404 from Gemini:** the model name is retired; use a current
  `gemini-*-flash` model. **HTTP 503:** the model is busy; resubmit the run
  or create a new test incident.
- **Incident not visible in the Defender portal:** manually created
  incidents are not synced to Defender; view them in Sentinel in the Azure
  portal.

## Files

- [`playbook/ai-triage-copilot.json`](playbook/) — exported playbook
  definition (API key scrubbed to a placeholder).
- [`test-incident.json`](test-incident.json) — the test incident used for
  verification.
- [`screenshots/`](screenshots/) — workspace, playbook designer, automation
  rule, incident and AI comment.
- [`script-fallback/`](script-fallback/) — a Python version of the same
  workflow (poll Sentinel API → Gemini triage → post comment), built earlier
  for a locked-down lab tenant where Logic App creation was blocked. The
  Logic App is the primary build; the script is kept as a fallback.
