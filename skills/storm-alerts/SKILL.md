---
name: storm-alerts
description: Check which accounts on a canopy-based-leads list had a property near a new National Weather Service storm-damage report, replay a past storm, or set up a weekly storm alert. Use after a storm, on a weekly schedule, or when asked which accounts were hit.
---

# Storm alerts

```bash
canopy-leads alert runs/<county>                 # last 7 days
canopy-leads alert runs/<county> --days 14 --km 3
canopy-leads alert runs/<county> --start 2024-05-16 --end 2024-05-18   # replay a past storm
```

Reports come from NWS Local Storm Reports for the county's offices (`nws_offices` in
county.yaml) via the Iowa Environmental Mesonet archive. Only tree- and grounds-relevant
reports are kept: wind damage, tornadoes, ice damage, tropical damage, gusts of 50+ mph, hail
of 1.75+ in, and remarks mentioning trees. Each property in `output/alert_points.csv` within
the radius is listed, highest priority (damage report within 2 km) and score first.

Outputs in `output/alerts/`: `alerts_<date>.csv` (one row per account, the call list),
`alerts_<date>_sites.csv` (every property hit) and `alert_log.csv` (each report/property pair
once, so weekly runs only surface what's new).

## After a run

Summarize for the user: how many reports, how many accounts and properties within range,
and the top 10 accounts with the report type, distance, nearest property and best contact.
Suggest a short, helpful talk track ("NWS logged tree damage 1 km from <property> on
<date>; we're doing free storm walks this week"). Do not send anything.

## Weekly schedule

Offer to schedule it (every Monday morning) with whatever scheduler the user has: a Claude
Code scheduled task, cron, or a calendar reminder to run the command. Create the schedule
only after the user says yes, and tell them where it lives and how to stop it.
