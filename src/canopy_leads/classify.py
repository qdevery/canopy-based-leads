"""Steps 1 and 2: load the county roll into the standard parcel table, then put every parcel
in a segment with the trade's ordered rules (first match wins).

Rules never mention a county's own codes. county.yaml translates local codes into tags
(state class B1 -> multifamily, building type 4389 -> country_club_golf), and trade.yaml
writes its rules against tags and name keywords, so one trade works in any county.
"""
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from .adapters import ADAPTERS
from .project import log

OTHER = "_other"  # a code the county config does not tag


# ------------------------------------------------------------------ normalize
def normalize(p):
    adapter = p.county.get("adapter", "generic")
    if adapter not in ADAPTERS:
        raise SystemExit(f"Unknown adapter '{adapter}'. Available: {', '.join(ADAPTERS)}")
    df, geom = ADAPTERS[adapter](p)
    codes = p.county.get("codes", {})
    fams = [c[6:] for c in df if c.startswith("codes_")]
    tag_cols = []
    for fam in fams:
        table = {str(k): v for k, v in (codes.get(fam) or {}).items()}
        col = f"tags_{fam}"
        df[col] = df[f"codes_{fam}"].apply(lambda s: sorted({table.get(c, OTHER) for c in s}))
        df[f"codes_{fam}"] = df[f"codes_{fam}"].apply(lambda s: ",".join(sorted(s)))
        tag_cols.append(col)
    df["tags"] = df[tag_cols].apply(lambda r: sorted({t for ts in r for t in ts} - {OTHER}), axis=1)
    df.to_parquet(p.work / "parcels.parquet", index=False)
    geom[["parcel_id", "geometry"]].to_parquet(p.work / "parcels_geom.parquet", index=False)
    tagged = (df["tags"].str.len() > 0).mean()
    log(f"normalized {len(df):,} parcels ({tagged:.0%} carry at least one tag), {len(geom):,} polygons")


# --------------------------------------------------------------- rule engine
class Rules:
    def __init__(self, trade, county):
        kw = dict(trade.get("keywords", {}))
        for k, extra in (county.get("keyword_additions") or {}).items():
            kw[k] = f"(?:{kw[k]})|(?:{extra})" if k in kw else extra
        self.kw = {k: re.compile(v) for k, v in kw.items()}
        self.rules = trade["rules"]

    def _kw(self, key, text):
        if key not in self.kw:
            raise SystemExit(f"trade.yaml rule uses keyword '{key}' that is not defined under keywords:")
        return bool(self.kw[key].search(text))

    def test(self, cond, p, ev):
        """True when every condition in `cond` holds for parcel p; appends evidence."""
        for key, val in cond.items():
            vals = val if isinstance(val, list) else [val]
            if key == "keyword":
                hit = [k for k in vals if self._kw(k, p["names"])]
                if not hit:
                    return False
                ev.append("name:" + "/".join(hit))
            elif key == "owner_keyword":
                hit = [k for k in vals if self._kw(k, p["owner_name"])]
                if not hit:
                    return False
                ev.append("owner name:" + "/".join(hit))
            elif key == "not_keyword":
                if any(self._kw(k, p["names"]) for k in vals):
                    return False
            elif key == "not_owner_keyword":
                if any(self._kw(k, p["owner_name"]) for k in vals):
                    return False
            elif key == "tag":
                hit = [t for t in vals if t in p["tags"]]
                if not hit:
                    return False
                ev.append("code:" + "/".join(hit))
            elif key == "not_tag":
                if any(t in p["tags"] for t in vals):
                    return False
            elif key == "only":  # {family: land_use, tags: [...]}: every code of that family is one of these
                fam_tags = p.get(f"tags_{val['family']}", [])
                if not fam_tags or not set(fam_tags) <= set(val["tags"]):
                    return False
                ev.append(f"{val['family']} only:" + "/".join(fam_tags))
            elif key == "any_of":
                for sub in vals:
                    sub_ev = []
                    if self.test(sub, p, sub_ev):
                        ev.extend(sub_ev)
                        break
                else:
                    return False
            elif key == "none_of":
                if any(self.test(sub, p, []) for sub in vals):
                    return False
            else:
                raise SystemExit(f"trade.yaml: unknown rule condition '{key}'")
        return True

    def classify(self, p):
        for rule in self.rules:
            ev = []
            if self.test(rule.get("when", {}), p, ev):
                conf = rule.get("confidence", "high")
                seg = rule.get("segment")
                return seg, rule.get("subtype", ""), "; ".join(ev), conf if seg else rule.get("confidence", "excluded")
        return None, "Not a target segment", "", "excluded"


def table_of_rules(trade):
    """One row per rule, for the workbook's Rules tab."""
    rows = []
    for i, r in enumerate(trade["rules"], 1):
        rows.append({"order": i, "segment": r.get("segment") or "(excluded)", "subtype": r.get("subtype", ""),
                     "confidence": r.get("confidence", "high"), "when": str(r.get("when", {}))})
    return pd.DataFrame(rows)


