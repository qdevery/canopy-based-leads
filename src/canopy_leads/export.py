"""Step 7: everything a sales team uses, written to output/:

  <county>_<trade>_leads.xlsx   Summary, one tab per segment, Management Companies,
                                Associations, Contacts, Method, Rules, Sources
  csv/                          a CSV of every tab
  clay/                         clay_companies.csv, clay_people.csv, clay_communities.csv
  call_sheet_top50.md           the first 50 calls with the angle for each
  alert_points.csv              one point per property, for the weekly storm alert

contacts.csv in the project folder (from the contacts step) is merged in when present.
Personal / free-mail addresses are always dropped: business contacts only.
"""
import re
from datetime import date

import numpy as np
import pandas as pd

from .classify import table_of_rules
from .project import log
from .score import nice

FREE_MAIL = re.compile(r"@(?:gmail|yahoo|hotmail|aol|outlook|icloud|me|live|msn|comcast|att|sbcglobal|verizon|"
                       r"bellsouth|cox|charter|earthlink|protonmail|ymail|mail)\.", re.I)
CONTACT_COLS = ["account_id", "account", "contact_type", "name", "title", "company", "business_email", "email_status",
                "business_phone", "linkedin_url", "city", "source", "found_on"]
MGMT_TYPES = ["Care-of firm on mailing", "Firm at shared mailing address", "Management company (name pending)",
              "Operator / management company", "Verified firm"]


def sheet_name(s):
    return re.sub(r"[\[\]\*\?/\\:]", "-", str(s))[:31]


