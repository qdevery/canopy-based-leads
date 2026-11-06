"""A synthetic county, so the whole pipeline runs offline in about a minute.

Every name, address, contact and storm report here is invented. Contact emails use the
reserved .example domain. Parcels sit in a made-up grid; nothing describes a real property.
"""
import random

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from .project import log

CELL = 1200  # metres between parcel centres
ORIGIN = (60_000, 900_000)  # EPSG:5070 metres (east Texas pine country)

FIRST = ["Willow", "Cedar", "Briar", "Fox", "Heron", "Maple", "Quail", "Stone", "Timber", "Pecan", "Magnolia",
         "Bluff", "Sable", "Copper", "Laurel", "Juniper", "Elm", "Hollow", "Prairie", "Falcon", "Cypress", "Aspen"]
SECOND = ["Creek", "Ridge", "Bend", "Glen", "Run", "Hollow", "Park", "Meadows", "Crossing", "Trails", "Lakes", "Point",
          "Grove", "Landing", "Woods", "Village", "Estates", "Pines", "Springs", "Oaks"]
MANAGERS = [("PINECONE COMMUNITY MANAGEMENT", "4100 COMMERCE PARK DR STE 200", "77701"),
            ("BLUEBIRD ASSOCIATION SERVICES", "PO BOX 4410", "77702"),
            ("COPPERLEAF HOA MANAGEMENT LLC", "880 GATEWAY BLVD STE 12", "77703")]
APT_OPERATORS = [("SUMMIT HOLLOW RESIDENTIAL LLC", "2200 LAKEFRONT PKWY STE 900", "77710"),
                 ("REDBUD MULTIFAMILY PARTNERS", "PO BOX 7781", "77711")]
SENIOR_OPERATORS = ["MAPLECREST SENIOR LIVING", "GOLDEN ACRE CARE GROUP", "RIVERSTONE HEALTH SERVICES"]
STREETS = ["OAK", "PINE", "MILL", "CHURCH", "LAKE", "RANCH", "FOREST", "HIGHLAND", "MEADOW", "RIVER", "SCHOOL", "MARKET"]


def _name(rng):
    return f"{rng.choice(FIRST)} {rng.choice(SECOND)}".upper()


def _street(rng):
    return f"{rng.randint(100, 9800)} {rng.choice(STREETS)} {rng.choice(['RD', 'ST', 'DR', 'LN', 'BLVD'])}"


