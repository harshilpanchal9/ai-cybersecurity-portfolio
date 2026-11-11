# Detection-as-Code

Own detection rules, written as code, mapped to MITRE ATT&CK, and tested against real events in Microsoft Sentinel.

## How it works

- Each rule is written in **Sigma** (vendor-neutral format).
- The Sigma rule is compiled to **KQL** for Microsoft Sentinel.
- The KQL runs as a scheduled analytics rule in Sentinel.
- Rules are tested by doing the action in Azure and watching the alert fire.

## Rules

| ID | Rule | ATT&CK | Data source |
|----|------|--------|-------------|
| DET-001 | Azure role assignment created | T1098.003 | AzureActivity |

## Tools

Sigma, KQL, Microsoft Sentinel, MITRE ATT&CK.