def file_name(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def search_name(account):
    """The name to give Apollo / Clay: no 'GROUP (+n related entities)', no pending-manager tag."""
    s = re.sub(r" group \(\+\d+ related entit(y|ies)\)$", "", str(account), flags=re.I)
    return "" if s.upper().startswith("UNNAMED MANAGER") else s


def load_contacts(p, accounts):
    path = p.dir / "contacts.csv"
    if not path.exists():
        return pd.DataFrame(columns=CONTACT_COLS)
    c = pd.read_csv(path, dtype=str).fillna("")
    for col in CONTACT_COLS:
        if col not in c:
            c[col] = ""
    free = c["business_email"].str.contains(FREE_MAIL)
    if free.any():
        log(f"contacts: dropped {int(free.sum())} personal / free-mail addresses (business contacts only)")
        c.loc[free, ["business_email", "email_status"]] = ["", "personal address dropped"]
    # link by account_id, else by account name
    ids = dict(zip(accounts["account"].str.upper(), accounts["account_id"]))
    miss = c["account_id"] == ""
    c.loc[miss, "account_id"] = c.loc[miss, "account"].str.upper().map(ids).fillna("")
    unlinked = c["account_id"] == ""
    if unlinked.any():
        log(f"contacts: {int(unlinked.sum())} rows match no account_id or account name — left out")
    return c[~unlinked][CONTACT_COLS]


def rank_contacts(c, trade):
    pats = trade.get("contact_titles", [])

    def rank(t):
        t = str(t).lower()
        return next((i for i, pat in enumerate(pats) if re.search(pat, t)), len(pats))

    c = c.copy()
    c["_r"] = (c["title"].map(rank) + (c["business_email"] == "") * 20
               + (~c["contact_type"].str.lower().str.startswith("person")) * 100)
    return c.sort_values(["account_id", "_r"]).drop(columns="_r")


def shortlist(p, tiers=("A",), max_people=3):
    """Accounts to research for contacts, with the credit estimate to approve first."""
    a = pd.read_parquet(p.work / "accounts.parquet")
    segs = p.segments()
    no_search = {k for k, s in segs.items() if not s.get("people_search", True)}
    have = set(load_contacts(p, a)["account_id"])
    s = a[a["tier"].isin(tiers) & ~a["primary_segment"].isin(no_search) & ~a["account_id"].isin(have)].copy()
    s["search_name"] = s["account"].map(search_name)
    s = s[s["search_name"] != ""]
    s["titles_to_find"] = s["primary_segment"].map(lambda k: segs.get(k, {}).get("buyer_titles", ""))
    s["max_people"] = max_people
    out = p.out / "contacts"
    out.mkdir(exist_ok=True)
    cols = ["account_id", "account", "search_name", "segment_label", "tier", "score", "site_city", "firm_website",
            "titles_to_find", "max_people"]
    s[cols].to_csv(out / "shortlist.csv", index=False)
    skipped = a[a["tier"].isin(tiers) & a["primary_segment"].isin(no_search)]
    print(f"\nContact shortlist: {len(s)} accounts (tiers {', '.join(tiers)}), written to {out / 'shortlist.csv'}")
    print(f"  Upper bound if every account returns {max_people} people: {len(s) * max_people:,} people")
    print("  Credit estimate (check your own plan's pricing before approving):")
    print(f"    Apollo people search ............ free (no emails or phones)")
    print(f"    Apollo person enrichment ........ ~1 credit per person -> up to {len(s) * max_people:,} credits")
    print(f"    Clay work-email lookups (gaps) .. varies by provider; run on a 10-row sample first")
    if len(skipped):
        print(f"  Not searched by rule: {len(skipped)} accounts in {', '.join(sorted({p.label(k) for k in skipped['primary_segment']}))}"
              " (no people lookups; use public websites / office lines)")
    print("  Nothing has been spent. Approve the count and cost before any enrichment.\n")
    return s


def export(p):
    a = pd.read_parquet(p.work / "accounts.parquet")
    leads = pd.read_parquet(p.work / "leads_scored.parquet")
    t, c = p.trade, p.county
    segs = p.segments()
    contacts = rank_contacts(load_contacts(p, a), t)
    best = contacts.drop_duplicates("account_id").set_index("account_id")
    a["contacts_found"] = a["account_id"].map(contacts.groupby("account_id").size()).fillna(0).astype(int)
    for col, src in [("best_contact", "name"), ("best_contact_title", "title"), ("best_contact_company", "company"),
                     ("best_contact_email", "business_email"), ("best_contact_phone", "business_phone")]:
        a[col] = a["account_id"].map(best[src]).fillna("") if len(best) else ""
    a["src_contacts"] = a["account_id"].map(best["source"]).fillna("") if len(best) else ""
    a["business_phone"] = a.get("business_phone", pd.Series(index=a.index, dtype=str))
    a["src_acreage"] = c.get("roll_source", "county appraisal roll") + " acreage (parcel polygon where missing); summed per account"
    a["src_canopy"] = c.get("canopy_source", "USFS/NLCD Tree Canopy Cover 2021, 30 m") + " over parcel polygons"

    storm_cols = [col for col in a if re.search(r"_(gust_mph|nearest_km|reports_10km)$", col)]
    pts = ["pts_acreage", "pts_canopy", "pts_properties", "pts_segment_fit", "pts_storm"]
    acct_cols = (["account_id", "account", "score", "tier", "outreach_angle", "segment_label", "buyer_type", "properties",
                  "parcels", "total_acres", "canopy_acres", "canopy_pct", "storm_exposure_0_100"] + storm_cols
                 + ["site_name", "site_street", "site_city", "other_sites", "mailing_address", "business_phone",
                    "district_consultant", "firm_website", "contacts_found", "best_contact", "best_contact_title",
                    "best_contact_company", "best_contact_email", "best_contact_phone"] + pts
                 + ["confidence", "owner_entities", "segments_all", "src_buyer", "src_acreage", "src_canopy", "src_storm",
                    "src_contacts", "src_score", "src_angle"])
    acct = a[[col for col in acct_cols if col in a]].copy()
    acct[["total_acres", "canopy_acres"]] = acct[["total_acres", "canopy_acres"]].round(1)

    tabs = {}
    ms = t.get("buyer", {}).get("managed_split")
    mgmt = acct[a["buyer_type"].isin(MGMT_TYPES)]
    tabs["Management Companies"] = mgmt
    for k, s in segs.items():
        if ms and k == ms["segment"]:
            continue
        tabs[s.get("tab", s["label"])] = acct[a["primary_segment"] == k]
    assoc = pd.DataFrame()
    if ms:
        hm = leads[leads["segment_final"] == ms["managed"]]
        g = hm.groupby("property_key")
        assoc = pd.DataFrame({
            "management_company": g["account"].first(), "parcels": g.size(), "acres": g["acreage"].sum().round(1),
            "canopy_acres": g["canopy_acres_est"].sum().round(1),
            "storm_exposure_0_100": (100 * g["w_storm"].sum() / g["acreage"].sum()).round(0),
            "site_city": g["site_city"].first().fillna("").str.title(), "sample_address": g["site_addr"].first(),
            "name_variants": g["name_variants"].first() if "name_variants" in hm else "",
            "manager_conflict": g["manager_conflict"].first() if "manager_conflict" in hm else "",
        }).reset_index().rename(columns={"property_key": "association"})
        assoc["association"] = assoc["association"].map(nice)
        assoc = assoc.merge(a[["account", "account_id", "score", "tier"]].rename(
            columns={"account": "management_company", "score": "manager_score", "tier": "manager_tier"}),
            on="management_company", how="left").sort_values(["manager_score", "acres"], ascending=False)
        tabs[sheet_name(f"{p.label(ms['managed'])} - communities")] = assoc

    contacts_out = contacts.merge(a[["account_id", "segment_label", "score", "tier"]], on="account_id", how="left")

    # ---------------------------------------------------------------- summary
    rows = []
    for k, s in segs.items():
        if ms and k == ms["segment"]:
            continue
        ls, ac = leads[leads["segment_final"] == k], a[a["primary_segment"] == k]
        rows.append({"segment": s["label"], "accounts": len(ac), "properties": ls["property_key"].nunique(),
                     "parcels": len(ls), "acres": round(ls["acreage"].sum()),
                     "canopy_acres": round(ls["canopy_acres_est"].sum()), "avg_score": round(ac["score"].mean(), 1) if len(ac) else None,
                     "tier_A": int((ac["tier"] == "A").sum()), "tier_B": int((ac["tier"] == "B").sum()),
                     "accounts_with_contacts": int((ac["contacts_found"] > 0).sum())})
    summ = pd.DataFrame(rows)
    summ.loc[len(summ)] = ["Total", len(a), summ["properties"].sum(), summ["parcels"].sum(), summ["acres"].sum(),
                           summ["canopy_acres"].sum(), round(a["score"].mean(), 1), int((a["tier"] == "A").sum()),
                           int((a["tier"] == "B").sum()), int((a["contacts_found"] > 0).sum())]
    top10 = acct.head(10)[["account", "score", "tier", "segment_label", "properties", "total_acres", "canopy_acres",
                           "storm_exposure_0_100", "outreach_angle"]]
    sc = t.get("score", {})
    method = pd.DataFrame(
        [(f"{k.replace('_', ' ').title()} ({(sc.get(k) or {}).get('points', d)} pts)", txt) for k, d, txt in [
            ("acreage", 25, "log scale of total acres; full points at " + str((sc.get("acreage") or {}).get("full_at", 300)) + "+ acres"),
            ("canopy", 20, "canopy acres (log) blended with canopy share of the grounds"),
            ("properties", 15, "log scale of properties per buyer; 1 property = 0"),
            ("segment_fit", 20, "; ".join(f"{s['label']} {s.get('fit', 0.5):.2f}" for s in segs.values())),
            ("storm", 20, "acre-weighted storm exposure: " + "; ".join(
                f"{e['name']} ({e.get('method')}, weight {e.get('weight', 1):g})" for e in c.get("storm_events", [])))]]
        + [("Tiers", f"A = {t.get('tiers', {}).get('A', 60)}+, B = {t.get('tiers', {}).get('B', 45)}+, C = below")]
        + [("Built", f"{date.today().isoformat()} with canopy-based-leads")]
        + [("Not done", "No emails sent, no sequences, no CRM records. No personal emails, cell phones, home "
                        "addresses or lookups of association board members.")],
        columns=["item", "detail"])
    sources = pd.DataFrame(c.get("sources", []) + t.get("sources", []))

    stem = p.file_stem
    xlsx = p.out / f"{stem}_leads.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Summary", index=False, startrow=1)
        top10.to_excel(xw, sheet_name="Summary", index=False, startrow=len(summ) + 4)
        for tab, frame in tabs.items():
            frame.to_excel(xw, sheet_name=sheet_name(tab), index=False)
        contacts_out.to_excel(xw, sheet_name="Contacts", index=False)
        method.to_excel(xw, sheet_name="Method", index=False)
        table_of_rules(t).to_excel(xw, sheet_name="Rules", index=False)
        if len(sources):
            sources.to_excel(xw, sheet_name="Sources", index=False)
        _style(xw, len(summ))
    csv_dir = p.out / "csv"
    csv_dir.mkdir(exist_ok=True)
    for tab, frame in list(tabs.items()) + [("contacts", contacts_out), ("summary", summ), ("method", method)]:
        frame.to_csv(csv_dir / f"{file_name(tab)}.csv", index=False)

    _clay(p, a, contacts, assoc)
    _call_sheet(p, acct)
    _alert_points(p, leads, a)
    print(summ.to_string(index=False))
    log(f"wrote {xlsx.relative_to(p.dir)}, csv/, clay/, call_sheet_top50.md, alert_points.csv")


