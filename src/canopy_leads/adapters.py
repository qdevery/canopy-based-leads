"""County adapters: read one appraisal district's files into the standard parcel table.

Every adapter returns (table, geometry):

table — one row per parcel/account with these columns (blank when the county lacks them):
    parcel_id, owner_name, owner_names_all, mailto, mail_addr_1, mail_addr_2, mail_city,
    mail_state, mail_zip, site_addr, site_city, site_zip, property_name, acreage,
    acreage_source, market_value, and one codes_<family> column per code family
    (a set of the parcel's raw codes, e.g. codes_state_class = {"B1"})
geometry — a GeoDataFrame of parcel_id + polygon, any CRS, possibly several rows per id

Add a county by writing county.yaml for the `generic` adapter (most counties publish one
parcel layer with owner and land-use attributes), or a new function here when the
district ships several linked tables, like Harris County's HCAD.
"""
import csv

import geopandas as gpd
import numpy as np
import pandas as pd

from .project import log

STANDARD = ["parcel_id", "owner_name", "owner_names_all", "mailto", "mail_addr_1", "mail_addr_2",
            "mail_city", "mail_state", "mail_zip", "site_addr", "site_city", "site_zip",
            "property_name", "acreage", "acreage_source", "market_value"]
EQUAL_AREA = 5070  # NAD83 / Conus Albers, for acreage from polygons
SQM_PER_ACRE = 4046.8564224


def _tab(path, usecols):
    return pd.read_csv(path, sep="\t", dtype=str, usecols=usecols, quoting=csv.QUOTE_NONE,
                       encoding="latin-1", on_bad_lines="skip", keep_default_na=False)


def _upper(s):
    return s.fillna("").astype(str).str.strip().str.upper()


def _code_set(series):
    return series.apply(lambda v: {str(v).strip()} if pd.notna(v) and str(v).strip() else set())


def polygon_acres(geom):
    """Acres per parcel_id from polygon area in an equal-area projection."""
    g = geom.to_crs(EQUAL_AREA)
    return (g.geometry.area / SQM_PER_ACRE).groupby(g["parcel_id"]).sum()


def reconcile_acreage(df, poly_acres, roll_label):
    """Use the roll's acreage unless it is missing or more than 2x the mapped polygon
    (a handful of records carry impossible acreage). Smaller-than-polygon acreage is kept,
    because one polygon can hold several accounts (condos, stacked parcels)."""
    df = df.join(poly_acres.rename("poly_acres"), on="parcel_id")
    ratio = df["acreage"] / df["poly_acres"]
    use_poly = df["poly_acres"].notna() & (df["acreage"].isna() | (df["acreage"] <= 0) | (ratio > 2))
    df["acreage"] = df["acreage"].where(~use_poly, df["poly_acres"]).round(4)
    df["acreage_source"] = np.where(use_poly, "parcel polygon area (roll acreage missing or >2x polygon)", roll_label)
    log(f"acreage: {int(use_poly.sum()):,} parcels use polygon area")
    return df.drop(columns="poly_acres")


# --------------------------------------------------------------------------- HCAD
def hcad(project):
    """Harris Central Appraisal District bulk files (download.hcad.org).
    raw/Real_acct_owner, raw/Real_building_land, raw/Parcels/Parcels.gdb"""
    raw = project.raw
    acct = _tab(raw / "Real_acct_owner/real_acct.txt", [
        "acct", "mailto", "mail_addr_1", "mail_addr_2", "mail_city", "mail_state", "mail_zip",
        "site_addr_1", "site_addr_2", "site_addr_3", "state_class", "land_ar", "acreage", "tot_mkt_val"])
    for c in acct.columns:
        acct[c] = acct[c].str.strip()
    acct["acreage"] = pd.to_numeric(acct["acreage"], errors="coerce")
    land_ar = pd.to_numeric(acct["land_ar"], errors="coerce")
    acct["acreage"] = acct["acreage"].where(acct["acreage"] > 0, land_ar / 43560)
    log(f"real_acct: {len(acct):,} accounts")

    own = _tab(raw / "Real_acct_owner/owners.txt", ["acct", "ln_num", "name", "aka"])
    own["acct"] = own["acct"].str.strip()
    own["name"], own["aka"] = _upper(own["name"]), _upper(own["aka"])
    own["ln_num"] = pd.to_numeric(own["ln_num"], errors="coerce")
    own = own.sort_values(["acct", "ln_num"])
    owner1 = own.groupby("acct")["name"].first().rename("owner_name")
    owners_all = (own.assign(n=(own["name"] + " " + own["aka"]).str.strip())
                  .groupby("acct")["n"].agg(" | ".join).rename("owner_names_all"))

    bo = _tab(raw / "Real_building_land/building_other.txt", ["acct", "impr_tp", "prop_nm"])
    for c in bo.columns:
        bo[c] = bo[c].str.strip()
    bt = bo.groupby("acct").agg(
        codes_building_type=("impr_tp", lambda x: {v for v in x if v}),
        property_name=("prop_nm", lambda x: " | ".join(sorted({v.upper() for v in x if v}))))

    ld = _tab(raw / "Real_building_land/land.txt", ["acct", "use_cd"])
    ld["acct"], ld["use_cd"] = ld["acct"].str.strip(), ld["use_cd"].str.strip()
    lu = ld.groupby("acct")["use_cd"].agg(lambda x: set(x) - {""}).rename("codes_land_use")
    log(f"owners {len(own):,} lines | buildings {len(bo):,} | land lines {len(ld):,}")

    df = acct.set_index("acct").join(owner1).join(owners_all).join(bt).join(lu).reset_index()
    df = df.rename(columns={"acct": "parcel_id", "site_addr_1": "site_addr", "site_addr_2": "site_city",
                            "site_addr_3": "site_zip", "tot_mkt_val": "market_value"})
    df["owner_name"] = df["owner_name"].fillna(_upper(df["mailto"]))
    df["owner_names_all"] = df["owner_names_all"].fillna(df["owner_name"])
    df["codes_state_class"] = _code_set(df["state_class"])
    for fam in ("codes_building_type", "codes_land_use"):
        df[fam] = df[fam].apply(lambda v: v if isinstance(v, set) else set())
    df["market_value"] = pd.to_numeric(df["market_value"], errors="coerce")

    geom = gpd.read_file(raw / "Parcels/Parcels.gdb", columns=["HCAD_NUM_1"], engine="pyogrio")
    geom = geom.rename(columns={"HCAD_NUM_1": "parcel_id"})
    geom["parcel_id"] = geom["parcel_id"].astype(str).str.strip()
    geom = geom[geom.geometry.notna()].copy()
    geom["geometry"] = geom.geometry.force_2d()
    log(f"parcel polygons: {len(geom):,}")
    df = reconcile_acreage(df, polygon_acres(geom), "HCAD real_acct acreage")
    return df, geom


