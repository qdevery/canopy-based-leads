"""Step 5: storm exposure per parcel from NWS Local Storm Reports.

county.yaml lists the region's defining storms; each one becomes a 0-1 score and the
weighted mean is storm_exposure. Three methods:

  gust_field      estimated peak gust at the parcel, inverse-distance weighted from the
                  6 nearest measured gusts, plus a bump for damage reports within 5 km
                  (hurricanes, big wind events with many gauges)
  nearest_report  distance to the nearest damage / gust / tornado report
                  (derechos, tornado outbreaks, ice storms)
  recent          distance-weighted count of reports in the last N days (keeps the
                  score current; use one of these in every county)
"""
import numpy as np
import pandas as pd

from .project import log, slug

DAMAGE = ["D", "T", "O", "0"]


def km_matrix(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1)[:, None], np.radians(lat2)[None, :]
    dlon = np.radians(lon2)[None, :] - np.radians(lon1)[:, None]
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def read_lsr(path):
    d = pd.read_csv(path, on_bad_lines="skip", dtype={"TYPECODE": str})
    d["MAG"] = pd.to_numeric(d.get("MAG"), errors="coerce")
    d["LAT"], d["LON"] = pd.to_numeric(d["LAT"], errors="coerce"), pd.to_numeric(d["LON"], errors="coerce")
    return d.dropna(subset=["LAT", "LON"])


def _in_box(d, bbox, pad=1.0):
    if not bbox:
        return d
    return d[d["LON"].between(bbox[0] - pad, bbox[2] + pad) & d["LAT"].between(bbox[1] - pad, bbox[3] + pad)]


def score_event(ev, d, lat, lon, bbox):
    m = ev.get("method", "nearest_report")
    out = {}
    if m == "gust_field":
        st = d[d["TYPECODE"].isin(ev.get("gust_typecodes", ["N", "G"])) & d["MAG"].notna()]
        st = _in_box(st.groupby(["LAT", "LON"], as_index=False)["MAG"].max(), bbox)
        if len(st) == 0:
            return np.zeros(len(lat)), {}
        dist = km_matrix(lat, lon, st["LAT"].to_numpy(), st["LON"].to_numpy())
        k = min(6, len(st))
        near = np.argsort(dist, axis=1)[:, :k]
        dn = np.maximum(np.take_along_axis(dist, near, axis=1), 1.0)
        w = 1 / dn ** 2
        gust = (w * st["MAG"].to_numpy()[near]).sum(1) / w.sum(1)
        dmg = d[d["TYPECODE"].isin(DAMAGE)]
        n5 = (km_matrix(lat, lon, dmg["LAT"].to_numpy(), dmg["LON"].to_numpy()) <= 5).sum(1) if len(dmg) else 0
        lo, hi = ev.get("gust_low", 60), ev.get("gust_high", 85)
        s = np.clip((gust - lo) / (hi - lo), 0, 1) + np.minimum(n5, 2) * 0.1
        out = {"gust_mph": gust.round(0)}
        return np.clip(s, 0, 1), out
    if m == "nearest_report":
        r = d[d["TYPECODE"].isin(ev.get("typecodes", ["D", "G", "T"]))]
        if len(r) == 0:
            return np.zeros(len(lat)), {}
        dkm = km_matrix(lat, lon, r["LAT"].to_numpy(), r["LON"].to_numpy()).min(1)
        full, zero = ev.get("full_km", 2), ev.get("zero_km", 15)
        return np.clip(1 - (dkm - full) / (zero - full), 0, 1), {"nearest_km": dkm.round(1)}
    if m == "recent":
        codes = ev.get("typecodes", ["D", "G", "T", "N", "O"])
        r = d[d["TYPECODE"].isin(codes) | (d.get("TYPETEXT", "") == "SNOW/ICE DMG")]
        if len(r) == 0:
            return np.zeros(len(lat)), {"reports_10km": np.zeros(len(lat), int)}
        dist = km_matrix(lat, lon, r["LAT"].to_numpy(), r["LON"].to_numpy())
        s = np.clip(np.exp(-dist / ev.get("decay_km", 4)).sum(1) / ev.get("saturation", 1.5), 0, 1)
        return s, {"reports_10km": (dist <= 10).sum(1)}
    raise SystemExit(f"storm event '{ev['name']}': unknown method '{m}'")


def storms(p):
    leads = pd.read_parquet(p.work / "leads.parquet", columns=["parcel_id", "lat", "lon"]).drop_duplicates("parcel_id")
    ok = leads["lat"].notna().to_numpy()
    lat, lon = leads.loc[ok, "lat"].to_numpy(), leads.loc[ok, "lon"].to_numpy()
    out = leads[["parcel_id"]].copy()
    events = p.county.get("storm_events", [])
    total_w, acc = 0.0, np.zeros(len(lat))
    for ev in events:
        path = p.raw / "storms" / f"{slug(ev['name'])}.csv"
        if not path.exists():
            log(f"missing {path.relative_to(p.dir)} — run: canopy-leads fetch <project> --what storms")
            continue
        d = read_lsr(path)
        s, extra = score_event(ev, d, lat, lon, p.county.get("bbox"))
        key = slug(ev["name"])
        out.loc[ok, f"storm_{key}"] = s
        for k, v in extra.items():
            out.loc[ok, f"{key}_{k}"] = v
        acc += ev.get("weight", 1) * s
        total_w += ev.get("weight", 1)
        log(f"{ev['name']}: {len(d):,} reports, mean score {s.mean():.2f}")
    if total_w:
        out.loc[ok, "storm_exposure"] = acc / total_w
        out["storm_exposure"] = out["storm_exposure"].fillna(out["storm_exposure"].median())
    else:
        out["storm_exposure"] = np.nan
    out["src_storm"] = (f"NWS Local Storm Reports ({', '.join(p.county.get('nws_offices', []))}) via the Iowa "
                        "Environmental Mesonet archive: " + "; ".join(f"{e['name']} {e.get('weight', 1):g}" for e in events))
    out.to_parquet(p.work / "storms.parquet", index=False)