def _style(xw, n_summary):
    from openpyxl.styles import Alignment, Font, PatternFill
    head = PatternFill("solid", fgColor="DCE8DC")
    wb = xw.book
    wb["Summary"].cell(row=1, column=1, value="Accounts by segment").font = Font(bold=True, size=13)
    wb["Summary"].cell(row=n_summary + 4, column=1, value="Top 10 accounts").font = Font(bold=True, size=13)
    for ws in wb.worksheets:
        hdr = [2, n_summary + 5] if ws.title == "Summary" else [1]
        for r in hdr:
            for cell in ws[r]:
                if cell.value is not None:
                    cell.font, cell.fill = Font(bold=True), head
        if ws.title != "Summary":
            ws.freeze_panes = "C2"
            ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            header = str(col[hdr[0] - 1].value or "")
            width = max(len(str(cell.value or "")) for cell in col[:300])
            ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 45)
            if header in ("outreach_angle", "detail", "when"):
                ws.column_dimensions[col[0].column_letter].width = 90
                for cell in col:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")


def _clay(p, a, contacts, assoc):
    out = p.out / "clay"
    out.mkdir(exist_ok=True)
    dom = (contacts[contacts["business_email"].str.contains("@")]
           .assign(d=lambda x: x["business_email"].str.split("@").str[1].str.lower())
           .groupby("account_id")["d"].agg(lambda x: x.mode().iat[0]))
    web = a["firm_website"].fillna("").str.replace(r"^https?://(www\.)?", "", regex=True).str.split("/").str[0]
    comp = pd.DataFrame({
        "account_id": a["account_id"], "company_name": a["account"], "company_name_for_enrichment": a["account"].map(search_name),
        "domain": web.where(web != "", a["account_id"].map(dom)).fillna(""),
        "segment": a["segment_label"], "tier": a["tier"], "score": a["score"], "outreach_angle": a["outreach_angle"],
        "properties": a["properties"], "total_acres": a["total_acres"].round(1), "canopy_acres": a["canopy_acres"].round(1),
        "storm_exposure_0_100": a["storm_exposure_0_100"], "top_site": a["site_name"], "site_city": a["site_city"],
        "site_zip": a["site_zip"], "mailing_address": a["mailing_address"], "lat": a["lat"], "lon": a["lon"],
        "contacts_found": a["contacts_found"], "src_buyer": a["src_buyer"]})
    comp.to_csv(out / "clay_companies.csv", index=False)
    comp[comp["tier"].isin(["A", "B"])].to_csv(out / "clay_companies_tier_AB.csv", index=False)
    people = contacts[contacts["contact_type"].str.lower().str.startswith("person")].copy()
    if len(people):
        nm = people["name"].str.replace(r",.*$|\(.*?\)", "", regex=True).str.strip().str.split()
        people["first_name"], people["last_name"] = nm.str[0].fillna(""), nm.str[-1].fillna("")
        people.insert(0, "person_id", [f"P{i:05d}" for i in range(1, len(people) + 1)])
    people.to_csv(out / "clay_people.csv", index=False)
    if len(assoc):
        assoc.insert(0, "community_id", [f"H{i:05d}" for i in range(1, len(assoc) + 1)])
        assoc.rename(columns={"account_id": "management_account_id"}).to_csv(out / "clay_communities.csv", index=False)


