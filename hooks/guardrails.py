"""PreToolUse guardrails for canopy-based-leads. Standard library only.

- BLOCK anything that contacts people or writes to a CRM: sending email, adding people to
  sequences or campaigns, creating contacts / accounts / deals / tasks.
- ASK before anything that spends enrichment credits (Apollo person / company enrichment,
  email and phone checks, Clay data points and enrichment runs), so the count and estimated
  cost are always approved by a person first.

The guardrails apply while Claude works in a canopy-based-leads project: the working folder (or a
folder above it, or one directly below it) holds county.yaml and trade.yaml. Elsewhere the
plugin stays out of the way. CANOPY_LEADS_GUARDRAILS=always applies them everywhere; =off disables them.

The research is the product; outreach is a separate decision a person makes in their own
tools. To allow outreach tools in a later session, set CANOPY_LEADS_ALLOW_OUTREACH=1. Edit the lists
below to match the tools you connect.
"""
import json
import os
import re
import sys
from pathlib import Path

BLOCK = [  # substrings of MCP tool names
    "emailer_campaigns_add_contact_ids", "emailer_campaigns_approve", "emailer_messages_send_now",
    "emailer_messages_create", "sequences_create", "sequences_update", "contacts_create", "contacts_bulk_create",
    "contacts_update", "accounts_create", "accounts_bulk_create", "accounts_update", "deals_create",
    "tasks_create", "tasks_bulk_create", "phone_calls_create", "labels_add_entity_ids", "send_message",
    "send_email", "send_now", "upsert-record", "create-record", "add-record-to-list",
]
ASK = [  # credit-spending enrichment
    "people_match", "people_bulk_match", "bulk_enrich", "organizations_enrich", "email_validation",
    "phone_validation", "add-contact-data-points", "add-company-data-points", "run_subroutine",
    "find_prospects", "enrich",
]
BASH_BLOCK = re.compile(r"\bclay\s+campaigns?\b.*\b(enroll|launch|start|send)\b", re.I)
BASH_ASK = re.compile(r"\bclay\s+(routines\s+runs\s+start|signals\s+(create|resume)|credits\s+top-up)\b", re.I)


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def in_project(cwd):
    d = Path(cwd or ".").resolve()
    is_proj = lambda p: (p / "county.yaml").exists() and (p / "trade.yaml").exists()  # noqa: E731
    if any(is_proj(p) for p in [d, *d.parents]):
        return True
    try:
        return any(is_proj(c) for c in d.iterdir() if c.is_dir()) or any(
            is_proj(g) for c in d.iterdir() if c.is_dir() and c.name in ("runs", "projects") for g in c.iterdir() if g.is_dir())
    except OSError:
        return False


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        sys.exit(0)
    mode = os.environ.get("CANOPY_LEADS_GUARDRAILS", "project")
    if mode == "off" or (mode != "always" and not in_project(event.get("cwd"))):
        sys.exit(0)
    tool = event.get("tool_name", "")
    outreach_ok = os.environ.get("CANOPY_LEADS_ALLOW_OUTREACH") == "1"
    if tool == "Bash":
        cmd = str((event.get("tool_input") or {}).get("command", ""))
        if BASH_BLOCK.search(cmd) and not outreach_ok:
            decide("deny", "canopy-based-leads guardrail: research and files only. Enrolling people in campaigns is "
                           "blocked. Set CANOPY_LEADS_ALLOW_OUTREACH=1 in a separate session if you decide to do outreach.")
        if BASH_ASK.search(cmd):
            decide("ask", "canopy-based-leads credit gate: this can spend Clay credits. Approve only if you have seen the "
                          "record count and the estimated cost.")
        sys.exit(0)
    if not tool.startswith("mcp__"):
        sys.exit(0)
    name = tool.split("__", 2)[-1].lower()
    if not outreach_ok and any(b in name for b in BLOCK):
        decide("deny", f"canopy-based-leads guardrail: '{name}' would contact people or write to a CRM. This plugin does "
                       "research and files only. Hand the CSVs to your team, or set CANOPY_LEADS_ALLOW_OUTREACH=1 in a "
                       "separate session if you decide to do outreach.")
    if any(a in name for a in ASK):
        decide("ask", f"canopy-based-leads credit gate: '{name}' can spend enrichment credits. Approve only if you have "
                      "seen the record count and the estimated cost for this batch.")
    sys.exit(0)


if __name__ == "__main__":
    main()
