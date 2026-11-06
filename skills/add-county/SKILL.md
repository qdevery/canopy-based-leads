---
name: add-county
description: Write a territory-gtm county.yaml for a county that isn't bundled - find the appraisal district's bulk parcel data, map its columns and local land-use / building codes to standard tags, pick the NWS office and the region's defining storms. Use when someone wants a territory list for a new county.
---

# Add a county

A county config tells the pipeline where the parcel data is, what its columns are called,
and what its local codes mean. Start from the bundled examples in
`src/territory_gtm/configs/counties/` (repository root = two folders above this skill):
`example_county.yaml` uses the `generic` adapter, which fits most counties;
`harris_tx.yaml` shows a district with several linked tables (its own adapter).

## 1. Find the data (public pages only)

- Search for "<county> appraisal district bulk data", "<county> assessor parcel download" or
  "<county> GIS open data parcels". In Texas every county has an appraisal district (CAD);
  elsewhere it's the assessor or the county GIS office.
- You need: owner name, mailing name / address (the "C/O" line names management firms),
  situs address, acreage, and land-use / property-class codes, plus parcel polygons.
- Read the download page's terms. If data is behind a login, a paid order form or a CAPTCHA,
  stop and tell the user: they can request it themselves (often a free public-records request).
- Many states also publish licensed-facility lists (assisted living, nursing homes) with
  coordinates; they confirm senior living and name the operator.

## 2. Inspect before mapping

Download a sample (or the file) into `runs/<county>/raw/` and look at it with pandas /
geopandas: column names, a few rows, the distinct values and counts of each code column.
Find the code descriptions (usually a lookup table or PDF on the same site).

## 3. Write county.yaml

- `adapter: generic`, `source.parcels` (path under raw/), optional `source.table` + keys.
- `columns:` map standard fields to the county's columns. Leave out what doesn't exist.
- `code_columns:` one column per code family (`state_class`, `land_use`, `building_type`...).
- `codes:` map each relevant local code to a tag from `tag_glossary` in the trade's YAML.
  Only map codes you have a description for; unmapped codes are simply untagged.
- `keyword_additions:` local public bodies (the state university, the port, the transit
  authority) under `PUBLIC`, local hospital systems under `HOSPITAL`, local tax consultants
  under `TAX_AGENT`.
- `bbox: [west, south, east, north]` in lon/lat, from the parcel layer's bounds.
- `nws_offices:` the NWS forecast office(s) covering the county (weather.gov shows it on the
  county's forecast page; e.g. HGX Houston, FWD Dallas–Fort Worth, EWX Austin/San Antonio).
- `storm_events:` one or two defining storms for the region (look at the Iowa Environmental
  Mesonet LSR archive for the office and pick events with many damage reports) plus one
  `recent` event with `days: 365`. Methods are explained in `src/territory_gtm/storms.py`.
- `downloads:` the direct file URLs so `tgtm fetch` can repeat the download next year.
- `sources:` one row per source with its URL and what it's used for.

## 4. Test

```bash
tgtm init runs/<county> --county path/to/county.yaml --trade tree_care
tgtm fetch runs/<county> && tgtm normalize runs/<county> && tgtm classify runs/<county>
```

`normalize` prints the share of parcels with at least one tag; a very low share means codes
are missing from the mapping. Review the checkpoint samples with the user before going on.
If the county ships several linked tables that the generic adapter can't join, write a small
adapter function in `src/territory_gtm/adapters.py` modelled on `hcad()`.
