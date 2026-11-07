# canopy-based-leads

**From a county tax roll to a ranked call list.** A Claude Code plugin and a Python pipeline
that find every commercial property with grounds worth servicing in a county, trace each one
to the company that actually buys the work, and score it 0–100 with a one-line outreach angle.
It runs on free public data. Contacts are optional and sit behind a credit gate.

Built for field-service companies: tree care out of the box; landscaping, roofing, paving or
irrigation with one YAML file.

**📖 Setup and how-to guide: https://apps.fringelines.io/canopy-based-leads/**

```
county tax roll ─► classify ─► canopy ─► who buys ─► storms ─► score ─► workbook, call sheet, Clay import
 (owners, codes,    8 segments   30 m tree   mgmt firm,   NWS damage   0–100 +     + contacts (credit gate)
  mailing lines)    by rules     cover       operator…    reports      angle       + weekly storm alerts
```

Harris County, TX (the worked example) on a laptop: 1.6 M accounts read → 32,317 parcels with
1+ acre of grounds → 9,890 buyer accounts → 169 tier A, in about 2½ minutes after download.

## Quick start

**As a Claude Code plugin** (Claude Code desktop or CLI):

```
/plugin marketplace add qdevery/canopy-based-leads
/plugin install canopy-leads@canopy-based-leads
/canopy-leads:demo
```

Then ask: *"Build a tree-care account list for Harris County, TX"* or run `/canopy-leads:build Travis County, TX`.

**As a command-line tool** (Python 3.10+):

```bash
git clone https://github.com/qdevery/canopy-based-leads && cd canopy-based-leads
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
canopy-leads demo runs/demo                      # synthetic county, offline, ~1 minute
canopy-leads init runs/harris --county harris_tx --trade tree_care
canopy-leads fetch runs/harris                   # ~650 MB from HCAD, canopy, storm reports
canopy-leads run runs/harris
```

## What you get (in `runs/<county>/output/`)

| File | What it is |
|---|---|
| `<county>_<trade>_leads.xlsx` | Summary, one tab per segment, Management Companies, managed communities, Contacts, Method, Rules, Sources. Every value has a `src_*` column. |
| `call_sheet_top50.md` | The first 50 calls: who, why, the angle. |
| `clay/` | `clay_companies.csv`, `clay_people.csv`, `clay_communities.csv`, linked by ids, ready for Clay tables. |
| `contacts/shortlist.csv` | Accounts to research for contacts, with the credit estimate to approve first. |
| `checkpoints/` | Samples and top-buyer lists to review before trusting the list. |
| `alerts/` | Weekly storm-damage alerts: accounts with a property near a new NWS report. |

See [`examples/demo_output/`](examples/demo_output/) for a full set from the synthetic county.

## How it works

1. **Normalize** the county's roll into one standard parcel table (an adapter per data format).
2. **Classify** every parcel into a segment with ordered rules over tags and name keywords
   (`county.yaml` maps local codes to tags, so rules work in any county).
3. **Canopy**: average tree cover over each parcel polygon (USFS/NLCD 30 m).
4. **Who buys**: roll parcels up to the buyer — the district, the licensed operator, a verified
   management firm, the care-of firm on the mailing line, the firm most often at that mailing
   address, an owner group, or the owner.
5. **Storms**: exposure to the region's defining storms from NWS Local Storm Reports.
6. **Score**: acreage 25 + canopy 20 + properties 15 + segment fit 20 + storm 20, tiers A/B/C,
   and an angle written from each account's own numbers.
7. **Export**, then optionally **contacts** (Apollo / Clay through Claude, cheapest first, after
   you approve the count and cost) and **storm alerts**.

## Plugin contents

| | |
|---|---|
| Skills | `build-territory-list`, `find-contacts`, `add-county`, `add-trade`, `storm-alerts` |
| Commands | `/canopy-leads:demo`, `/canopy-leads:build`, `/canopy-leads:storm-alert` |
| Hook | `hooks/guardrails.py`: inside a project folder, blocks sending, sequencing and CRM writes, and asks before any credit-spending enrichment |

## Ground rules

- Research and files only: no emails, sequences, campaigns or CRM records.
- Public data only: never around a login, paywall, CAPTCHA, robots.txt or a site's terms.
- Business contacts only: no personal emails or cells, no home addresses, no skip tracing,
  never HOA board members or other volunteers.
- Ask before spending credits: count and estimate first, then a person says yes.
- Don't guess: missing stays missing, with a suggested source.

## Configs

- Counties: `src/canopy_leads/configs/counties/` — `harris_tx` (HCAD) and `example_county`
  (template for the `generic` adapter, which fits most counties).
- Trades: `src/canopy_leads/configs/trades/tree_care.yaml`.
- `canopy-leads init` copies both into your project folder; edit the copies.

## Data sources

| Source | Used for |
|---|---|
| County appraisal district / assessor bulk data (e.g. [HCAD](https://download.hcad.org/)) | owners, mailing / care-of lines, acreage, codes, parcel outlines |
| [USFS / NLCD Tree Canopy Cover](https://www.mrlc.gov/data) | canopy per parcel |
| [NWS Local Storm Reports via Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/request/gis/lsrs.phtml) | storm exposure, weekly alerts |
| State licensed-facility lists (e.g. [Texas HHSC](https://apps.hhs.texas.gov/providers/directories/)) | senior living operators |
| Apollo, Clay (optional, your own accounts) | business contacts |

Check each source's terms before commercial use; they can change.

## Development

```bash
pip install -e ".[test]" && pytest
```

MIT licensed. Issues and pull requests welcome — especially county configs and new trades.
