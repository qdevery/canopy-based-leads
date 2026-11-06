"""Download the public source data a project needs into raw/.

- the county roll and parcel layer: the `downloads:` list in county.yaml
- licensed facility lists: `licensed_facilities.files[].url`
- tree canopy: USFS/NLCD Tree Canopy Cover 2021 (30 m) from the MRLC web coverage service,
  clipped to the county's bounding box
- storm reports: NWS Local Storm Reports from the Iowa Environmental Mesonet archive. The
  Storm Prediction Center's own pages disallow automated access, so they are never crawled.

Only plain public downloads: nothing here logs in, gets around a paywall or CAPTCHA, or
ignores a site's robots.txt or terms.
"""
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone

from .project import log, slug

UA = {"User-Agent": "territory-gtm/0.1 (public-data research; https://github.com/qdevery/territory-gtm)"}
WCS = ("https://www.mrlc.gov/geoserver/mrlc_download/wcs?service=WCS&version=2.0.1&request=GetCoverage"
       "&coverageId={cov}&subset=X({x0},{x1})&subset=Y({y0},{y1})&format=image/geotiff")
TCC = "mrlc_download__nlcd_tcc_conus_2021_v2021-4"
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/lsr.py?{wfos}&sts={s}&ets={e}&fmt=csv"


def download(url, dest, timeout=600):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    log(f"downloaded {dest.name} ({dest.stat().st_size / 1e6:,.1f} MB)")


def roll(p, force=False):
    for d in p.county.get("downloads", []):
        name = d.get("save_as") or urllib.parse.urlparse(d["url"]).path.rsplit("/", 1)[-1]
        dest = p.raw / name
        if dest.exists() and not force:
            log(f"have {name}")
        else:
            download(d["url"], dest)
        if d.get("unzip_to"):
            out = p.raw / d["unzip_to"]
            if force or not out.exists():
                with zipfile.ZipFile(dest) as z:
                    z.extractall(out)
                log(f"unzipped {name} -> {d['unzip_to']}/")
    for f in (p.county.get("licensed_facilities") or {}).get("files", []):
        dest = p.raw / f["path"]
        if f.get("url") and (force or not dest.exists()):
            download(f["url"], dest)


def _albers_bbox(bbox):
    """lon/lat bbox -> EPSG:5070 metres, which the MRLC coverage is published in."""
    from pyproj import Transformer
    t = Transformer.from_crs(4326, 5070, always_xy=True)
    xs, ys = zip(*[t.transform(x, y) for x in (bbox[0], bbox[2]) for y in (bbox[1], bbox[3])])
    pad = 600
    return int(min(xs) - pad), int(max(xs) + pad), int(min(ys) - pad), int(max(ys) + pad)


def canopy(p, force=False):
    dest = p.raw / "canopy.tif"
    if dest.exists() and not force:
        log("have canopy.tif")
        return
    bbox = p.county.get("bbox")
    if not bbox:
        raise SystemExit("county.yaml needs bbox: [west, south, east, north] (lon/lat) to fetch canopy")
    x0, x1, y0, y1 = _albers_bbox(bbox)
    cov = p.county.get("canopy_coverage", TCC)
    download(WCS.format(cov=cov, x0=x0, x1=x1, y0=y0, y1=y1), dest)
    with open(dest, "rb") as f:
        if f.read(4) not in (b"II*\x00", b"MM\x00*"):
            dest.unlink()
            raise SystemExit("MRLC returned an error instead of a GeoTIFF (box too large or service down). "
                             "Try a smaller bbox, or download Tree Canopy Cover from mrlc.gov/data and save it as raw/canopy.tif")


def storm_window(ev, now=None):
    now = now or datetime.now(timezone.utc)
    if ev.get("days"):
        return now - timedelta(days=int(ev["days"])), now
    return (datetime.fromisoformat(str(ev["start"]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(ev["end"]).replace("Z", "+00:00")))


def lsr_url(offices, start, end):
    wfos = "&".join(f"wfo%5B%5D={w}" for w in offices)
    return IEM.format(wfos=wfos, s=start.strftime("%Y-%m-%dT%H:%MZ"), e=end.strftime("%Y-%m-%dT%H:%MZ"))


def storms(p, force=False):
    offices = p.county.get("nws_offices") or []
    if not offices:
        raise SystemExit("county.yaml needs nws_offices: [XXX] (the NWS forecast office codes covering the county)")
    for ev in p.county.get("storm_events", []):
        dest = p.raw / "storms" / f"{slug(ev['name'])}.csv"
        if dest.exists() and not force and not ev.get("days"):
            log(f"have storms/{dest.name}")
            continue
        s, e = storm_window(ev)
        download(lsr_url(offices, s, e), dest, timeout=180)


def run(p, what=("roll", "canopy", "storms"), force=False):
    if "roll" in what:
        roll(p, force)
    if "canopy" in what:
        canopy(p, force)
    if "storms" in what:
        storms(p, force)
