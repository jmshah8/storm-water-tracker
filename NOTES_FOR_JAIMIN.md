# Notes for Jaimin

- 2026-09-16: Netlify credits remaining at start: 285 of 300 (2026-09-16). Jaimin reports the 30-day billing cycle has just started, so 15 credits were already used this cycle before any Storm Water Tracker deploy.
- 2026-09-16: Scaffold created.
- 2026-09-16: `python3` on this Mac is pyenv's 3.11.7; Python 3.12.14 was installed with Homebrew and the `.venv` is built with `python3.12`. Added `.venv/` to `.gitignore` (not in the step 1.1 list) so the virtualenv the plan creates in the repo root is never committed.
- 2026-09-16: Another Netlify site on the same team (`anticipationdesk`) is connected to Git, so its pushes trigger 15-credit production deploys that come out of the same 300-credit monthly pool.
- 2026-09-16: Step 1.2 — all ten feeds resolved (total 14,200 overflows). Southern's and Wessex's `licenseInfo` is a longer sentence ("… © 2026 by Southern Water is licensed under CC BY 4.0", "… © 2024 by Wessex Water is licensed under CC BY 4.0") rather than "Licensed under CC BY 4.0"; still CC BY 4.0. ST Connect: empty `licenseInfo`, 1 record (placeholder feed), as the spec expected.
- 2026-09-17: Step 1.4 — first live collection; `launch_utc` = 2026-09-17T00:49:00Z. **Method page note:** events with `start_utc` earlier than `launch_utc` are only "the most recent event per overflow at launch", not a complete record (the seeded events go back to 2020-01-31 for overflows that have not spilled since). The site must not show league tables or monthly counts for any period before September 2026, and must label September 2026 "partial (from 17 Sep 2026)".
- 2026-09-17: Anglian's feed returns overflow `AWS00528` twice (two identical records, ObjectId 966 and 967). The collector processes the first record per `overflow_key` and logs `duplicate_id_records_skipped` (plus `duplicate_id_records_differing` if a duplicate ever differs), so overflows = 14,199 against the feed's count of 14,200.
- 2026-09-17: 15 Severn Trent `ReceivingWaterCourse` values end with a line break (e.g. `'FORD BROOK\n'`). Kept verbatim (CSV-quoted), which is why `wc -l data/overflows.csv` is 15 higher than the row count. Templates will need to trim it for display.
- 2026-09-17: RESOLVED (GATE 1, Jaimin): 5 United Utilities records have `LatestEventEnd` earlier than `LatestEventStart` while `Status = 0` (e.g. UUP00604: start 12 Sep 2026 07:10 UTC, end 10 Sep 2026 09:19 UTC). Decision: leave `end_utc` (and `duration_min`, `end_observed`) empty when the feed's end precedes the start; the collector logs `ends_before_start_left_empty`. The 5 already-collected rows were corrected. Such an event looks "ongoing" in the CSV until a newer event infers its end, so the site should not describe these as ongoing spills. Starts (all the rule uses) are unaffected. Jaimin will ask United Utilities about it — draft email below.
- 2026-09-17: RESOLVED (GATE 1, Jaimin): 14 Wessex records are `Status = -1` (offline) with no `StatusStart`; their offline periods have an empty `offline_start_utc` (filed under the month first observed). Decision: when a monitor comes back online and the feed gives no `StatusStart`, close the period at the time our collector saw it back, labelled in a new column `offline_end_source` = `collector` (`feed` when the time came from the feed's `StatusStart`).
- 2026-09-17: RESOLVED (GATE 1, Jaimin): repository growth. Decision: no per-overflow `observed_utc` in `status_snapshot.json`, so a poll commits only when something real changes. Measuring the fix showed two more causes of the same churn, removed under the same decision: (1) almost every company re-stamps `LastUpdated` on every record at every refresh (13,101 of 14,199 changed in 80 minutes with nothing else changing), so `last_updated_ms` is no longer stored and does not update `last_seen_utc`; (2) United Utilities and Northumbrian add random milliseconds to unchanged times on every refresh (e.g. 1787909680000 → 1787909680300), so snapshot times are stored cut to whole seconds (the CSVs were already whole seconds). The snapshot now holds only `status`, `status_start_ms`, `latest_event_start_ms`, `latest_event_end_ms`. Consequence for step 1.11: the footer's "last poll" time cannot come from a data file (a quiet poll writes nothing); it has to come from the poll workflow's latest run.

## Draft email to United Utilities (for Jaimin to send)

Subject: Storm overflow data feed: 5 records where the latest event ends before it starts

Hello,

I use the storm overflow activity data that United Utilities publishes through the National Storm Overflow Hub (Stream), ArcGIS item 8225548a267f4a408c36a91b6e0f5a1c, "United_Utilities_Storm_Overflow_Activity" feature service.

In that feed, five overflows currently have a LatestEventEnd that is earlier than their LatestEventStart, while their Status is 0 (Stop). Times below are UTC, converted from the feed's epoch-millisecond values (checked on 17 September 2026 at 02:08 UTC):

1. UUP00604 (The Lune Estuary, via Mill Race culvert): LatestEventStart 12 Sep 2026 07:10:00 (1789197000000); LatestEventEnd 10 Sep 2026 09:19:00 (1789031940000); StatusStart 10 Sep 2026 09:19:00.
2. UUP00667 (Manchester Ship Canal): LatestEventStart 29 Jul 2025 16:21:00 (1753806060000); LatestEventEnd 29 Jul 2025 13:06:00 (1753794360000); StatusStart 18 Aug 2025 19:32:00.
3. UUP01453 (River Goyt): LatestEventStart 4 Apr 2025 11:08:00 (1743764880000); LatestEventEnd 27 Jan 2025 03:00:00 (1737946800000); StatusStart 4 Apr 2025 13:02:00.
4. UUP01489 (Arrowe Brook): LatestEventStart 3 Sep 2026 22:22:00 (1788474120000); LatestEventEnd 29 Aug 2026 22:40:00 (1788043200000); StatusStart 15 Sep 2026 05:12:00.
5. UUP02258 (TRIB TROUT BECK): LatestEventStart 15 Sep 2026 21:20:00 (1789507200000); LatestEventEnd 15 Sep 2026 06:02:00 (1789452120000); StatusStart 15 Sep 2026 22:36:00.

Could you tell me:
- whether LatestEventStart or LatestEventEnd is the correct value for each of these, and when each latest event actually ended; and
- whether this is a known issue with the feed, and whether it will be corrected.

Until I hear back, I am recording the start times as published and leaving the end times blank for these five.

Many thanks,
Jaimin Shah
- 2026-09-17: Step 1.7 — rainfall pipeline. The Hydrology API lists 995 rainfall stations; all 995 have a 15-minute measure and coordinates (EA status: 971 Active, 19 Closed, 5 Suspended), so gauges.csv has 995 rows. **Observed lag** (run at 11:52 UTC on 17 Sep): 782 gauges already had a complete day for yesterday (16 Sep) and 777 of 995 gauges had all 96 readings for 14 Sep. That is about half a day behind, not the ~2 days the spec saw on 15 Sep; the 72-hour pending period in §5.3 still covers it comfortably.
- 2026-09-17: 196 of the 995 gauges returned no readings at all for 2–16 Sep (172 marked Active plus the 19 Closed and 5 Suspended); e.g. Garrigill Noonstones Hill's latest reading is 18 Aug 2026. They stay in gauges.csv but will simply never be chosen for an event, because §5.3 picks the nearest gauge with enough readings.
- 2026-09-17: The 02:30 UTC reading on 15 Sep 2026 is missing from almost every gauge (690 gauges have 95 readings that day; checked live, the slot is absent from the API, not dropped by us). 95 readings is still a complete day (≥ 88), but any event whose 48-hour window includes 15 Sep can have at most 191 of 192 readings, so it becomes final only by the 14-day rule in §5.3.
- 2026-09-17: The Hydrology API refuses some requests with 403 Forbidden under load, and serves the same URL normally moments later. The first run (5 requests/second, 5 in parallel, no retry on 403) lost 301 of 995 gauges; `rain.py` now retries 403/429 three times with backoff like a 5xx, and the second run fetched 993 of 995 (the 2 failures succeeded when fetched on their own). Gauges that still fail keep their previous rows and are listed in the run log.
- 2026-09-17: Daily rain files and gauges.csv keep a row's previous `fetched_utc` when nothing else in the row changed (same reasoning as the collector's quiet snapshot: otherwise every daily run would rewrite all fifteen files just to change timestamps). Gauge-days with no readings at all get no row.
