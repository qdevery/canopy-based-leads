---
name: build-territory-list
description: Build a ranked B2B account list for a field-service company (tree care, landscaping, roofing, paving...) from free public data - a county's appraisal / tax roll, tree canopy and NWS storm reports - with a score, tier and outreach angle per account. Use when someone asks to build a lead list, prospect list, account list or territory map for a county, or to run canopy-based-leads.
---

# Build a territory account list

You run the `canopy-leads` pipeline for a county + trade and review each checkpoint with the user.
The pipeline is deterministic Python; your job is setup, judgment at the checkpoints, and
explaining the results. The repository root is two folders above this skill's base directory
(it holds `pyproject.toml`, `src/canopy_leads/` and `docs/`).

## Ground rules (repeat them to the user at the start, follow them throughout)

- **Research and files only.** Never send emails or messages, add anyone to a sequence or
  campaign, or create CRM records. The plugin's hook blocks those tools in project folders.
- **Public data only.** Never get around a login, paywall, CAPTCHA, robots.txt or a site's terms.
  If a source blocks automated access, say so and use another (e.g. storm reports come from
  the Iowa Environmental Mesonet archive because the Storm Prediction Center disallows bots).
- **Business contacts only.** Business emails and business phones. No personal cells, home
  addresses or skip tracing. No contact details for HOA board members or other volunteers.
- **Ask before spending credits.** Before any Apollo / Clay enrichment, state the record count
  and estimated credits and wait for a clear yes (see the `find-contacts` skill).
- **Don't guess.** If a field isn't available, say so and propose another source.

## 1. Set up (once per machine)

```bash
python3 -m venv .venv && .venv/bin/pip install "<repo root>"
.venv/bin/canopy-leads list
```

Needs Python 3.10+. If `pip` fails on GDAL / rasterio, suggest `conda install -c conda-forge
geopandas rasterio rasterstats` and then `pip install --no-deps "<repo root>"`.
If the user has never run it, offer `canopy-leads demo runs/demo` first (offline, about a minute).

## 2. Interview (keep it short)

Ask only what you can't infer: the county and state, the trade (bundled: `canopy-leads list`), the
segments they care about, the minimum acreage worth a visit (default 1 acre), and whether they
want contacts researched (and which tiers). Note the folder they want the project in.

## 3. Configure

- County bundled → `canopy-leads init runs/<county> --county <name> --trade <trade>`.
- County not bundled → follow the `add-county` skill to write `county.yaml` first.
- Trade not bundled → follow the `add-trade` skill.
- Read the copied `county.yaml` with the user: source URLs, bbox, NWS office(s), storm events.

## 4. Fetch

`canopy-leads fetch runs/<county>` downloads the roll (often 0.5–2 GB; say how big before starting
and run it in the background), the canopy raster and the storm reports. Check each source's
terms page once and tell the user what you found.

## 5. Checkpoint 1: classification

```bash
canopy-leads normalize runs/<county> && canopy-leads classify runs/<county>
```

Open `output/checkpoints/1_classification_counts.csv`, `1_samples_by_segment.csv` and
`1_uncertain_top200.csv`. Show the user a compact table and 3–5 examples per segment.
Look for misfires (a given name read as "HOA", churches that are really schools, public
owners slipping through). Fix them in `trade.yaml` rules or `county.yaml` codes /
`keyword_additions`, rerun classify, and say what changed and why. Get a go-ahead.

## 6. Checkpoint 2: who buys

```bash
canopy-leads canopy runs/<county> && canopy-leads rollup runs/<county>
```

Review `2_top_buyers_by_acres.csv`, `2_top_buyers_by_properties.csv` and
`2_firm_alias_candidates.csv`. For the largest management firms, check the firm's own
website (public pages only) and add verified rows to `firm_aliases.csv` with the URL as
`verified_source`. Flag inferred links ("confirm before use") rather than asserting them.
Rerun `canopy-leads rollup`.

## 7. Score and export

```bash
canopy-leads storms runs/<county> && canopy-leads score runs/<county> && canopy-leads export runs/<county>
```

Report: accounts per segment, tier A / B / C counts, the top 10 with their angles, what is
missing and why (e.g. "canopy is 30 m, so small reserves have no reading"). Point to
`output/<stem>_leads.xlsx`, `call_sheet_top50.md`, `csv/` and `clay/`.

## 8. Next

- Contacts → the `find-contacts` skill (always behind the credit gate).
- Weekly storm-damage alerts → the `storm-alerts` skill.
- Rerun any time with `canopy-leads run runs/<county> --from <step>`.

Keep every number traceable: each workbook column has a `src_*` column, and the Method,
Rules and Sources tabs explain the build. Never invent a value to fill a gap.
