"""Step 4: keep parcels with real grounds, then roll each one up to the company that buys the work.

The parcel owner is often not who hires the contractor. Each parcel's buyer is the first of:
  1. a district segment (e.g. MUDs): the district itself, which buys by board vote / bids
  2. the operator named on a state licensed-facility list (e.g. senior living)
  3. a verified firm from firm_aliases.csv, matched to the care-of name, mailing address or owner
  4. the parcel's own care-of business name ("C/O", "%", "ATTN")
  5. the firm most often named care-of at that mailing address across the whole county
     (the address must serve 3+ distinct owners and the firm 30%+ of its accounts)
  6. an owner group: 2+ distinct lead owners sharing one mailing address
  7. the owner itself
Care-of names that look like people (board members, officers) are never kept.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .project import log

# Generic English / US patterns. county.yaml can add local names via keyword_additions
# (e.g. TAX_AGENT: the property-tax consultants common in that state).
ABBR = [(r"\bDEPT\s*\d+\b|\bDEPT\b|\bDEPARTMENT\b", " "),
        (r"\bMGMT\b|\bMNGMT\b|\bMGMNT\b|\bMGT\b|\bMANAGMENT\b|\bMANAGEMNT\b|\bMANAGEMEN\b|\bMGNT\b", "MANAGEMENT"),
        (r"\bASSOC\b|\bASSN\b|\bASSC\b", "ASSOCIATION"),
        (r"\bCO\b", "COMPANY"), (r"\bSVCS?\b", "SERVICES"), (r"\bPROP\b|\bPROPS\b", "PROPERTIES"),
        (r"\bGRP\b", "GROUP"), (r"&", " AND ")]
SUFFIX = r"\b(INC|LLC|L L C|LP|L P|LTD|CORP|CORPORATION|PLLC|PC|THE)\b"
GENERIC_CO = re.compile(r"^(REAL ESTATE|PROPERTY|PROPERTIES|LEGAL|FINANCE|ACCOUNTING|TAX|CORPORATE|ADMINISTRATION|"
                        r"OWNER|MANAGER|MANAGEMENT|MANAGING AGENT|GENERAL PARTNER|GP|AGENT|OFFICE)( (DIVISION|SERVICES))?$")
BUSINESS = (r"MANAGEMENT|PROPERT|REALTY|REAL ESTATE|GROUP|COMPANY|SERVICES|PARTNERS|CAPITAL|RESIDENTIAL|LIVING|"
            r"ADVISOR|ASSET|INVEST|HOLDINGS|ASSOCIA|FIRSTSERVICE|TRUST|FUND|EQUIT|DEVELOP|COMMUNIT|HOSPITALITY|"
            r"HEALTH|SENIOR|CARE|\bINC\b|\bLLC\b|\bLP\b|\bLTD\b|\bCORP|\bCOMPANY\b|\bCO\b|TAX|ACCOUNT|\bLAW\b|"
            r"ATTORNEY|\bPC\b|\bPLLC\b|ENGINEER|CONSULT|BANK")
PERSON_ROLE = re.compile(r"TREASURER|PRESIDENT|SECRETARY|DIRECTOR|BOARD|OFFICER|\bPRES\b|\bTREAS\b|\bVP\b|CHAIR|"
                         r"MEMBER|TRUSTEE")
# Tax consultants and payables departments appear as care-of on many accounts but don't buy field work
TAX_AGENT = (r"\bTAX\b|PROPERTY TAX|PROTEST|APPRAISAL|ASSESSMENT|ACCOUNTING|ACCOUNTS PAYABLE|\bAP\b|PAYABLE|"
             r"\bLEASE ADMIN|\bREAL ESTATE TAX")
MGR_WORDS = re.compile(r"MANAGEMENT|ASSOCIA|FIRSTSERVICE|PROPERT|REALTY|COMMUNITY|\bCMA\b|\bAMG\b|SERVICES|ADMIN|"
                       r"PARTNERS|GROUP|\bPMG\b|CONSULT")
ASSOC_WORDS = (r"\b(HOMEOWNERS?|HOMEOWNERSHIP|HOME OWNERS?|HOA|POA|ASSOCIATIONS?|ASSOCIATON|ASSOC|ASSN|ASSC|ASS|IN|INC|"
               r"COMMUNITY|COMM|PROPERTY|PROPERTIES|OWNERS?|MASTER|RESIDENTIAL|MAINTENANCE|MAINT|CIVIC|CLUB|OF|THE|"
               r"AND|PHASE|PH|SECTION|SEC|II|III|IV|I|NO|\d+)\b")
STREET_SUFFIX = {"DR", "DRIVE", "ST", "STREET", "RD", "ROAD", "AVE", "AVENUE", "BLVD", "LN", "LANE", "PKWY", "PKY",
                 "CT", "PL", "WAY", "CIR", "TRL", "HWY", "FWY", "FRWY", "LOOP"}
MANAGED_TYPES = {"Care-of firm on mailing", "Firm at shared mailing address"}


def assoc_key(name):
    """Core of an association name, so 'GREEN TRLS HOA PHASE II' and 'GREEN TRAILS ASSN' match."""
    if not isinstance(name, str):
        return ""
    s = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    for a, b in [(r"\bTRLS?\b", "TRAILS"), (r"\bCRK\b", "CREEK"), (r"\bVLG\b", "VILLAGE"), (r"\bEST\b", "ESTATES"),
                 (r"\bLKS?\b", "LAKES")]:
        s = re.sub(a, b, s)
    core = re.sub(r"\s+", " ", re.sub(ASSOC_WORDS, " ", s)).strip()
    return core or re.sub(r"\s+", " ", s).strip()


def canon(name):
    if not isinstance(name, str) or not name.strip():
        return ""
    s = name.upper()
    for pat, rep in ABBR:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(SUFFIX, " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\b(MANAGEMENT|ASSOCIATION MANAGEMENT)( (COMPANY|SERVICES|SERVICE))+$", r"\1", s)
    return "" if GENERIC_CO.match(s) else s


def care_of(mailto):
    if not isinstance(mailto, str):
        return ""
    m = re.search(r"(?:C/O|C / O|%|ATTN:?)\s*(.+)$", mailto.upper())
    return m.group(1).strip() if m else ""


def strip_street_suffix(s):
    toks = s.split()
    while len(toks) > 2 and toks[-1] in STREET_SUFFIX:
        toks.pop()
    return " ".join(toks)


def addr_key(a1, zip_):
    if not isinstance(a1, str) or not a1.strip() or "ADDRESS UNKNOWN" in a1.upper():
        return ""
    s = a1.upper()
    s = re.sub(r"\b(STE|SUITE|UNIT|APT|BLDG|FL|FLR|FLOOR|RM|ROOM|SITE)\b\.?\s*[#A-Z0-9-]*", " ", s)
    s = re.sub(r"\bSTE\d+\w*\b", " ", s)
    s = re.sub(r"#\s*[A-Z0-9-]+", " ", s)
    s = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return f"{strip_street_suffix(s)} | {str(zip_)[:5]}"


def looks_residential(a1, a2):
    s = f"{a1} {a2}".upper()
    return not re.search(r"P ?O BOX|\bBOX\b|\bSTE\b|SUITE|#|\bFL(OO)?R?\b|\bUNIT\b|PMB|\bBLDG\b", s)


def load_aliases(path):
    """firm_aliases.csv: match_type (care_of|address|owner), pattern (regex), firm, firm_type,
    website, verified_source. Address patterns look like '^123 MAIN \\| 77001'."""
    if not Path(path).exists():
        return [], {}
    al = pd.read_csv(path, dtype=str, comment="#").fillna("")
    rules = []
    for _, a in al.iterrows():
        pat = a["pattern"]
        if not pat:
            continue
        if a["match_type"] == "address" and r" \|" in pat:
            street, rest = pat.split(r" \|", 1)
            pat = "^" + strip_street_suffix(street.lstrip("^")) + r" \|" + rest
        rules.append((a["match_type"], re.compile(pat), a["firm"], a["firm_type"], a["verified_source"]))
    return rules, dict(zip(al["firm"], al["website"]))


def rollup(p):
    t, c = p.trade, p.county
    b = t.get("buyer", {})
    filt = t.get("filters", {})
    min_acres = float(filt.get("min_acres", 1.0))
    kw_add = c.get("keyword_additions") or {}
    business = re.compile(BUSINESS + (f"|{kw_add['BUSINESS']}" if kw_add.get("BUSINESS") else ""))
    tax_agent = re.compile(TAX_AGENT + (f"|{kw_add['TAX_AGENT']}" if kw_add.get("TAX_AGENT") else ""))
    roll_src = c.get("roll_source", f"{c.get('name', 'County')} appraisal roll")
    mail_src = f"{roll_src}: mailing address / care-of line"

    allp = pd.read_parquet(p.work / "classified.parquet")
    can = pd.read_parquet(p.work / "canopy.parquet")
    seg = allp[allp["segment"].notna()].merge(can, on="parcel_id", how="left")
    seg["canopy_acres_est"] = (seg["acreage"] * seg["canopy_pct"] / 100).round(2)

    # ------------------------------------------------------------- filters
    grouped = set(b.get("group_segments", []))
    seg["assoc_key"] = ""
    if grouped:
        g = seg["segment"].isin(grouped)
        zip5 = (seg[g].sort_values("acreage", ascending=False).drop_duplicates("owner_name")
                .set_index("owner_name")["site_zip"].astype(str).str[:5])
        okey = {o: f"{assoc_key(o)} | {zip5.get(o, '')}" for o in seg.loc[g, "owner_name"].unique()}
        seg.loc[g, "assoc_key"] = seg.loc[g, "owner_name"].map(okey)
    floor_segs = set(filt.get("aggregate_floor_segments", []))
    group_acres = seg.groupby("assoc_key")["acreage"].transform("sum")
    keep = seg["acreage"] >= min_acres
    keep |= seg["segment"].isin(floor_segs) & (seg["assoc_key"] != "") & (group_acres >= min_acres)
    for ef in filt.get("extra", []):
        hit = seg["subtype"] == ef["subtype"]
        ok = (seg["acreage"] >= ef.get("min_acres", 0)) & (seg["canopy_pct"].fillna(0) >= ef.get("min_canopy_pct", 0))
        keep &= ~hit | ok
    leads = seg[keep].copy()
    leads["filter_note"] = np.where(leads["acreage"] < min_acres, f"parcel under {min_acres:g} ac kept: its association totals {min_acres:g}+ ac", "")
    log(f"{len(seg):,} segment parcels -> {len(leads):,} with {min_acres:g}+ acres of grounds")

    # ------------------------------------------- address -> firm, county-wide
    allp["addr_key"] = [addr_key(a, z) for a, z in zip(allp["mail_addr_1"], allp["mail_zip"])]
    allp["co"] = allp["mailto"].map(care_of)
    allp["co_canon"] = allp["co"].map(canon)
    allp["owner_canon"] = allp["mailto"].fillna("").str.replace(r"(C/O|%|ATTN).*$", "", regex=True).map(canon)
    co_ok = ((allp["co_canon"] != "") & allp["co"].str.contains(business) & ~allp["co"].str.contains(PERSON_ROLE)
             & ~allp["co"].str.contains(tax_agent))
    af = (allp[co_ok & (allp["addr_key"] != "")].groupby(["addr_key", "co_canon"]).size().rename("n").reset_index()
          .sort_values("n", ascending=False).drop_duplicates("addr_key"))
    addr_owners = allp[allp["addr_key"] != ""].groupby("addr_key")["owner_canon"].nunique().rename("owners")
    addr_accts = allp[allp["addr_key"] != ""].groupby("addr_key").size().rename("accounts")
    af = af.merge(addr_owners, on="addr_key").merge(addr_accts, on="addr_key")
    af = af[(af["n"] >= 3) & (af["owners"] >= 3) & (af["n"] / af["accounts"] >= 0.3)]
    addr_firm = dict(zip(af["addr_key"], af["co_canon"]))

    aliases, websites = load_aliases(p.dir / "firm_aliases.csv")
    log(f"firm aliases: {len(aliases)} rules | shared-address firms found: {len(addr_firm):,}")

    # --------------------------------------------------------- assign buyers
    leads["care_of_raw"] = leads["mailto"].map(care_of)
    leads["care_of_canon"] = leads["care_of_raw"].map(canon)
    leads["addr_key"] = [addr_key(a, z) for a, z in zip(leads["mail_addr_1"], leads["mail_zip"])]
    leads["owner_canon"] = leads["owner_name"].map(canon)
    lead_addr_owners = leads[leads["addr_key"] != ""].groupby("addr_key")["owner_canon"].nunique()
    district = set(b.get("district_segments", []))
    facility = set(b.get("facility_segments", []))

    def assign(r):
        co, co_raw = r["care_of_canon"], r["care_of_raw"]
        person_co = bool(co_raw) and (bool(PERSON_ROLE.search(co_raw)) or not business.search(co_raw))
        tax_co = bool(co_raw) and bool(tax_agent.search(co_raw))
        if r["segment"] in district:
            return r["owner_canon"], "District (board vote / bids)", f"{roll_src}: owner name", "high"
        op = r.get("facility_operator")
        if r["segment"] in facility and isinstance(op, str) and op.strip():
            return canon(op) or op, "Operator / management company", r.get("src_facility") or "licensed facility list", "high"
        targets = {"care_of": co, "address": r["addr_key"], "owner": r["owner_canon"]}
        for mtype, pat, firm, ftype, src in aliases:
            if targets.get(mtype) and pat.search(targets[mtype]):
                return firm, ftype or "Verified firm", f"firm_aliases.csv: {src}", "high"
        if co and not person_co and not tax_co:
            return co, "Care-of firm on mailing", mail_src, "medium"
        if r["addr_key"] in addr_firm:
            return addr_firm[r["addr_key"]], "Firm at shared mailing address", f"{roll_src}: most common care-of firm at this mailing address", "medium"
        if r["addr_key"] and lead_addr_owners.get(r["addr_key"], 0) >= 2:
            return f"OWNER GROUP @ {r['addr_key']}", "Owner group (shared mailing address)", f"{roll_src}: 2+ owners share this mailing address", "low"
        return r["owner_canon"] or r["owner_name"], "Owner (no manager found)", f"{roll_src}: owner name", "low"

    recs = leads.to_dict("records")
    BC = ["buyer", "buyer_type", "src_buyer", "buyer_confidence"]
    leads[BC] = pd.DataFrame([assign(r) for r in recs], index=leads.index)
    # care-of / address-derived names take the verified spelling when an alias matches
    derived = leads["buyer_type"].isin(MANAGED_TYPES)
    for mtype, pat, firm, ftype, src in aliases:
        if mtype == "care_of":
            hit = derived & leads["buyer"].str.contains(pat)
            leads.loc[hit, BC] = [firm, ftype or "Verified firm", f"firm_aliases.csv: {src}", "high"]
            derived &= ~hit

    # districts: note the consultant / operator firm on the mailing line
    is_d = leads["segment"].isin(district)
    leads["district_consultant"] = ""
    leads.loc[is_d, "district_consultant"] = [
        r["care_of_canon"] if r["care_of_canon"] and business.search(r["care_of_raw"]) and not PERSON_ROLE.search(r["care_of_raw"])
        else addr_firm.get(r["addr_key"], "") for r in leads[is_d].to_dict("records")]

    grp = leads["buyer"].str.startswith("OWNER GROUP @")
    if grp.any():
        top = (leads[grp].groupby(["buyer", "owner_canon"])["acreage"].sum().reset_index()
               .sort_values("acreage", ascending=False).drop_duplicates("buyer"))
        n_ent = leads[grp].groupby("buyer")["owner_canon"].nunique()
        label = {bb: f"{o} GROUP (+{n_ent[bb] - 1} related entities)" for bb, o in zip(top["buyer"], top["owner_canon"])}
        leads.loc[grp, "buyer"] = leads.loc[grp, "buyer"].map(label)

    person = leads["care_of_raw"].ne("") & (leads["care_of_raw"].str.contains(PERSON_ROLE)
                                            | ~leads["care_of_raw"].str.contains(business))
    leads.loc[person, "care_of_raw"] = "[individual – omitted]"
    leads.loc[person, "care_of_canon"] = ""

    # ----------------------------------------------------- managed / self split
    leads["segment_final"] = leads["segment"]
    leads["property_key"] = leads["owner_canon"]
    ms = b.get("managed_split")
    if ms:
        is_g = leads["segment"] == ms["segment"]
        mgr = leads["buyer_type"].isin(MANAGED_TYPES) & leads["buyer"].str.contains(MGR_WORDS)
        mgr |= leads["src_buyer"].str.startswith("firm_aliases") & leads["buyer_type"].str.contains("management", case=False)
        office_ct = leads[is_g].groupby("addr_key")["assoc_key"].nunique()
        shared = (leads["addr_key"].map(office_ct).fillna(0) >= ms.get("shared_office_min", 5)) & (leads["addr_key"] != "")
        leads.loc[is_g & (mgr | shared), "segment_final"] = ms["managed"]
        leads.loc[is_g & ~(mgr | shared), "segment_final"] = ms["self"]
        unnamed = is_g & shared & ~mgr
        leads.loc[unnamed, "buyer"] = "UNNAMED MANAGER @ " + leads.loc[unnamed, "addr_key"]
        leads.loc[unnamed, "buyer_type"] = "Management company (name pending)"
        leads.loc[unnamed, "src_buyer"] = f"{roll_src}: mailing address shared by {ms.get('shared_office_min', 5)}+ associations"
        # one answer per association: the manager holding most of its acreage (named beats pending)
        m = leads[is_g & (leads["segment_final"] == ms["managed"])].copy()
        m["named"] = ~m["buyer"].str.startswith("UNNAMED")
        pick = (m.groupby(["assoc_key", "named"] + BC)["acreage"].sum().reset_index()
                .sort_values(["named", "acreage"], ascending=False).drop_duplicates("assoc_key").set_index("assoc_key")[BC])
        in_m = is_g & leads["assoc_key"].isin(pick.index)
        leads.loc[in_m, "segment_final"] = ms["managed"]
        leads.loc[in_m, BC] = pick.loc[leads.loc[in_m, "assoc_key"], BC].values
        named = m[m["named"]].groupby("assoc_key")["buyer"].agg(lambda x: sorted(set(x)))
        conflict = named[named.str.len() > 1]
        leads["manager_conflict"] = leads["assoc_key"].map(
            lambda k: "mailing lines show several managers: " + "; ".join(conflict[k]) if k in conflict.index else "")
    if grouped:
        g = leads["segment"].isin(grouped)
        name = (leads[g].groupby(["assoc_key", "owner_canon"])["acreage"].sum().reset_index()
                .sort_values("acreage", ascending=False).drop_duplicates("assoc_key").set_index("assoc_key")["owner_canon"])
        leads.loc[g, "property_key"] = leads.loc[g, "assoc_key"].map(name)
        leads.loc[g, "name_variants"] = leads.loc[g, "assoc_key"].map(
            leads[g].groupby("assoc_key")["owner_canon"].agg(lambda x: " | ".join(sorted(set(x)))))
    if ms:
        sm = leads["segment_final"] == ms["self"]
        leads.loc[sm, "buyer"] = leads.loc[sm, "property_key"]
        leads.loc[sm, ["buyer_type", "src_buyer", "buyer_confidence"]] = [
            "Self-managed association", f"{roll_src}: owner name", "medium"]

    # mailing address shown only when it isn't a likely home
    home = (leads["segment_final"] == (ms or {}).get("self")) & np.array(
        [looks_residential(a, bb) for a, bb in zip(leads["mail_addr_1"], leads["mail_addr_2"])])
    leads["mailing_address_public"] = (leads["mail_addr_1"].fillna("") + " " + leads["mail_addr_2"].fillna("") + ", "
                                       + leads["mail_city"].fillna("") + " " + leads["mail_state"].fillna("") + " "
                                       + leads["mail_zip"].fillna("")).str.replace(r"\s+", " ", regex=True).str.strip(" ,")
    leads.loc[home, "mailing_address_public"] = "[looks like a residence – omitted; use the association's website]"
    leads["src_mailing"] = np.where(home, "omitted by privacy rule", mail_src)
    leads["firm_website"] = leads["buyer"].map(websites).fillna("")
    leads.to_parquet(p.work / "leads.parquet", index=False)

    # ---------------------------------------------------------- checkpoint 2
    ck = p.out / "checkpoints"
    ck.mkdir(exist_ok=True)
    roll = (leads.groupby("buyer").agg(
        buyer_type=("buyer_type", lambda x: x.mode().iat[0]),
        segments=("segment_final", lambda x: "; ".join(f"{k} ({v})" for k, v in x.value_counts().items())),
        properties=("property_key", "nunique"), parcels=("parcel_id", "size"), acres=("acreage", "sum"),
        canopy_acres=("canopy_acres_est", "sum"), confidence=("buyer_confidence", lambda x: x.mode().iat[0]))
        .round(1).sort_values("acres", ascending=False))
    roll.head(300).to_csv(ck / "2_top_buyers_by_acres.csv")
    roll.sort_values("properties", ascending=False).head(300).to_csv(ck / "2_top_buyers_by_properties.csv")
    # firms worth verifying and adding to firm_aliases.csv
    cand = (leads[leads["buyer_type"].isin(MANAGED_TYPES | {"Management company (name pending)"})]
            .groupby(["buyer", "addr_key"]).agg(properties=("property_key", "nunique"), acres=("acreage", "sum"))
            .reset_index().sort_values("properties", ascending=False).head(150))
    cand.to_csv(ck / "2_firm_alias_candidates.csv", index=False)
    log("segments: " + ", ".join(f"{k} {v:,}" for k, v in leads["segment_final"].value_counts().items()))
    log(f"{leads['buyer'].nunique():,} buyers | checkpoint files in {ck}")