# ------------------------------------------------------------------------ generic
def generic(project):
    """One parcel layer (shapefile, geodatabase, GeoPackage, GeoJSON) carrying owner and
    land-use attributes, optionally joined to a separate roll table. county.yaml:

    source:
      parcels: Parcels/parcels.shp      # path under raw/
      layer: null                       # for multi-layer files
      table: roll.csv                   # optional; csv, txt (set sep), xlsx or dbf
      table_sep: ","
      parcels_key: PARCEL_ID            # join keys when a table is used
      table_key: ACCOUNT
    columns:                            # standard name: source column
      parcel_id: PARCEL_ID
      owner_name: OWNER
      ...
    code_columns:                       # code family: source column (one code per parcel)
      state_class: STATE_CD
      land_use: LAND_USE
    """
    src, cols = project.county["source"], project.county["columns"]
    geo = gpd.read_file(project.raw / src["parcels"], layer=src.get("layer"), engine="pyogrio")
    log(f"parcel layer: {len(geo):,} features")
    if src.get("table"):
        path = project.raw / src["table"]
        if path.suffix.lower() in (".xlsx", ".xls"):
            tab = pd.read_excel(path, dtype=str)
        elif path.suffix.lower() == ".dbf":
            tab = pd.DataFrame(gpd.read_file(path, engine="pyogrio").drop(columns="geometry", errors="ignore"))
        else:
            tab = pd.read_csv(path, sep=src.get("table_sep", ","), dtype=str, keep_default_na=False,
                              encoding=src.get("encoding", "utf-8"), on_bad_lines="skip")
        geo[src["parcels_key"]] = geo[src["parcels_key"]].astype(str).str.strip()
        tab[src["table_key"]] = tab[src["table_key"]].astype(str).str.strip()
        attrs = pd.DataFrame(geo.drop(columns="geometry")).merge(
            tab, left_on=src["parcels_key"], right_on=src["table_key"], how="outer", suffixes=("", "_table"))
    else:
        attrs = pd.DataFrame(geo.drop(columns="geometry"))

    df = pd.DataFrame({std: attrs[col] if col in attrs else "" for std, col in cols.items()})
    for c in STANDARD:
        if c not in df:
            df[c] = ""
    df["parcel_id"] = df["parcel_id"].astype(str).str.strip()
    for c in ("owner_name", "owner_names_all", "mailto", "property_name"):
        df[c] = _upper(df[c])
    df["owner_names_all"] = df["owner_names_all"].where(df["owner_names_all"] != "", df["owner_name"])
    df["acreage"] = pd.to_numeric(df["acreage"], errors="coerce") * float(project.county.get("acreage_factor", 1))
    df["market_value"] = pd.to_numeric(df["market_value"], errors="coerce")
    for fam, col in project.county.get("code_columns", {}).items():
        df[f"codes_{fam}"] = _code_set(attrs[col]) if col in attrs else [set()] * len(df)
    # one row per parcel: several features or roll lines can share an id
    sets = [c for c in df if c.startswith("codes_")]
    agg = {c: "first" for c in df if c not in sets + ["parcel_id", "acreage"]}
    agg.update({c: (lambda x: set().union(*x)) for c in sets})
    agg["acreage"] = "max"
    df = df.groupby("parcel_id", as_index=False).agg(agg)

    geom = gpd.GeoDataFrame({"parcel_id": geo[src.get("parcels_key", cols["parcel_id"])].astype(str).str.strip()},
                            geometry=geo.geometry, crs=geo.crs)
    geom = geom[geom.geometry.notna()].copy()
    geom["geometry"] = geom.geometry.force_2d()
    df = reconcile_acreage(df, polygon_acres(geom), "county roll acreage")
    return df, geom


ADAPTERS = {"hcad": hcad, "generic": generic}
