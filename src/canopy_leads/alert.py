"""Weekly storm-damage alert: which accounts have a property near a new NWS storm report?

Pulls Local Storm Reports for the county's NWS offices from the Iowa Environmental Mesonet
archive, keeps the ones that damage trees and grounds, and lists every property in
output/alert_points.csv within --km of a report, highest-priority and highest-score first.

    canopy-leads alert my-list                       # last 7 days
    canopy-leads alert my-list --days 14 --km 3
    canopy-leads alert my-list --start 2024-05-16 --end 2024-05-18   # replay a past storm
    canopy-leads alert my-list --reports saved.csv                    # offline / demo

Writes output/alerts/alerts_<date>.csv (one row per account) and alerts_<date>_sites.csv, and
appends new hits to output/alerts/alert_log.csv so a report/property pair is logged once.
"""
import csv
import io
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from .fetch import UA, lsr_url

TREE_WORDS = re.compile(r"\btrees?\b|\blimbs?\b|\bbranch", re.I)
DAMAGE = ("D", "T", "O", "0")


def keep(r):
    """Wind damage, tornadoes, ice damage, tropical damage, gusts of 50+ mph, hail of 1.75+ in,
    and any report whose remark mentions trees."""
    code, text = r.get("TYPECODE", ""), r.get("TYPETEXT", "")
    try:
        mag = float(r.get("MAG") or "nan")
    except ValueError:
        mag = float("nan")
    if code in DAMAGE or text == "SNOW/ICE DMG":
        return True
    if code in ("G", "N") and text != "MARINE TSTM WIND":
        return math.isnan(mag) or mag >= 50
    if code == "H":
        return not math.isnan(mag) and mag >= 1.75
    return code != "M" and bool(TREE_WORDS.search(r.get("REMARK") or ""))


def km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def alert(p, days=7, start=None, end=None, radius_km=3.0, reports=None):
    end = (datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end else datetime.now(timezone.utc))
    start = (datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc) if start else end - timedelta(days=days))
    if reports:
        text = open(reports, encoding="utf-8", errors="replace").read()
    else:
        req = urllib.request.Request(lsr_url(p.county["nws_offices"], start, end), headers=UA)
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    reps = []
    for r in rows:
        try:
            r["lat"], r["lon"] = float(r["LAT"]), float(r["LON"])
        except (TypeError, ValueError, KeyError):
            continue
        if keep(r):
            reps.append(r)

    with open(p.out / "alert_points.csv", newline="") as f:
        points = list(csv.DictReader(f))
    dlat = radius_km / 111.0
    hits = []
    for pt in points:
        plat, plon = float(pt["lat"]), float(pt["lon"])
        near = [(km(plat, plon, r["lat"], r["lon"]), r) for r in reps
                if abs(r["lat"] - plat) <= dlat and abs(r["lon"] - plon) <= dlat * 1.3]
        near = [(d, r) for d, r in near if d <= radius_km]
        if not near:
            continue
        d, r = min(near, key=lambda x: x[0])
        damage = r.get("TYPECODE") in DAMAGE or r.get("TYPETEXT") == "SNOW/ICE DMG"
        hits.append({**pt, "priority": "high" if damage and d <= 2 else "medium" if damage or d <= 2 else "watch",
                     "report_time_utc": r.get("VALID2") or r.get("VALID", ""), "report_type": r.get("TYPETEXT", ""),
                     "magnitude": r.get("MAG", ""), "report_location": f"{r.get('CITY', '')}, {r.get('COUNTY', '')} Co.",
                     "km_from_site": round(d, 1), "reports_within_radius": len(near),
                     "report_remark": (r.get("REMARK") or "")[:300],
                     "report_id": f"{r.get('VALID')}|{r.get('LAT')}|{r.get('LON')}|{r.get('TYPECODE')}",
                     "source": "NWS Local Storm Reports via Iowa Environmental Mesonet"})
    rank = {"high": 0, "medium": 1, "watch": 2}
    hits.sort(key=lambda h: (rank[h["priority"]], -float(h.get("score") or 0)))
    out = p.out / "alerts"
    out.mkdir(exist_ok=True)
    stamp = end.strftime("%Y-%m-%d")
    lead = ["priority", "report_time_utc", "report_type", "magnitude", "report_location", "km_from_site",
            "reports_within_radius"]
    site_cols = lead + [k for k in (points[0].keys() if points else []) if k not in ("lat", "lon")] + ["report_remark", "source"]
    _write(out / f"alerts_{stamp}_sites.csv", hits, site_cols)

    by_acct = {}
    for h in hits:
        b = by_acct.setdefault(h["account"], {**h, "sites_hit": 0, "_sites": []})
        b["sites_hit"] += 1
        b["_sites"].append(h["site_name"] or h["site_street"])
    calls = list(by_acct.values())
    for cl in calls:
        cl["sites_hit_names"] = "; ".join(dict.fromkeys(s for s in cl["_sites"] if s))[:400]
    _write(out / f"alerts_{stamp}.csv", calls, lead + ["sites_hit", "sites_hit_names"] + site_cols[len(lead):])

    log = out / "alert_log.csv"
    seen = set()
    if log.exists():
        with open(log, newline="") as f:
            seen = {(r["report_id"], r["account"], r["site_name"]) for r in csv.DictReader(f)}
    new = [h for h in hits if (h["report_id"], h["account"], h["site_name"]) not in seen]
    first = not log.exists()
    with open(log, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["logged_utc", "report_id"] + site_cols, extrasaction="ignore")
        if first:
            w.writeheader()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        for h in new:
            w.writerow({"logged_utc": now, **h})

    print(f"Window {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC | {len(rows)} reports, {len(reps)} tree-relevant | "
          f"{len(hits)} properties at {len(calls)} accounts within {radius_km:g} km | {len(new)} new to the log")
    for h in calls[:15]:
        print(f"  [{h['priority']}] {h['account']} ({h['tier']} {h['score']}) – {h['sites_hit']} site(s), "
              f"{h['report_type']} {h['km_from_site']} km from {h['site_name'] or h['site_street']}")
    return calls


def _write(path, rows, cols):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