# ------------------------------------------------------- licensed facilities
def licensed_facilities(p, df):
    """Optional state lists of licensed facilities (e.g. Texas HHSC assisted living and nursing
    facilities). A facility inside a parcel confirms or assigns the facility's segment and
    names its operator, who is usually the buyer."""
    cfg = p.county.get("licensed_facilities")
    if not cfg:
        return df
    frames = []
    for f in cfg["files"]:
        path = p.raw / f["path"]
        if not path.exists():
            log(f"licensed facilities: {path.name} not found, skipped (run canopy-leads fetch)")
            continue
        if path.suffix.lower() in (".xlsx", ".xls"):
            x = pd.read_excel(path, header=f.get("header_row", 0), dtype=str)
        else:
            x = pd.read_csv(path, dtype=str, keep_default_na=False)
        x.columns = [str(c).strip().rstrip("_") for c in x.columns]
        for col, want in (f.get("filters") or {}).items():
            x = x[x[col].astype(str).str.strip().str.upper() == str(want).upper()]
        frames.append(x)
    if not frames:
        return df
    hh = pd.concat(frames, ignore_index=True)
    c = cfg["columns"]
    if "latlon" in c:
        ll = hh[c["latlon"]].astype(str).str.split(",", expand=True)
        hh["lat"], hh["lon"] = pd.to_numeric(ll[0], errors="coerce"), pd.to_numeric(ll[1], errors="coerce")
    else:
        hh["lat"], hh["lon"] = pd.to_numeric(hh[c["lat"]], errors="coerce"), pd.to_numeric(hh[c["lon"]], errors="coerce")
    hh = hh.dropna(subset=["lat", "lon"])
    geom = gpd.read_parquet(p.work / "parcels_geom.parquet")
    pts = gpd.GeoDataFrame(hh, geometry=gpd.points_from_xy(hh["lon"], hh["lat"]), crs=4326).to_crs(geom.crs)
    j = gpd.sjoin(pts, geom, how="inner", predicate="within").drop_duplicates(subset=[c["name"], "parcel_id"])
    by = j.groupby("parcel_id").agg(
        facility_name=(c["name"], lambda x: " | ".join(map(str, x))),
        facility_operator=(c["operator"], "first") if c.get("operator") in j else (c["name"], lambda x: ""),
        facility_phone=(c["phone"], "first") if c.get("phone") in j else (c["name"], lambda x: ""))
    df = df.join(by, on="parcel_id")
    seg = cfg.get("segment")
    hit = df["facility_name"].notna()
    excluded_public = df["subtype"].str.startswith("Public", na=False)
    keep_seg = df["segment"].isin(cfg.get("keep_segments", []))
    moved = hit & (df["segment"] != seg) & ~keep_seg & ~excluded_public
    df.loc[hit & (df["segment"] == seg), "evidence"] += " + licensed facility at parcel"
    df.loc[moved, "evidence"] = "licensed facility at parcel (was: " + df.loc[moved, "segment"].fillna(df.loc[moved, "subtype"]) + ")"
    df.loc[moved, ["segment", "subtype", "confidence"]] = [seg, "Licensed facility", "high"]
    df["src_facility"] = np.where(hit, cfg.get("source", "state licensed facility list"), "")
    log(f"licensed facilities: {len(hh):,} listed, {int(hit.sum()):,} parcels matched, {int(moved.sum()):,} moved into {seg}")
    return df


# ------------------------------------------------------------------- classify
def classify(p):
    df = pd.read_parquet(p.work / "parcels.parquet")
    for col in [c for c in df if c.startswith("tags")]:
        df[col] = df[col].apply(list)
    df["names"] = (df["owner_names_all"].fillna("") + " | " + df["mailto"].fillna("") + " | "
                   + df["property_name"].fillna("")).str.upper()
    rules = Rules(p.trade, p.county)
    cols = ["names", "owner_name"] + [c for c in df if c.startswith("tags")]
    recs = df[cols].to_dict("records")
    for r in recs:
        r["tags"] = set(r["tags"])
    log(f"classifying {len(recs):,} parcels …")
    res = [rules.classify(r) for r in recs]
    df[["segment", "subtype", "evidence", "confidence"]] = pd.DataFrame(res, index=df.index)
    df = licensed_facilities(p, df)
    for col in [c for c in df if c.startswith("tags")]:
        df[col] = df[col].apply(lambda v: ",".join(v))
    df = df.drop(columns="names")
    df.to_parquet(p.work / "classified.parquet", index=False)

    # checkpoint: counts and samples to review before going further
    ck = p.out / "checkpoints"
    ck.mkdir(exist_ok=True)
    counts = (df.assign(segment=df["segment"].fillna("(not a lead)"))
              .groupby(["segment", "subtype", "confidence"]).size().rename("parcels").reset_index()
              .sort_values(["segment", "parcels"], ascending=[True, False]))
    counts.to_csv(ck / "1_classification_counts.csv", index=False)
    show = ["parcel_id", "segment", "subtype", "confidence", "evidence", "owner_name", "mailto", "property_name",
            "acreage", "site_addr", "site_city", "tags"]
    seg = df[df["segment"].notna()]
    sample = seg.sample(frac=1, random_state=1).groupby("segment").head(25).sort_values("segment")[show]
    sample.to_csv(ck / "1_samples_by_segment.csv", index=False)
    unc = df[df["confidence"] == "uncertain"]
    unc.sort_values("acreage", ascending=False).head(200)[show].to_csv(ck / "1_uncertain_top200.csv", index=False)
    log("segments: " + ", ".join(f"{k} {v:,}" for k, v in seg["segment"].value_counts().items()))
    log(f"checkpoint files in {ck} — review the samples before continuing")