def make_parcels(seed=7):
    rng = random.Random(seed)
    rows = []

    def add(owner, mail_name, mail_addr, mail_zip, acres, sc, bt="", lu="", prop="", city="EXAMPLEVILLE"):
        rows.append({"OWNER": owner, "MAIL_NAME": mail_name, "MAIL_ADDR": mail_addr, "MAIL_CITY": "EXAMPLEVILLE",
                     "MAIL_ST": "TX", "MAIL_ZIP": mail_zip, "ACRES": round(acres, 2), "STATE_CD": sc, "BLDG_TYPE": bt,
                     "LAND_USE": lu, "PROP_NAME": prop, "SITUS": _street(rng), "SITUS_CITY": city,
                     "SITUS_ZIP": rng.choice(["77720", "77721", "77722", "77723"]),
                     "MKT_VAL": int(acres * rng.randint(40_000, 400_000))})

    # HOAs: 36 associations, 2-5 common-area parcels each; 24 run by 3 management firms
    for i in range(36):
        nm = _name(rng)
        owner = f"{nm} COMMUNITY ASSOCIATION INC" if i % 3 else f"{nm} HOMEOWNERS ASSN"
        if i < 24:
            firm, addr, z = MANAGERS[i % 3]
            mail_name, mail_addr = f"{owner} C/O {firm}", addr
        else:
            firm, z = None, "77725"
            mail_name, mail_addr = owner, _street(rng)  # self-managed: mails to a volunteer's house
        for _ in range(rng.randint(2, 5)):
            add(owner, mail_name, mail_addr, z, rng.uniform(0.4, 18), "X2" if rng.random() < .2 else "C1", lu="OPEN")
    # apartments
    for i in range(48):
        nm = _name(rng)
        owner = f"{nm} APARTMENTS LP"
        if i < 30:
            op, addr, z = APT_OPERATORS[i % 2]
            add(owner, f"{owner} C/O {op}", addr, z, rng.uniform(4, 30), "B1", "APT", "COM", f"{nm} APARTMENTS")
        else:
            add(owner, owner, _street(rng), "77726", rng.uniform(2, 16), "B1", "APT", "COM", f"{nm} APARTMENTS")
    # senior living (some only identifiable through the state facility list)
    for i in range(18):
        nm = _name(rng)
        bt = "NURS" if i % 2 else "RETIRE"
        add(f"{nm} SENIOR LIVING LLC" if i < 14 else f"{nm} PROPERTIES LLC", f"{nm} PROPERTIES LLC", _street(rng),
            "77727", rng.uniform(2, 22), "F1", bt if i < 14 else "OFFICE", "COM", f"{nm} {'CARE CENTER' if i % 2 else 'SENIOR LIVING'}")
    # churches, 12 of them parishes of one diocese with a central facilities office
    for i in range(60):
        nm = _name(rng).title().upper()
        if i < 12:
            owner = f"DIOCESE OF EXAMPLE ST {rng.choice(['MARY', 'JOSEPH', 'PAUL', 'ANNE', 'LUKE', 'JAMES'])} PARISH"
            add(owner, "DIOCESE OF EXAMPLE", "PO BOX 1200", "77701", rng.uniform(2, 25), "X3", "CHURCH", "COM")
        else:
            owner = f"{nm} {rng.choice(['BAPTIST CHURCH', 'METHODIST CHURCH', 'BIBLE FELLOWSHIP', 'CHURCH OF CHRIST'])}"
            add(owner, owner, _street(rng), "77728", rng.uniform(1, 18), "X3", "CHURCH", "COM")
    # golf
    for i in range(5):
        nm = _name(rng)
        add(f"{nm} COUNTRY CLUB INC", f"{nm} COUNTRY CLUB INC", _street(rng), "77729", rng.uniform(120, 290), "F1", "GOLF", "COM")
    # other commercial with grounds
    for kind, sc, bt, n, lo, hi in [("REGIONAL HOSPITAL", "F1", "HOSP", 4, 15, 70), ("ACADEMY", "XJ", "SCHOOL", 8, 5, 40),
                                    ("OFFICE PARK LP", "F1", "OFFICE", 14, 3, 35), ("SHOPPING CENTER LLC", "F1", "RETAIL", 12, 4, 30),
                                    ("MANUFACTURING CO", "F2", "WHSE", 10, 5, 80), ("MEMORIAL CEMETERY", "X4", "", 5, 5, 45),
                                    ("INN & SUITES LLC", "F1", "HOTEL", 4, 2, 8)]:
        for _ in range(n):
            nm = _name(rng)
            add(f"{nm} {kind}", f"{nm} {kind}", _street(rng), "77730", rng.uniform(lo, hi), sc, bt, "COM")
    # districts, managed day to day by an operator firm
    for i in range(22):
        owner = f"EXAMPLE COUNTY MUD {i + 3}"
        add(owner, f"{owner} C/O BAYLEAF DISTRICT SERVICES", "7700 UTILITY WAY STE 300", "77740",
            rng.uniform(1, 40), "X1", "", "UTIL")
    # public owners and homes: in the roll, never leads
    for _ in range(25):
        add(rng.choice(["CITY OF EXAMPLEVILLE", "EXAMPLE ISD", "EXAMPLE COUNTY"]), "CITY OF EXAMPLEVILLE", "PO BOX 1",
            "77701", rng.uniform(1, 60), "X1", "", "COM")
    for _ in range(420):
        last = rng.choice(["DOE", "ROE", "POE", "MOE", "LOE"])
        add(f"{last} {rng.choice(['JANE', 'JOHN', 'ALEX', 'SAM'])} {rng.choice('ABCDEFG')}", "", _street(rng), "77750",
            rng.uniform(0.1, 0.6), "A1", "", "RES")

    df = pd.DataFrame(rows)
    rng.shuffle(order := list(range(len(df))))
    df = df.iloc[order].reset_index(drop=True)
    df.insert(0, "PARCEL_ID", [f"EX{i:06d}" for i in range(1, len(df) + 1)])
    side = int(np.ceil(np.sqrt(len(df))))
    geoms = []
    for i, ac in enumerate(df["ACRES"]):
        cx, cy = ORIGIN[0] + (i % side) * CELL, ORIGIN[1] + (i // side) * CELL
        w = np.sqrt(ac * 4046.86) * rng.uniform(0.75, 1.3)
        h = ac * 4046.86 / w
        geoms.append(box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    return gpd.GeoDataFrame(df, geometry=geoms, crs=5070)


def make_canopy(parcels, path, seed=7):
    """30 m canopy raster: a smooth background plus segment-typical cover on each parcel."""
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = parcels.total_bounds
    x0, y0, x1, y1 = x0 - 900, y0 - 900, x1 + 900, y1 + 900
    w, h = int((x1 - x0) / 30), int((y1 - y0) / 30)
    yy, xx = np.mgrid[0:h, 0:w]
    base = 25 + 15 * np.sin(xx / 70) * np.cos(yy / 55) + rng.normal(0, 6, (h, w))
    typical = {"GOLF": 38, "OPEN": 46, "CHURCH": 22, "APT": 16, "NURS": 18, "RETIRE": 20, "HOSP": 14, "SCHOOL": 24,
               "OFFICE": 15, "RETAIL": 6, "WHSE": 9, "HOTEL": 8, "UTIL": 30, "RES": 32}
    shapes = []
    for g, bt, lu in zip(parcels.geometry, parcels["BLDG_TYPE"], parcels["LAND_USE"]):
        v = typical.get(bt) or typical.get(lu) or 25
        shapes.append((g, float(np.clip(v + rng.normal(0, 9), 1, 90))))
    tr = from_origin(x0, y1, 30, 30)
    burned = rasterize(shapes, out_shape=(h, w), transform=tr, fill=-1, dtype="float32")
    arr = np.where(burned >= 0, burned + rng.normal(0, 8, (h, w)), base)
    arr = np.clip(arr, 0, 95).astype("uint8")
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=1, dtype="uint8", crs="EPSG:5070",
                       transform=tr, nodata=255) as dst:
        dst.write(arr, 1)


def make_storms(parcels, storms_dir, seed=7):
    """IEM-format Local Storm Report CSVs for the demo county's three storms + an alert replay."""
    rng = np.random.default_rng(seed)
    ll = parcels.geometry.centroid.to_crs(4326)
    lon0, lat0, lon1, lat1 = ll.x.min(), ll.y.min(), ll.x.max(), ll.y.max()
    storms_dir.mkdir(parents=True, exist_ok=True)

    def frame(n, code, text, mags, lat, lon, when, remark):
        return pd.DataFrame({"VALID": when, "VALID2": when, "LAT": np.round(lat, 4), "LON": np.round(lon, 4), "MAG": mags,
                             "WFO": "XXX", "TYPECODE": code, "TYPETEXT": text, "CITY": "EXAMPLEVILLE",
                             "COUNTY": "EXAMPLE", "STATE": "TX", "SOURCE": "PUBLIC", "REMARK": remark})

    # a hurricane whose gusts rise toward the south-east corner
    n = 22
    lat, lon = rng.uniform(lat0 - .1, lat1 + .1, n), rng.uniform(lon0 - .1, lon1 + .1, n)
    gust = 58 + 30 * ((lon - lon0) / (lon1 - lon0) + (lat1 - lat) / (lat1 - lat0)) / 2 + rng.normal(0, 3, n)
    hurr = pd.concat([frame(n, "N", "NON-TSTM WND GST", gust.round(0), lat, lon, "202407081400", "Measured gust."),
                      frame(12, "D", "NON-TSTM WND DMG", "", rng.uniform(lat0, lat1, 12), rng.uniform((lon0 + lon1) / 2, lon1, 12),
                            "202407081500", "Several large trees down on homes and roads.")])
    hurr.to_csv(storms_dir / "hurricane_example_2024.csv", index=False)
    # a derecho tracking west to east across the middle of the county
    t = rng.uniform(0, 1, 40)
    der = frame(40, "D", "TSTM WND DMG", "", (lat0 + lat1) / 2 + rng.normal(0, .025, 40), lon0 + t * (lon1 - lon0),
                "202405161900", "Numerous trees and power lines down.")
    der.to_csv(storms_dir / "spring_2024_derecho.csv", index=False)
    rec = frame(26, rng.choice(["D", "G", "T"], 26), "TSTM WND DMG", "", rng.uniform(lat0, lat1, 26), rng.uniform(lon0, lon1, 26),
                "202606021800", "Large limbs down.")
    rec.to_csv(storms_dir / "last_12_months.csv", index=False)
    # a fresh storm for the weekly alert replay
    al = frame(9, "D", "TSTM WND DMG", "", rng.uniform(lat0, (lat0 + lat1) / 2, 9), rng.uniform(lon0, lon1, 9),
               "202611031830", "Trees down blocking the road.")
    al.to_csv(storms_dir / "demo_alert_reports.csv", index=False)


def make_facilities(parcels, path, seed=7):
    """A state licensed-facility list: senior parcels plus two that only this list reveals."""
    rng = random.Random(seed)
    sen = parcels[parcels["BLDG_TYPE"].isin(["NURS", "RETIRE"]) | parcels["OWNER"].str.contains("PROPERTIES LLC")
                  & parcels["PROP_NAME"].str.contains("CARE|SENIOR")]
    pts = sen.to_crs(4326).geometry.representative_point()
    pd.DataFrame({"Facility Name": sen["PROP_NAME"], "County": "EXAMPLE",
                  "Geo Location": [f"{p.y:.6f},{p.x:.6f}" for p in pts],
                  "Management Company": [rng.choice(SENIOR_OPERATORS) for _ in range(len(sen))],
                  "Facility Phone Number": [f"(555) 01{rng.randint(0, 99):02d}" for _ in range(len(sen))]}).to_csv(path, index=False)


def make_contacts(path):
    """Invented business contacts (reserved .example domains) for a few demo accounts."""
    pd.DataFrame([
        ("", "Pinecone Community Management", "Person", "Jordan Lee", "Director of Community Management",
         "Pinecone Community Management", "jordan.lee@pinecone-cm.example", "verified (demo)", "(555) 010-2000"),
        ("", "Pinecone Community Management", "Person", "Riley Park", "Community Manager",
         "Pinecone Community Management", "riley.park@pinecone-cm.example", "verified (demo)", ""),
        ("", "Bluebird Association Services", "Person", "Sam Rivera", "Portfolio Manager",
         "Bluebird Association Services", "sam.rivera@bluebird-as.example", "verified (demo)", "(555) 010-3000"),
        ("", "Diocese Of Example (central facilities)", "Person", "Casey Morgan", "Director of Facilities",
         "Diocese of Example", "facilities@diocese.example", "shared office mailbox (demo)", "(555) 010-4000"),
        ("", "Summit Hollow Residential", "Person", "Taylor Brooks", "Regional Maintenance Supervisor",
         "Summit Hollow Residential", "tbrooks@summithollow.example", "verified (demo)", ""),
        ("", "Summit Hollow Residential", "Person", "Avery Chen", "Personal address example",
         "Summit Hollow Residential", "avery.home@gmail.example", "", ""),
    ], columns=["account_id", "account", "contact_type", "name", "title", "company", "business_email", "email_status",
                "business_phone"]).assign(source="invented for the demo", found_on="2026-11-01").to_csv(path, index=False)


FIRM_ALIASES = """match_type,pattern,firm,firm_type,website,verified_source
care_of,^PINECONE COMMUNITY,Pinecone Community Management,HOA management company,https://pinecone-cm.example,demo: firm's own website
address,^4100 COMMERCE PARK \\| 77701,Pinecone Community Management,HOA management company,https://pinecone-cm.example,demo: care-of lines at the firm's office
care_of,^SUMMIT HOLLOW,Summit Hollow Residential,Apartment operator,https://summithollow.example,demo: operator website
owner,^DIOCESE OF EXAMPLE,Diocese of Example (central facilities),Religious organization (central facilities),,demo: diocese website lists its parishes
"""


def build(project):
    raw = project.raw
    log("generating the synthetic Example County …")
    parcels = make_parcels()
    parcels.to_file(raw / "example_parcels.gpkg", driver="GPKG")
    make_canopy(parcels, raw / "canopy.tif")
    make_storms(parcels, raw / "storms")
    make_facilities(parcels, raw / "facilities.csv")
    make_contacts(project.dir / "contacts.csv")
    (project.dir / "firm_aliases.csv").write_text(FIRM_ALIASES)
    log(f"{len(parcels):,} parcels, canopy raster, storm reports, a facility list and demo contacts written")
