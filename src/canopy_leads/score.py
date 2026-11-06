"""Step 6: one row per buyer account, a 0-100 score, a tier and a one-sentence outreach angle.

Default (tree care):  acreage 25 + canopy 20 + properties per buyer 15 + segment fit 20 + storm 20
Every weight, cap and tier cut lives in trade.yaml under `score:`. Set a part's points to 0 to
drop it (a paving trade has no use for canopy).
"""
import re

import numpy as np
import pandas as pd

from .project import log, slug

ACRONYMS = ["MUD", "WCID", "FWSD", "HOA", "POA", "LLC", "LP", "ISD", "II", "III", "IV", "UMC", "PUD", "USA", "TX",
            "LLP", "PLLC", "REIT", "YMCA", "YWCA", "PC", "CCRC"]


def nice(s, keep_group=False):
    """'GREEN TRAILS COMMUNITY ASSN' -> 'Green Trails Community Assn' (acronyms kept)."""
    m = re.search(r" GROUP \(\+\d+ related entit(y|ies)\)$", str(s))
    if m:
        return nice(str(s)[:m.start()]) + (str(s)[m.start():].replace(" GROUP", " group") if keep_group else "")
    s = str(s)
    if s != s.upper():
        return s
    s = s.title()
    for a in ACRONYMS:
        s = re.sub(rf"\b{a.title()}\b", a, s)
    s = re.sub(r"\b(\w*\d\w*)\b", lambda m: m.group(0).upper(), s)
    return s.replace("'S ", "'s ")


def logcap(x, cap):
    return np.clip(np.log1p(np.maximum(x, 0)) / np.log1p(cap), 0, 1)


PERSON = (r"^[A-Z'\-]+ [A-Z'\-]+( [A-Z'\-]+)? [A-Z]$|\bET (UX|VIR|AL)$|^ESTATE OF |\bESTATE$"
          r"|^[A-Z'\-]+ [A-Z'\-]+ [A-Z] (&|AND) [A-Z'\- ]+$|^[A-Z'\-]+ [A-Z'\-]+ (&|AND) [A-Z'\-]+( [A-Z])?$")


def storm_hook(r, events):
    """The most striking storm fact for this account, in words."""
    for ev in events:
        k = slug(ev["name"])
        if ev.get("method") == "nearest_report" and r.get(f"{k}_nearest_km", 99) <= ev.get("full_km", 2) + 1:
            return f"inside the {ev['name']} damage area"
    for ev in events:
        k = slug(ev["name"])
        g = r.get(f"{k}_gust_mph")
        if ev.get("method") == "gust_field" and pd.notna(g) and g >= ev.get("hook_mph", 75):
            return f"where {ev['name']} gusted to about {g:.0f} mph"
    for ev in events:
        k = slug(ev["name"])
        n = r.get(f"{k}_reports_10km")
        if ev.get("method") == "recent" and pd.notna(n) and n >= 3:
            return f"with {n:.0f} NWS wind or tornado damage reports within 10 km in the past year"
    named = [e["name"] for e in events if e.get("method") != "recent"]
    return f"in an area hit by {' and '.join(named)}" if named else "in a storm-prone area"