def _call_sheet(p, acct, n=50):
    lines = [f"# First {n} calls: {p.name}", "",
             f"Built {date.today().isoformat()}. Ranked by score. Business contacts only; confirm any 'low' confidence link on the call.", ""]
    for i, r in enumerate(acct.head(n).itertuples(), 1):
        who = (f"{r.best_contact}, {r.best_contact_title}" if isinstance(r.best_contact, str) and r.best_contact
               else "No contact yet: research the company's site or main line")
        lines += [f"## {i}. {r.account} ({r.tier}, {r.score})", "",
                  f"- **Segment:** {r.segment_label} · {r.properties} {'property' if r.properties == 1 else 'properties'} · {r.total_acres:,.0f} acres · "
                  f"{(r.canopy_acres if pd.notna(r.canopy_acres) else 0):,.0f} canopy acres",
                  f"- **Who:** {who}",
                  f"- **Reach:** {' · '.join(v for v in (r.best_contact_email, r.best_contact_phone) if v) or '—'}",
                  f"- **Angle:** {r.outreach_angle}", ""]
    (p.out / f"call_sheet_top{n}.md").write_text("\n".join(lines))


def _alert_points(p, leads, a):
    pts = (leads.dropna(subset=["lat"]).sort_values("acreage", ascending=False)
           .drop_duplicates(["account", "property_key"]))
    pts = pts.merge(a[["account", "account_id", "score", "tier", "segment_label", "best_contact", "best_contact_title",
                       "best_contact_email", "best_contact_phone"]], on="account", how="left")
    pts["site_name"] = pts["site"].map(nice)
    pts = pts.rename(columns={"site_addr": "site_street", "acreage": "acres"})
    cols = ["account_id", "account", "segment_label", "score", "tier", "site_name", "site_street", "site_city", "acres",
            "lat", "lon", "best_contact", "best_contact_title", "best_contact_email", "best_contact_phone"]
    pts[cols].to_csv(p.out / "alert_points.csv", index=False)
