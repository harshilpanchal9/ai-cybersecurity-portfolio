#!/usr/bin/env python3
"""
Sentinel AI Triage Copilot -- script version.

Does the same job as the planned Logic App playbook, but runnable with the
permissions Harshil actually has in the TryHackMe tenant (where Logic App
playbook creation is blocked):

  1. Lists NEW incidents in a Microsoft Sentinel workspace (REST API).
  2. Sends each one to Google Gemini (AI Studio, free tier) for a triage draft.
  3. Posts the draft back to the incident as a comment, for analyst validation.
  4. Remembers processed incidents in seen.json so nothing gets commented twice.

Prerequisites (run on your own machine):
  - Python 3.9+
  - Azure CLI installed, signed in once with your lab account:  az login
  - A Gemini API key from https://aistudio.google.com (free tier).
    Pass it via the GEMINI_API_KEY environment variable, or paste it when asked.
    Never commit it to git, never paste it into chat.

Usage:
    python sentinel_triage_copilot.py                 # one pass over new incidents
    python sentinel_triage_copilot.py --dry-run        # draft only, post nothing
    python sentinel_triage_copilot.py --watch 120      # repeat every 120 seconds
"""

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API_VERSION = "2022-07-01-preview"

# --- Edit these defaults if your lab workspace differs ---
DEFAULT_SUBSCRIPTION_ID = "1746294a-5aa8-4cbb-82a4-11e731b20942"
DEFAULT_RESOURCE_GROUP = "rg-10189781"
DEFAULT_WORKSPACE = "eastus-sentinel-10189781"

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

TRIAGE_PROMPT_TEMPLATE = """You are a Tier 1 SOC analyst assistant. Given this Microsoft Sentinel incident, produce a triage summary with: 1) What happened (plain language), 2) Severity justification, 3) Three concrete next investigation steps. Mark anything you are unsure about with [UNVERIFIED]. Do not invent entities not present below.

Incident title: {title}
Severity: {severity}
Description: {description}
Incident number: {number}
"""

SEEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")


def get_azure_token(subscription_id):
    """Get a management.azure.com token from the Azure CLI login, if available."""
    try:
        out = subprocess.run(
            ["az", "account", "get-access-token",
             "--subscription", subscription_id,
             "--query", "accessToken", "--output", "tsv"],
            capture_output=True, text=True, timeout=60, check=True,
        )
        token = out.stdout.strip()
        return token or None
    except Exception:
        return None


def sentinel_request(method, url, token, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, {"_error_body": raw}
    except urllib.error.URLError as e:
        return 0, {"_error_body": str(e)}


def list_incidents(base, token):
    """List all incidents in the workspace (paginated)."""
    incidents = []
    url = f"{base}/incidents?api-version={API_VERSION}"
    while url:
        status, payload = sentinel_request("GET", url, token)
        if status != 200:
            print(f"[!] Listing incidents failed (HTTP {status}): "
                  f"{str(payload.get('_error_body', payload))[:500]}")
            return incidents
        incidents.extend(payload.get("value", []))
        url = payload.get("nextLink")
    return incidents


def gemini_triage(api_key, incident):
    props = incident.get("properties", {})
    prompt = TRIAGE_PROMPT_TEMPLATE.format(
        title=props.get("title", "(no title)"),
        severity=props.get("severity", "(unknown)"),
        description=props.get("description", "(no description)"),
        number=props.get("incidentNumber", "(unknown)"),
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(
        GEMINI_URL + "?key=" + urllib.parse.quote(api_key),
        data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"[!] Gemini call failed (HTTP {e.code}): {raw[:500]}")
        return None
    try:
        return payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        print(f"[!] Unexpected Gemini response: {json.dumps(payload)[:500]}")
        return None


def post_comment(base, token, incident_id, message):
    comment_id = str(uuid.uuid4())
    url = (f"{base}/incidents/{incident_id}/comments/{comment_id}"
           f"?api-version={API_VERSION}")
    return sentinel_request("PUT", url, token, {"properties": {"message": message}})


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


def run_once(args, api_key, seen):
    token = get_azure_token(args.subscription)
    if not token:
        print("[!] Could not get an Azure token from the Azure CLI.")
        print("    Run 'az login' with your lab account first, or paste a token below.")
        token = getpass.getpass("Azure access token (paste, hidden): ").strip()
        if not token:
            return False
    base = (f"https://management.azure.com/subscriptions/{args.subscription}"
            f"/resourceGroups/{args.resource_group}"
            f"/providers/Microsoft.OperationalInsights/workspaces/{args.workspace}"
            f"/providers/Microsoft.SecurityInsights")
    incidents = list_incidents(base, token)
    new_ones = [i for i in incidents
                if i.get("properties", {}).get("status") == "New"]
    print(f"[*] Found {len(incidents)} incident(s), {len(new_ones)} with status New.")
    fresh = [i for i in new_ones if i.get("name") not in seen]
    print(f"[*] {len(fresh)} not yet triaged by this script.")
    for inc in fresh:
        name = inc.get("name")
        title = inc.get("properties", {}).get("title", name)
        print(f"\n[*] Triaging: {title} (id: {name})")
        summary = gemini_triage(api_key, inc)
        if summary is None:
            print("    Skipped (Gemini error). Will retry next run.")
            continue
        comment = ("AI triage draft -- verify before acting:\n\n" + summary +
                   "\n\n---\n_Posted by Sentinel AI Triage Copilot (Gemini). "
                   "Analyst validation required._")
        if args.dry_run:
            print("    [dry-run] Would post comment:\n")
            print(comment)
            continue
        status, payload = post_comment(base, token, name, comment)
        if status in (200, 201):
            print(f"    [ok] Comment posted to incident {name}.")
            seen[name] = {
                "title": title,
                "commented_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            save_seen(seen)
        else:
            print(f"    [!] Comment failed (HTTP {status}): {str(payload)[:500]}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sentinel AI Triage Copilot (script version)")
    parser.add_argument("--subscription", default=DEFAULT_SUBSCRIPTION_ID)
    parser.add_argument("--resource-group", default=DEFAULT_RESOURCE_GROUP)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--watch", type=int, default=0, metavar="SECONDS",
                        help="Repeat every SECONDS instead of running once "
                             "(0 = run once)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Draft triage summaries but do not post comments")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        api_key = getpass.getpass("Gemini API key (paste, hidden): ").strip()
    if not api_key:
        print("[!] No Gemini API key provided. Exiting.")
        sys.exit(1)

    seen = load_seen()
    while True:
        ok = run_once(args, api_key, seen)
        if not ok or not args.watch:
            break
        print(f"\n[*] Sleeping {args.watch}s before next pass...")
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