class SafeDict(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def score(p):
    t, c = p.trade, p.county
    leads = pd.read_parquet(p.work / "leads.parquet")
    storm = pd.read_parquet(p.work / "storms.parquet")
    leads = leads.merge(storm, on="parcel_id", how="left")
    events = c.get("storm_events", [])
    segs = p.segments()
    area = c.get("short_name", c.get("name", "county"))

    leads["w_storm"] = leads["storm_exposure"] * leads["acreage"]
    leads["canopy_area"] = leads["acreage"].where(leads["canopy_pct"].notna(), 0)
    leads["site"] = (leads["property_name"].fillna("").str.split(" | ", regex=False).str[0].str.strip()
                     .replace("", np.nan).fillna(leads["property_key"]).fillna(leads["site_addr"]))
    g = leads.groupby("buyer")
    feat = {
        "primary_segment": (leads.groupby(["buyer", "segment_final"])["acreage"].sum().reset_index()
                            .sort_values("acreage", ascending=False).drop_duplicates("buyer").set_index("buyer")["segment_final"]),
        "buyer_type": g["buyer_type"].agg(lambda x: x.mode().iat[0]),
        "properties": g["property_key"].nunique(), "parcels": g.size(),
        "total_acres": g["acreage"].sum(), "canopy_acres": g["canopy_acres_est"].sum(min_count=1),
        "canopy_area": g["canopy_area"].sum(), "storm_raw": g["w_storm"].sum() / g["acreage"].sum(),
        "confidence": g["buyer_confidence"].agg(lambda x: x.mode().iat[0]),
        "src_buyer": g["src_buyer"].agg(lambda x: x.mode().iat[0]),
        "owner_entities": g["property_key"].agg(lambda x: "; ".join(sorted(set(map(str, x)))[:8])),
        "segments_all": g["segment_final"].agg(lambda x: "; ".join(f"{k} ({v})" for k, v in x.value_counts().items())),
        "business_phone": g["facility_phone"].first() if "facility_phone" in leads else None,
        "district_consultant": g["district_consultant"].agg(lambda x: next((v for v in x if v), "")),
        "firm_website": g["firm_website"].agg(lambda x: next((v for v in x if v), "")),
        "src_storm": g["src_storm"].first(),
    }
    for col in [col for col in leads if re.search(r"_(gust_mph|reports_10km)$", col)]:
        feat[col] = g[col].max()
    for col in [col for col in leads if col.endswith("_nearest_km")]:
        feat[col] = g[col].min()
    a = pd.DataFrame({k: v for k, v in feat.items() if v is not None})
    big = leads.sort_values("acreage", ascending=False)
    top = big.drop_duplicates("buyer").set_index("buyer")
    a["site_name"] = top["site"].map(nice)
    a["site_street"] = top["site_addr"].fillna("").str.title()
    a["site_city"] = top["site_city"].fillna("").str.title()
    a["site_zip"] = top["site_zip"].fillna("").astype(str).str[:5]
    a["lat"], a["lon"] = top["lat"], top["lon"]
    a["mailing_address"] = top["mailing_address_public"]
    a["other_sites"] = (big.drop_duplicates(["buyer", "site"]).groupby("buyer")["site"]
                        .apply(lambda s: "; ".join(map(nice, s.iloc[1:6]))))
    a["canopy_pct"] = (100 * a["canopy_acres"] / a["canopy_area"].replace(0, np.nan)).round(1)

    # owners that look like private individuals: withhold the mailing address (may be a home)
    a["individual_owner"] = a["buyer_type"].str.startswith("Owner") & a.index.to_series().str.match(PERSON)
    a.loc[a["individual_owner"], "mailing_address"] = "[owner looks like an individual – withheld]"

    # ------------------------------------------------------------------- score
    sc = t.get("score", {})
    part = lambda k, d: {**d, **(sc.get(k) or {})}  # noqa: E731
    ac = part("acreage", {"points": 25, "full_at": 300})
    cp = part("canopy", {"points": 20, "full_acres": 60, "full_pct": 35, "acres_share": 0.6})
    pr = part("properties", {"points": 15, "full_at": 50})
    sf = part("segment_fit", {"points": 20})
    st = part("storm", {"points": 20})
    a["pts_acreage"] = ac["points"] * logcap(a["total_acres"], ac["full_at"])
    a["pts_canopy"] = cp["points"] * (cp["acres_share"] * logcap(a["canopy_acres"].fillna(0), cp["full_acres"])
                                      + (1 - cp["acres_share"]) * np.clip(a["canopy_pct"].fillna(0) / cp["full_pct"], 0, 1))
    a["pts_properties"] = pr["points"] * logcap(a["properties"] - 1, pr["full_at"] - 1)
    fit = {k: s.get("fit", 0.5) for k, s in segs.items()}
    a["pts_segment_fit"] = sf["points"] * a["primary_segment"].map(fit).fillna(0.5)
    a["storm_exposure_0_100"] = (100 * a["storm_raw"]).round(0)
    a["pts_storm"] = st["points"] * a["storm_raw"].fillna(a["storm_raw"].median()).fillna(0)
    pts = ["pts_acreage", "pts_canopy", "pts_properties", "pts_segment_fit", "pts_storm"]
    a["score"] = a[pts].sum(axis=1).round(0).astype(int)
    a[pts] = a[pts].round(1)
    tiers = t.get("tiers", {"A": 60, "B": 45})
    a["tier"] = np.where(a["score"] >= tiers["A"], "A", np.where(a["score"] >= tiers["B"], "B", "C"))

    # ------------------------------------------------------------------ angle
    def angle(r):
        s = segs.get(r["primary_segment"], {})
        n_props = int(r["properties"])
        name = "the owner" if r["individual_owner"] else re.sub(r"\s*\(.*?\)", "", nice(r.name)).strip()
        site = r["site_name"]
        if r["individual_owner"] or str(site).lower() in name.lower():
            site = f"{r['site_street']} in {r['site_city'] or area}".strip()
        unit = s.get("unit", "properties")
        fields = SafeDict(
            name=name, properties=n_props, acres=f"{r['total_acres']:.0f}",
            canopy_acres=f"{(r['canopy_acres'] if pd.notna(r['canopy_acres']) else 0):.0f}",
            storm_hook=storm_hook(r, events), area=area, site=site,
            sites=f"its {n_props} {area} {unit}" if n_props > 1 else site,
            operator=nice(r["district_consultant"]) if r["district_consultant"] else "its operator")
        tmpl = s.get("angle") or t.get("default_angle", "Offer {name} a site assessment for {sites} ({acres} acres, {storm_hook}).")
        return re.sub(r"\s+", " ", tmpl.format_map(fields)).strip()

    a["outreach_angle"] = a.apply(angle, axis=1)
    a["segment_label"] = a["primary_segment"].map(lambda s: p.label(s))
    a["src_score"] = "Computed: " + ", ".join(f"{k.replace('pts_', '')} {v['points']}" for k, v in
                                               zip(pts, [ac, cp, pr, sf, st])) + " (see Method tab)"
    a["src_angle"] = "Written from this row's fields with the segment's template in trade.yaml"
    a = a.reset_index().rename(columns={"buyer": "account"})
    a["account"] = a["account"].map(lambda v: nice(v, keep_group=True))
    a = a.sort_values(["score", "total_acres"], ascending=False)
    a.insert(0, "account_id", [f"A{i:05d}" for i in range(1, len(a) + 1)])
    a.to_parquet(p.work / "accounts.parquet", index=False)
    leads["account"] = leads["buyer"].map(lambda v: nice(v, keep_group=True))
    leads.to_parquet(p.work / "leads_scored.parquet", index=False)
    log(f"{len(a):,} accounts | tier A {int((a['tier'] == 'A').sum()):,}, B {int((a['tier'] == 'B').sum()):,}, "
        f"C {int((a['tier'] == 'C').sum()):,}")
