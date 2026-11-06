"""End-to-end check on the synthetic county: every step runs and the outputs hang together."""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from territory_gtm.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_demo_end_to_end(tmp_path):
    proj = tmp_path / "demo"
    main(["demo", str(proj)])
    out = proj / "output"
    xlsx = out / "example_county_tree_care_leads.xlsx"
    assert xlsx.exists()
    sheets = pd.ExcelFile(xlsx).sheet_names
    for s in ["Summary", "Management Companies", "HOA - Managed", "Golf", "Contacts", "Method", "Rules"]:
        assert s in sheets
    a = pd.read_parquet(proj / "work" / "accounts.parquet")
    assert a["score"].between(0, 100).all()
    assert set(a["tier"]) <= {"A", "B", "C"}
    assert a["outreach_angle"].str.contains(r"\{").sum() == 0  # every template field filled
    # verified firm aliases roll many associations up to one manager
    hm = a[a["primary_segment"] == "hoa_managed"]
    assert hm["properties"].max() >= 5
    # business contacts only: the planted personal gmail address is dropped
    c = pd.read_csv(out / "csv" / "contacts.csv")
    assert not c["business_email"].fillna("").str.contains("gmail").any()
    # self-managed HOAs and districts are never sent to people search
    sl = pd.read_csv(out / "contacts" / "shortlist.csv")
    assert not sl["segment_label"].isin(["HOA – Self-Managed", "Utility & Special Districts"]).any()
    assert (out / "clay" / "clay_companies.csv").exists()
    assert (out / "call_sheet_top50.md").read_text().count("## ") == 50
    assert list((out / "alerts").glob("alerts_*.csv"))


def run_hook(event, env=None):
    r = subprocess.run([sys.executable, str(ROOT / "hooks" / "guardrails.py")], input=json.dumps(event),
                       capture_output=True, text=True, env=env)
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else None


def test_guardrails(tmp_path):
    (tmp_path / "county.yaml").write_text("name: x")
    (tmp_path / "trade.yaml").write_text("id: x")
    cwd = str(tmp_path)
    assert run_hook({"tool_name": "mcp__s__apollo_emailer_campaigns_add_contact_ids", "cwd": cwd}) == "deny"
    assert run_hook({"tool_name": "mcp__s__apollo_people_bulk_match", "cwd": cwd}) == "ask"
    assert run_hook({"tool_name": "mcp__s__apollo_mixed_people_api_search", "cwd": cwd}) is None
    assert run_hook({"tool_name": "Bash", "tool_input": {"command": "clay routines runs start f"}, "cwd": cwd}) == "ask"
    # outside a project the plugin stays out of the way
    elsewhere = tmp_path / "elsewhere" / "deeper"
    elsewhere.mkdir(parents=True)
    (tmp_path / "county.yaml").unlink()
    assert run_hook({"tool_name": "mcp__s__apollo_emailer_campaigns_add_contact_ids", "cwd": str(elsewhere)}) is None
