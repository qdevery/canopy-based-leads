"""Step 3: tree canopy and a map point for every parcel that landed in a segment.

canopy_pct is the mean of the canopy raster over the parcel polygon (zonal statistics);
canopy_acres_est = acreage x canopy_pct. At 30 m, parcels smaller than about one pixel get no
reading. A trade with canopy weight 0 (roofing, paving) can skip the raster entirely.
"""
import geopandas as gpd
import numpy as np
import pandas as pd

from .project import log


def canopy(p):
    df = pd.read_parquet(p.work / "classified.parquet", columns=["parcel_id", "segment", "acreage"])
    floor = float(p.trade.get("filters", {}).get("canopy_min_acres", 0))
    ids = set(df.loc[df["segment"].notna() & (df["acreage"].fillna(0) >= floor), "parcel_id"])
    geom = gpd.read_parquet(p.work / "parcels_geom.parquet")
    geom = geom[geom["parcel_id"].isin(ids)].copy()
    geom["geometry"] = geom.geometry.make_valid()
    geom = geom.dissolve(by="parcel_id").reset_index()
    log(f"{len(geom):,} segment parcels with polygons")

    pts = geom.copy()
    pts["geometry"] = pts.geometry.representative_point()
    pts = pts.to_crs(4326)
    out = pd.DataFrame({"parcel_id": geom["parcel_id"], "lat": pts.geometry.y.round(6), "lon": pts.geometry.x.round(6)})

    tif = p.raw / "canopy.tif"
    if tif.exists():
        import rasterio
        from rasterstats import zonal_stats
        with rasterio.open(tif) as r:
            arr = r.read(1).astype("float32")
            arr[(arr > 100) | (arr < 0)] = np.nan  # 254/255 = background / not processed
            g = geom.to_crs(r.crs)
            zs = zonal_stats(g.geometry, arr, affine=r.transform, stats=["mean", "count"], nodata=np.nan)
        out["canopy_pct"] = [round(z["mean"], 1) if z["mean"] is not None else np.nan for z in zs]
        out["canopy_px"] = [z["count"] for z in zs]
        src = p.county.get("canopy_source", "USFS/NLCD Tree Canopy Cover 2021, 30 m (mrlc.gov)")
        out["src_canopy"] = np.where(out["canopy_pct"].notna(), src, "parcel smaller than a canopy pixel")
        log(f"canopy measured for {out['canopy_pct'].notna().sum():,} of {len(out):,} parcels")
    else:
        out["canopy_pct"], out["canopy_px"], out["src_canopy"] = np.nan, 0, "no canopy raster (raw/canopy.tif)"
        log("no raw/canopy.tif — canopy left blank (run: canopy-leads fetch <project> --what canopy)")
    out.to_parquet(p.work / "canopy.parquet", index=False)
