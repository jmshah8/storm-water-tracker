# 01 — Specification: Storm Water Tracker

Everything in this file was verified against the live sources on 15 September 2026 unless marked *unverified*. Where a source could change (feed URLs, field names), the build plan includes a step that re-verifies it before code depends on it.

---

## 1. Purpose and scope

**Purpose.** Record every storm-overflow discharge published by the ten English water and sewerage companies, join each discharge to Environment Agency rainfall, and flag discharges that began on a "dry day" under the EA's definition — showing the evidence for every flag, so that anyone can reproduce the result.

**Audience.** Jaimin only (personal project). The site is still built to a professional standard because the method must survive scrutiny if it is ever shown to anyone.

**In scope.** England's storm overflows (the National Storm Overflow Hub, ~14,187 overflows, ten companies). Rainfall from EA gauges (phase 1) and Met Office radar (phase 2). Thames Water history from April 2022 (phase 3).

**Out of scope.** Wales and Scotland (different legal duties and feeds; Scotland noted as a future port). Emergency overflows. River water-quality data. Any prediction. Any alerting/notifications. Any user accounts.

---

## 2. Sources

### 2.1 Discharge events — National Storm Overflow Hub (via Stream)

- **What it is.** Water UK's map and data feeds for "all 14,187 storm overflows in England" (Water UK release, 22 Nov 2024). Hosted on Stream (streamwaterdata.co.uk). The data is published under a legal duty: Environment Act 2021 s.81 inserted s.141DA into the Water Industry Act 1991 — a company "must publish" that a discharge has occurred, its location, "when the discharge began" and "when the discharge ended"; start information "must be published within an hour of the discharge beginning". Fully in force 1 January 2025.
- **Landing page.** https://www.streamwaterdata.co.uk/pages/the-national-storm-overflow-hub
- **Data page (one card per company).** https://www.streamwaterdata.co.uk/pages/storm-overflows-data
- **FAQ.** https://www.streamwaterdata.co.uk/pages/storm-overflows-faqs
- **Licence.** CC BY 4.0 for every company whose ArcGIS item carries a `licenseInfo` (verified for Thames, Anglian, South West, Southern, Wessex; ST Connect's is empty). Attribute as: "Storm overflow data: [Company] via the National Storm Overflow Hub (Stream), CC BY 4.0." CHECK 1.2 prints each `licenseInfo`; an empty or different one is reported, not treated as a code failure.
- **Access.** Public ArcGIS Feature Services. No API key was required to read the Thames and Anglian services on 15 Sep 2026. Treat "no key needed" as verified-in-practice, not guaranteed.

**The ten company datasets** (Stream dataset IDs from the data page; each resolves to an ArcGIS item of the same ID):

| Company | Stream dataset ID (= ArcGIS item ID) |
|---|---|
| Anglian Water | `333c5c0600f94757b134b276ac4ad8b0` |
| Northumbrian Water | `2d91e4a41b884c9a9dd58dec4ee49b75` |
| Severn Trent Water | `9c5edb37e19044738373137ac76feea2` |
| Southern Water | `7f5ee61ab15d4c79a3f708ccf448a810` |
| South West Water | `cabfce76b72a4a278a33d737c0708d42` |
| Thames Water | `216f455c4435450693cf1d0d0ecf6023` |
| United Utilities | `8225548a267f4a408c36a91b6e0f5a1c` |
| Wessex Water | `632885799ff946cd86200f07b7f175fb` |
| Yorkshire Water | `7f575862a2254a4aaba62573e1012731` |
| ST Connect (Severn Trent's second licence area) | `63295ca00e8741fd9d0cd02bd5301d9d` |

**How to resolve a dataset ID to a query URL** (verified for Thames and Anglian):
1. `GET https://www.arcgis.com/sharing/rest/content/items/{ITEM_ID}?f=json` → read `url` (a `.../FeatureServer` URL) and `licenseInfo`.
2. Layer 0 is the overflow layer: `GET {url}/0?f=pjson` → confirm the fields below.
3. Query: `GET {url}/0/query?where=1%3D1&outFields=*&returnGeometry=false&f=json&resultOffset={n}&resultRecordCount={maxRecordCount}` and page with `resultOffset` until `exceededTransferLimit` is absent/false. `supportsPagination` is true for both verified services.

Verified examples (15 Sep 2026):
- Thames: `https://services2.arcgis.com/g6o32ZDQ33GpCIu3/arcgis/rest/services/Thames_Water_Storm_Overflow_Activity_(Production)_view/FeatureServer` — layer 0 `maxRecordCount` 2000; `licenseInfo` "Licensed under CC BY 4.0".
- Anglian: `https://services3.arcgis.com/VCOY1atHWVcDlvlJ/arcgis/rest/services/stream_service_outfall_locations_view/FeatureServer` — layer 0 `maxRecordCount` 1000; CC BY 4.0.
- South West Water: `https://services-eu1.arcgis.com/OMdMOtfhATJPcHe3/arcgis/rest/services/NEH_outlets_PROD/FeatureServer` — **camelCase field names** (`status, statusStart, latestEventStart, latestEventEnd, longitude, latitude, receivingWaterCourse, lastUpdated, company`, plus `Id`); `maxRecordCount` 2000; CC BY 4.0.
- ST Connect: `https://services-eu1.arcgis.com/zat3uNEZelYVksuM/arcgis/rest/services/STREAM_Data/FeatureServer` — uses **`LatestEventFinish`** instead of `LatestEventEnd`, has an extra `GlobalID`, an **empty `licenseInfo`**, and exactly **1 record** (a placeholder feed). Collect it anyway; report it as-is.

**Field names are NOT identical across the ten services.** `sources.py` must normalise field names **case-insensitively** and accept these aliases: `LatestEventEnd` ⇐ {`LatestEventEnd`, `latestEventEnd`, `LatestEventFinish`}; every other logical field ⇐ its case-insensitive match. The resolved alias map per company is written into `sources_resolved.json` and CHECK 1.2 prints it. A company whose fields cannot be mapped → GATE 0.

**Layer 0 logical fields (canonical spelling as on Thames/Anglian; other companies may differ in case):**

| Field | Type | Meaning |
|---|---|---|
| `Id` | string | Company's overflow identifier (the stable key) |
| `Company` | string | Company name as the company writes it |
| `Status` | integer, coded | `1` = Start (discharging now), `0` = Stop (not discharging), `-1` = Offline (monitor not reporting) |
| `StatusStart` | date (epoch ms UTC) | When the current Status began |
| `LatestEventStart` | date (epoch ms UTC) | Start of the most recent discharge event |
| `LatestEventEnd` | date (epoch ms UTC) | End of the most recent discharge event; null while ongoing |
| `Longitude`, `Latitude` | double | WGS84 |
| `ReceivingWaterCourse` | string | Named river/sea/etc. |
| `LastUpdated` | date (epoch ms UTC) | Company's last update of this record |
| `OBJECTID` / `ObjectId` | OID | Internal; ignore |

**Cadence.** FAQ: "For the purposes of publishing EDM data, near real-time means within the hour." and "all monitors take measurements at least every 15 minutes". Thames metadata: refreshed every 5 minutes; Anglian: every 60 minutes.

**History.** None. FAQ: "The Hub does not have access to data from before its date of publication." The feed exposes only the latest event per overflow. **Therefore the archive is built forward by polling.** Company feeds began between 1 Nov 2024 (Anglian) and 1 Jan 2025.

**Audit status.** Data page: "Data provided on the map and in the API is near real-time data and has not undergone an audit process required to comply with the Environment Agency regulatory EDM Annual Return dataset." This caveat must appear on the Method page.

### 2.2 Rainfall — EA Hydrology API (primary rainfall source)

- **Reference.** https://environment.data.gov.uk/hydrology/doc/reference — licence OGL v3.
- **Why this and not the real-time flood-monitoring API.** The Hydrology API serves 15-minute rainfall totals with long history, returns up to 2,000,000 rows per call, outputs CSV, and needs no key. The real-time API keeps only ~4 weeks. Trade-off: the Hydrology API lags. On 15 Sep 2026 the latest reading for a sample gauge was `2026-09-13T00:15:00` (about two days behind), quality `Unchecked`. This lag defines the site's "confirmed" delay (§5.6).
- **Stations.** `GET https://environment.data.gov.uk/hydrology/id/stations?observedProperty=rainfall&_limit=5000` → items with `@id`, `notation`, `label`, `lat`, `long`, `easting`, `northing`, `stationReference`, `dateOpened`, `measures[]`.
- **Measures.** Use the 15-minute total: measure `@id` ends with `-rainfall-t-900-mm-qualified` (period 900 s, unit mm, valueType total). Listing: `GET https://environment.data.gov.uk/hydrology/id/measures?observedProperty=rainfall&periodName=15min&_limit=5000`.
- **Readings.** `GET https://environment.data.gov.uk/hydrology/id/measures/{measure_notation}/readings?mineq-date=YYYY-MM-DD&max-date=YYYY-MM-DD&_limit=100000` (or `.csv` / `_format=csv`). Items: `dateTime` (ISO, **no timezone marker**), `value` (mm), `quality` (e.g. `Unchecked`, `Good`). `mineq-date` is inclusive, `max-date` exclusive.
- **Timezone assumption.** The Hydrology API's `dateTime` carries no zone. The EA's real-time API uses `Z` (UTC). **We treat Hydrology `dateTime` as UTC.** Step 1.8 in the build plan verifies this by comparing one gauge-day across the two APIs before any classification runs.
- **Polite use.** No published rate limit. Pace requests at ≤ 5 per second; one call per measure per day covering a rolling 4-day window.

### 2.3 Rainfall — EA real-time flood-monitoring API (optional, not used in v1)

https://environment.data.gov.uk/flood-monitoring/doc/rainfall — "approximately 1000 real time rain gauges"; 15-min totals; "typically transfered once or twice per day" (sic); OGL, no registration; ~4-week window; measure IDs like `E7050-rainfall-tipping_bucket_raingauge-t-15_min-mm`. Kept in reserve for a "provisional same-day" mode. Note: some stations are stale (E7050's latest reading on 15 Sep 2026 was from 23 Jun 2026), so never assume a gauge is live.

### 2.4 Context only — EA Event Duration Monitoring annual returns

https://www.data.gov.uk/dataset/19f6064d-7356-466f-844e-d20ea10ae9fd/event-duration-monitoring-storm-overflows-annual-returns — zips for 2020–2025, OGL. Annual spill counts and hours per overflow; **no per-event timestamps**, so unusable for dry-day classification (Commons Library CBP-10027: "there is at present no way to distinguish 'dry spills' … within this dataset"). Used only on the Method page as context and, optionally, to sanity-check our per-overflow annual counts against the official ones.

### 2.5 Radar — Met Office UK composite (phase 2)

- **Registry.** https://registry.opendata.aws/met-office-uk-radar-observations/ — "Four images per hour (every 15 minutes). The data is available within 20 minutes of the validity time of the product." 2-year rolling archive. Licence: "British Crown copyright 2024-2025, the Met Office, is licensed under CC BY-SA".
- **Bucket.** `s3://met-office-radar-obs-data` (region `eu-west-2`), public, `--no-sign-request`. Key pattern verified: `radar/YYYY/MM/DD/YYYYMMDDHHMM_ODIM_ng_radar_rainrate_composite_1km_UK.h5` (~1.3–1.5 MB each, 96 per day). Oldest key seen on 15 Sep 2026: `radar/2024/11/21/...`.
- **Format.** ODIM_H5 (HDF5). The quantity is a surface rain **rate** (mm/h); a 15-minute accumulation = rate × 0.25. Grid: 1 km UK composite. Projection, gain/offset, `nodata`/`undetect` values must be read from the file's `where`/`what` attributes at runtime (phase 2, step 2.2) — do not hard-code them.

### 2.6 Thames Water API (phase 3)

- **Portal.** https://data.thameswater.co.uk/ (register at `/s/apis`, create credentials at `/s/application-listing` — per a third-party guide; *unverified against the portal itself*, which did not render for us).
- **Base URL and endpoints** (from two independent open-source clients; *unverified directly*): `https://prod-tw-opendata-app.uk-e1.cloudhub.io/data/STE/v1/DischargeCurrentStatus` and `.../DischargeAlerts`. Auth headers: `client_id`, `client_secret`. Query params: `limit` (max 1000 per call), `col_1`/`operand_1`/`value_1` (filter, e.g. `col_1=DateTime&operand_1=gte&value_1=2022-04-01`). Response: `{"items": [...]}` with fields including `LocationName`, `AlertType`, `AlertStatus`, `DateTime`, `ReceivingWaterCourse`, `X`, `Y` (likely OSGB36 easting/northing) — confirm by inspecting a live response in step 3.2.
- **History.** Third-party reports: alert stream available from 1 April 2022. Confirm in step 3.1.
- **Timezone of `DateTime`.** Unknown. Step 3.1 determines it empirically by comparing overlap events against the Hub's epoch-ms timestamps (test offsets of 0 and ±60 minutes; the correct one matches within a few minutes). A wrong assumption would shift events across UTC-day boundaries and change verdicts, so this is a GATE if ambiguous.

### 2.7 Prior art (for the About/Method pages, not for data)

- River Truth (Nexfort Data Ltd) — https://rivertruth.co.uk/ — already flags "dry-weather spills" per event with the rule "effectively no rainfall in the preceding 24 h" (their words). Different rule from the EA's; no published threshold or rainfall source; ~1 week of history visible. This site differs by using the EA's exact rule, archiving forward, and publishing per-company totals and a CSV.
- Top of the Poops — https://top-of-the-poops.org/ — annual EDM data plus live feeds; rainfall shown as aggregate; "Rainfall data is delayed by up to two days."
- Rivers Trust sewage map; Surfers Against Sewage Safer Seas & Rivers Service — spills, not dry-day classification.

---

## 3. Data model (all committed CSVs; UTF-8; `\n`; header row; sorted by the stated key)

### 3.0 `data/meta.json`
`{"launch_utc": "<ISO Z or null>", "rule_version": "dry-day-v1", "site_url": "https://<netlify-site-name>.netlify.app/"}`. `launch_utc` is set once by the first live `collect.py` run and never changed. `site_url` is set at step 0.2 once the Netlify project exists.

### 3.1 `data/overflows.csv` — one row per overflow ever seen (key: `overflow_key`)
| column | type | notes |
|---|---|---|
| `overflow_key` | string | `{company_slug}:{Id}` |
| `company_slug` | string | one of: `anglian`, `northumbrian`, `severn-trent`, `southern`, `south-west`, `thames`, `united-utilities`, `wessex`, `yorkshire`, `st-connect` |
| `company_name` | string | display name (§8.4) |
| `source_id` | string | the feed's `Id` verbatim |
| `latitude`, `longitude` | float | WGS84, 6 dp |
| `receiving_watercourse` | string | verbatim, may be empty |
| `first_seen_utc`, `last_seen_utc` | ISO Z | |

### 3.2 `data/status_snapshot.json` — last observed record per overflow (for change detection)
Object keyed by `overflow_key` → `{status, status_start_ms, latest_event_start_ms, latest_event_end_ms, last_updated_ms, observed_utc}`. Sorted keys, 2-space indent.

### 3.3 `data/events/YYYY-MM.csv` — one row per discharge event, filed by UTC month of `start_utc` (key: `event_id`)
| column | notes |
|---|---|
| `event_id` | `{overflow_key}:{start_ms}` |
| `overflow_key`, `company_slug` | |
| `start_utc` | ISO Z from `LatestEventStart` |
| `end_utc` | ISO Z from `LatestEventEnd`; empty while ongoing |
| `duration_min` | integer; empty while ongoing |
| `source` | `hub` (phase 1) or `thames_api` (phase 3) |
| `first_observed_utc` | when our poller first saw this event |
| `last_observed_utc` | when our poller last saw it |
| `end_observed` | `true` if we saw the end via the feed; `false` if inferred (§4.4) |

### 3.4 `data/offline/YYYY-MM.csv` — monitor offline periods (key: `overflow_key`,`offline_start_utc`)
Columns: `overflow_key`, `company_slug`, `offline_start_utc` (from `StatusStart` when `Status=-1`), `offline_end_utc` (empty while offline), `first_observed_utc`, `last_observed_utc`.

### 3.5 `data/rain/gauges.csv` — EA Hydrology rainfall stations with a 15-min measure (key: `gauge_id`)
Columns: `gauge_id` (station `notation`), `measure_id` (the `-rainfall-t-900-mm-qualified` notation), `label`, `latitude`, `longitude`, `date_opened`, `fetched_utc`.

### 3.6 `data/rain/daily/YYYY-MM-DD.csv` — per gauge, per UTC day (key: `gauge_id`)
Columns: `date` (UTC), `gauge_id`, `total_mm` (sum of 15-min values), `max15_mm` (largest single 15-min value), `n_readings` (expected 96), `n_unchecked`, `n_good`, `n_other_quality`, `fetched_utc`. A day is **complete** when `n_readings ≥ 88` (≥ 91.7%, i.e. at most 8 missing 15-min slots).

### 3.7 `data/classification/all_events_classified.csv` (key: `event_id`) and `data/classification/dry_day_spills.csv` (subset where `verdict = dry_day`)
| column | notes |
|---|---|
| `event_id`, `overflow_key`, `company_slug`, `start_utc`, `end_utc`, `duration_min`, `source` | copied |
| `day_utc` | UTC calendar date of `start_utc` |
| `window_start_utc`, `window_end_utc` | `day_utc − 1 day 00:00Z` to `day_utc + 1 day 00:00Z` (48 h) |
| `gauge_id`, `gauge_label`, `gauge_distance_km` | chosen gauge (§5.3); empty if none |
| `rain_day_mm` | total on `day_utc` |
| `rain_prev24_mm` | total on `day_utc − 1` |
| `rain_window_total_mm` | sum of the two |
| `rain_window_max15_mm` | max single 15-min reading in the window |
| `n_readings_present`, `n_readings_expected` | expected 192 |
| `verdict` | one of `dry_day`, `not_dry`, `pending_rain_data`, `no_gauge_within_10km`, `insufficient_readings` |
| `verdict_basis` | `total` (see §5.2) |
| `rule_version` | `dry-day-v1` |
| `classified_utc` | |
| `radar_window_total_mm`, `radar_3x3_max_total_mm`, `radar_status` | phase 2; empty in phase 1 |
| `is_final` | `true` once the verdict is final per §5.3 |

Also `data/classification/verdict_changes.csv` (key: `event_id`,`changed_utc`): `event_id, from_verdict, to_verdict, changed_utc, n_readings_present` — every flip between `dry_day` and `not_dry`, for audit.

---

## 4. Collector logic (`scripts/collect.py`)

4.1 For each company: load the Feature Service URL and field-alias map from `scripts/sources_resolved.json` (written by `sources.py`; re-resolve if a query returns 4xx), page through layer 0, and normalise each record to `{overflow_key, status, status_start_ms, latest_event_start_ms, latest_event_end_ms, last_updated_ms, lat, lon, watercourse}` using the alias map. `collect.py` accepts `--now ISO` to fix the clock (used by tests for byte-identical output) and `--fixture PATH` (a JSON file shaped exactly like the ArcGIS query response: `{"features": [{"attributes": {...}}, ...]}` per company, keyed by `company_slug`).

4.2 **Upsert overflows.** New `overflow_key` → append to `overflows.csv` with `first_seen_utc = now`. Update coordinates and watercourse only if changed. `last_seen_utc` is updated only when the overflow's record changed in this poll (so an unchanged feed produces no CSV diff); the per-poll observation time lives in `status_snapshot.json` (`observed_utc`).

4.2a **Guard against silent schema drift.** If any mapped logical field is absent from the first record returned for a company, exit 2 with a message naming the company and field (a renamed field must fail loudly in CI, never produce nulls).

4.3 **Detect events.** Compare against `status_snapshot.json`:
- If `latest_event_start_ms` is non-null: first look for an existing event for the same overflow whose `start_utc` is within ±15 minutes of it (**near-duplicate rule** — companies occasionally re-time a start). If one exists, it *is* this event: keep its `event_id` unchanged (ids are immutable), update its `start_utc` to the feed's current value, and count the re-timing in a run counter reported in the log. If none exists → **new event**: `event_id = {overflow_key}:{latest_event_start_ms}`, `start_utc`, `end_utc` (if `latest_event_end_ms` non-null), `first_observed_utc = now`.
- If an event exists and `latest_event_end_ms` is now non-null and the event's `end_utc` is empty → set `end_utc`, `duration_min`, `end_observed = true`.
- Set `last_observed_utc = now` for the event matching the current `latest_event_start_ms` **only when that event's row changed in this poll** (new, re-timed, or end filled in) — otherwise leave the row untouched so unchanged feeds produce no diff.

4.4 **Inferred ends.** If an overflow's `latest_event_start_ms` moves to a *newer* event while an older event still has empty `end_utc`, set the older event's `end_utc` to the newer event's `start_utc` and `end_observed = false`. (We missed the stop between polls.)

4.5 **Offline.** `Status = -1` → open an offline period from `status_start_ms` if none open; when `Status` returns to 0/1 → close it with `offline_end_utc = status_start_ms` of the new status.

4.6 Write snapshot and the affected month CSVs deterministically. Exit 0 if no changes (the workflow then skips the commit).

4.7 **What we cannot capture** (state on Method page): an event that starts and ends between two polls *and* is followed by another event before the next poll loses the first event. Poll interval is 10 minutes; Thames's feed refreshes every 5 minutes, others hourly, so in practice this is rare.

---

## 5. The rule (`swt/rule.py`, pure function, unit-tested)

5.1 **Source sentence.** "A dry day spill is when a storm overflow is used on a 'dry day' – which is defined as no rainfall above 0.25mm on that day and the preceding 24 hours." (EA, 28 Aug 2024.)

5.2 **Interpretation, `dry-day-v1`.** Let `D` be the UTC calendar day containing the event's `start_utc`. The **window** is the 48 hours from `D−1 00:00Z` to `D+1 00:00Z` ("that day and the preceding 24 hours"). Compute `rain_window_total_mm` = sum of all 15-minute totals in the window at the chosen gauge, and `rain_window_max15_mm` = the largest single 15-minute total.

**Verdict `dry_day` if and only if `rain_window_total_mm ≤ 0.25`.**

Why total, not max-15-min: the sentence is ambiguous between "no single reading above 0.25 mm" and "no more than 0.25 mm of rain". Requiring the *total* to be ≤ 0.25 mm is the stricter reading — it flags fewer events — so it minimises false accusations. Both numbers are stored so the alternative reading can be recomputed. `verdict_basis = total` records which was used.

5.3 **Gauge selection and verdict states.** Candidates = gauges in `gauges.csv` within **10.0 km** (haversine, WGS84) of the overflow, ordered by distance. Choose the nearest candidate whose window has `n_readings_present ≥ 176` (≥ 91.7% of 192); if it exists, verdict is `dry_day` or `not_dry` by §5.2.
Otherwise, in this order:
- no candidate within 10 km → `no_gauge_within_10km` (final);
- `now_utc < window_end_utc + 72 h` → `pending_rain_data` (the Hydrology API lags ~2 days; rain may still arrive). This is decided by **time**, never by whether a daily file exists;
- else → `insufficient_readings` (final unless data later appears; re-checked every run).

**Overflows without coordinates** (empty lat/lon in the feed) → `no_gauge_within_10km`, final.

**Provisional vs final — `is_final` is true in exactly these cases, false otherwise:**
- `no_gauge_within_10km` (always final);
- `dry_day` / `not_dry` with `n_readings_present = 192` **and** `now_utc ≥ window_end_utc + 72 h` (the 72 h prevents locking in a farther gauge while the nearest is still lagging);
- `dry_day` / `not_dry` with any reading count once `now_utc ≥ window_end_utc + 14 days`.
`pending_rain_data` and `insufficient_readings` are never final and are re-evaluated every run. A non-final verdict may change; a final one never changes without `--force` and a rule-version bump. The site shows non-final `dry_day`/`not_dry` verdicts with the "Provisional" sub-line in §5.6. Every change between `dry_day` and `not_dry` is appended to `data/classification/verdict_changes.csv` (columns exactly as §3.7) so flips are auditable. Because the rain pipeline refetches a rolling 15-day window (§6.2), late-arriving readings inside the 14-day provisional period are actually picked up.

5.4 **Time.** Everything in UTC. A "day" is a UTC calendar day. The Hydrology API `dateTime` is treated as UTC (verified in step 1.8). Stated on the Method page as: "We use UTC calendar days. The Environment Agency's definition does not specify a time zone; EDM data is reported in GMT."

5.5 **What is classified.** Every event's **start**. An event that started in rain and continued into a dry day is *not* flagged in v1 (recorded as future work). Events with `source = thames_api` (phase 3) are classified identically.

5.6 **Labels on the site (the only permitted wording; badge text is uppercase in CSS, not in the source).**
- `pending_rain_data` → badge `Rain check pending`; sub-line `Rainfall data for this window is not yet available from the Environment Agency.`
- `dry_day` → badge `Dry day spill · EA definition`; sub-line `Potential breach; not confirmed.` followed by either `Complete rain data (192 of 192 readings).` or `Provisional — rain data {n} of 192 readings.`
- `not_dry` → badge `Not a dry day`; sub-line `Rain recorded in the window: {total} mm.`
- `no_gauge_within_10km` → badge `No gauge within 10 km`; sub-line `Cannot be classified under this method.`
- `insufficient_readings` → badge `Insufficient rain data`; sub-line `Nearest gauges returned fewer than 176 of 192 readings.`
- Expected lag: spill visible within ~1 hour; verdict typically 2–3 days later (Hydrology API lag ≈ 2 days + window end).

5.7 **Versioning.** Any change to §5.2–5.3 requires a new `rule_version` (`dry-day-v2`, …), a Method-page changelog entry, and full re-classification. Never re-classify old events under a new version silently.

---

## 6. Rainfall pipeline (`scripts/rain.py`)

6.1 Weekly (Sunday) refresh `gauges.csv` from the stations endpoint; keep only stations with a `-rainfall-t-900-mm-qualified` measure and valid `lat`/`long`.
6.2 Daily at 06:30 UTC: for each gauge, one request `GET .../readings?mineq-date={D−15}&max-date={D}&_format=csv` (a rolling 15-day window — ~1,440 rows per gauge — so late-arriving data inside the 14-day provisional period is picked up). Aggregate to per-day rows; rewrite `data/rain/daily/{date}.csv` for each of the fifteen days (deterministic; unchanged files produce no diff).
6.3 Values: treat `value` empty/`null` as missing (do not count as a reading). Negative values → missing and counted in `n_other_quality`.
6.4 A gauge-day with `n_readings < 88` is still written (so partial data is visible) but is not "complete".

---

## 7. Design system

**Inspiration.** A dark, near-monochrome landing page: wordmark top-left, sparse nav top-right with one small pill button, a single large sans-serif headline set low-left, a quiet generative visual made of small light dashes on black, a thin rule with a short label and a two-sentence description bottom-right. Calm, serious, no colour noise. This site is an accountability instrument; the design should feel like an instrument panel, not a campaign.

7.1 **Palette (CSS custom properties, single theme — dark only; no toggle).**
```
--bg:        #0b0b0c;   /* page */
--surface:   #121214;   /* cards, table header */
--rule:      #262629;   /* hairlines */
--text:      #ececec;   /* primary */
--muted:     #8b8b90;   /* secondary text, labels */
--faint:     #4a4a4f;   /* dashes in the hero visual, disabled */
--flag:      #d9b26a;   /* the ONLY accent: dry-day markers, one word at a time */
--flag-dim:  #5b4a2a;   /* flag at low emphasis (table stripes, bar strip) — never for text */
--white:     #ffffff;   /* nav pill background, focus ring */
--black:     #000000;   /* nav pill text */
--vignette:  rgba(255,255,255,0.03);  /* hero radial highlight only */
```
Rules: these eleven values are the **only** colour literals allowed in `style.css` and templates (acceptance D4 greps for any other hex/rgb/hsl). `--flag` appears only on dry-day markers, the dry-day count tile, and the dry-day rows' left border. `--faint` and `--flag-dim` never carry text (their contrast is ~2:1). No gradients except the hero vignette (`--vignette` centre → transparent).

7.2 **Typography.** `Inter` from Google Fonts (weights 400, 500), fallback `-apple-system, "Segoe UI", Helvetica, Arial, sans-serif`. Hero headline 56px/1.05 (clamp 36–64px), weight 400, letter-spacing −0.01em. Body 16px/1.55. Labels: 12px, uppercase, letter-spacing 0.08em, `--muted`. Numbers in tables: `font-variant-numeric: tabular-nums`. No italics. No bold heavier than 500.

7.3 **Layout.** Max width 1200px, 24px side padding (16px on phones), 12-column grid on desktop collapsing to single column ≤ 720px. Generous vertical rhythm (section padding 96px desktop / 56px mobile). Hairline rules (`1px solid var(--rule)`) separate sections; no boxes with heavy borders; cards are `--surface` with 1px `--rule` border and 8px radius at most.

7.4 **Navigation.** Left: wordmark `storm water tracker` in Inter 500, 18px, with a small 16×16 monochrome glyph (four short horizontal dashes of decreasing length — an abstract "rain/sewer" mark drawn as inline SVG). Right: `Overview · Companies · Events · Method` as plain links (to `index.html`, `companies/index.html`, `events/index.html`, `method.html`); a small pill `DATA ↗` (white background, black text, 12px uppercase) linking to the Data page. `About` is linked from the footer only. Active link has a 4px dot before it (as in the inspiration). Nav is 72px tall, transparent over the hero, `--bg` elsewhere.

7.5 **Hero (Overview page only).** Full-viewport-height (min 640px) black section. Left-bottom: headline `Spilling when it isn't raining.` and, beneath it in `--muted` 18px: `Every storm-overflow discharge in England, checked against Environment Agency rainfall using the EA's own dry-day definition.` Right-bottom: a thin rule, then label `ENGLAND · {N} STORM OVERFLOWS` where `{N}` is the row count of `data/overflows.csv` at build time (not a hard-coded figure), then two sentences: `Companies must publish each discharge within an hour. We record them all and flag the ones that started on a dry day. Evidence shown for every flag.` Centre-right, behind the text: the **hero visual** — England drawn as ~4,000 tiny horizontal dashes (1×3px, `--faint`) at overflow coordinates (generated SVG `static/england-overflows.svg`, ≤ 400 KB). Dashes at overflows with a `dry_day` verdict in the last 30 days are `--flag` and 1×5px. No animation beyond a 600 ms opacity fade-in on load (`prefers-reduced-motion` respected).

7.6 **Components.**
- *Stat tile*: label (12px uppercase muted) over a 40px tabular number, hairline top border. Four in a row on desktop, 2×2 on mobile.
- *League table*: company, overflows, events (period), dry-day spills (period), dry-day per 100 overflows, last dry-day. Sortable by clicking headers (vanilla JS). Dry-day count cell in `--flag`.
- *Event row / event page*: left 2px border `--flag` for dry-day; monospace-free — keep Inter; fields as a definition list with muted labels.
- *Verdict badge*: 12px, `text-transform: uppercase`, text exactly as §5.6; `dry_day` badge in `--flag` on `--surface`; all other badges in `--muted` on `--surface`; the §5.6 sub-line beneath in 14px `--muted`.
- *Footer*: hairline, then three muted lines: data timestamps (last poll, last rain fetch, last classification), attribution lines (§2.1 and §2.2 in Phase 1; add §2.5's Met Office line in Phase 2), a link to About, and "A personal project. Not affiliated with any water company, regulator or campaign."

7.7 **Copy rules.** Sentence case for headings except labels. British English. Numbers with thin-space thousands separators (`14 187`) in prose, plain in tables. Never the word "illegal" (see CLAUDE.md). Dates as `15 Sep 2026, 14:05 UTC`.

7.8 **Accessibility.** Contrast ≥ 4.5:1 for all text on `--bg`/`--surface` (`--muted` on `--bg` ≈ 5.8:1; `--flag` on `--bg` ≈ 9.9:1; `--text` on `--bg` ≈ 17:1 — step 1.13 verifies these with a script, do not trust these figures). Focus rings visible (`outline: 2px solid var(--text)`). Tables have `<th scope>`; the hero SVG has `role="img"` and an `aria-label`.

---

## 8. Pages (static HTML in `site/`)

8.1 `index.html` — hero; four stat tiles (Dry day spills · last 30 days / Dry day spills · this year / Events recorded · last 30 days / Overflows tracked); league table for the last 30 days with a toggle to "this year" (both tables in the HTML, JS only toggles visibility); "Latest dry day spills" list (20 most recent, linking to event pages); a short "How this works" block (four sentences + link to Method); footer.

8.1a `companies/index.html` — the league table for the last 30 days and for this year (both rendered in the HTML; a vanilla-JS toggle shows one at a time; no fetching), each row linking to the company page. `events/index.html` — all `dry_day` and `pending_rain_data` events, newest first, 200 per page (`index.html`, `index-2.html`, …), each linking to its event page; a link to the full CSV for everything else.

8.2 `companies/{company_slug}.html` — company name, overflows count, monthly table (month, events, dry-day spills, dry-day per 100 overflows, complete-rain-data share), full list of dry-day spills for the company (paginated 100 per page as `-2.html`, `-3.html` …), link to CSV filtered by company.

8.3 `events/{event_id_safe}.html` — **only for events with `verdict = dry_day` or `pending_rain_data`** (all events are in the CSV). `event_id_safe` = `event_id` with every character outside `[A-Za-z0-9_-]` replaced by `_`; if two events collide after slugging, append `-2`, `-3` … deterministically (sorted by `event_id`). The build fails loudly if a collision cannot be resolved. Shows: verdict badge; overflow ID, company, watercourse, coordinates (6 dp) with a link to OpenStreetMap at that point (plain link, no embedded map); start/end/duration; the rain evidence table (gauge, distance, rain on day, rain previous 24 h, window total, window max 15-min, readings present/expected, quality mix); rule text verbatim; rule version; classified time; a "Reproduce this" block giving the exact Hydrology API URL for the gauge and window; phase-2 radar block when available.

8.4 **Company display names**: Anglian Water, Northumbrian Water, Severn Trent Water, Southern Water, South West Water, Thames Water, United Utilities, Wessex Water, Yorkshire Water, ST Connect. (Use the feed's `Company` string only to sanity-check the mapping.)

8.5 `method.html` — in this order: the EA sentence verbatim with link and date; how we implement it (§5.2–5.6 in plain English); why "total ≤ 0.25 mm" was chosen and what the alternative would give; gauge matching and the 10 km assumption; the UTC assumption (with the date of the BST-day verification from step 1.8); provisional vs final verdicts; the lag; what we can miss (§4.7); the launch-date caveat ("Our complete record begins on {launch date}; events before it are only the most recent event per overflow at launch"); the ST Connect placeholder feed (one record); overflows without coordinates (count); the Hub's own "not audited" caveat verbatim; sources list (all of `06_SOURCES.md`, each with link, date fetched, and quote); the rule changelog; the prior-art paragraph (§2.7) written neutrally.

8.6 `data.html` — download links for every CSV in `data/classification/` and `data/events/`, `data/overflows.csv`, `data/rain/gauges.csv`, and (phase 3) `data/thames_history/*.csv`; the build step copies exactly these files into `site/data/` (not the daily rain or radar files — the event pages' "Reproduce this" links point at the EA API for those); the column dictionary (§3); licence and attribution (site content CC BY 4.0; upstream licences as §2).

8.7 `about.html` — three short paragraphs: what this is (a personal project by one person), why (the EA's own dry-day count is only released by FOI; the public dataset cannot distinguish dry spills), and what it is not (not affiliated, not an alert service, not legal findings).

8.8 Every page: `<title>` `Storm Water Tracker — {page}`; meta description; `<meta name="robots" content="noindex">` (personal site; Jaimin can remove later); canonical link built from `data/meta.json.site_url` (e.g. `https://storm-water-tracker.netlify.app/`); no external scripts except Google Fonts CSS. **All internal links and asset paths are relative** (`../static/style.css`, never `/static/style.css`) so the same build works at the production URL, at the daily alias URL and when opened locally; CHECK 1.11(b) rejects any root-relative `href`/`src`.

8.9 (Phase 3) `thames-backtest.html` is linked from the Thames company page (a "Back-test to April 2022" link under the company name) and from the Method page's sources section. The nav does not change.

---

## 9. Hosting and automation

**Split of responsibilities.** GitHub (public repository + Actions) does all the work: collecting, rainfall, classification, radar, building the static site. **Netlify only serves the built site**, as a **private** project that requires Jaimin's Netlify login, and it is deployed to on a strict credit budget. The two are never linked by Netlify's Git integration.

9.1 **GitHub repository `storm-water-tracker`, public** (public repos get unlimited free Actions minutes; the poller alone uses ~4,000 minutes/month, above the 2,000-minute private-repo allowance). The repo holds only open data and code; the site's privacy is enforced by Netlify, not by the repo. Secrets (Netlify token and site ID; Thames API credentials in phase 3) live only in GitHub Actions secrets and, for local runs, a git-ignored `.env`.

9.2 **Netlify hosting — verified against Netlify's docs on 16 Sep 2026.**
- **Privacy.** Netlify project visibility: "A project can be public (anyone with the URL can view it), private (only your team and people you invite can view it), or password protected (public, but requires a shared password to view)." "Private projects are enforced with Netlify login". "On a Free and Personal plan, private projects can only be seen by the Team Owner." Production deploys and previews are set separately — **both are set to Private**. Visitors without access "see a Netlify-branded page explaining they don't have access". Password protection is Pro-only and is not used. Setting: Project configuration → General → Visitor access → Project visibility. (https://docs.netlify.com/manage/security/secure-access-to-sites/project-visibility/)
- **Credits (Free plan).** 300 credits/month, hard limit, no top-ups, reset each billing cycle. A **production deploy costs 15 credits**; "Deploy Previews/branch deploys" are listed at 0 credits; bandwidth 20 credits/GB; web requests 2 credits per 10,000. When the balance hits zero, "all of your web projects (sites/apps) are paused" until the reset — this affects every site on the account, not just this one. (https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work/)
- **The project is a manual-deploy site.** It is created with `netlify sites:create` (or "Deploy manually" in the UI) and is **never connected to the GitHub repository** in Netlify. A Git-connected site would build on every 10-minute data commit — 15 credits each — and exhaust the month in about two hours.
- **Deploys come only from the `deploy-netlify.yml` workflow**, using the Netlify CLI from GitHub Actions with `NETLIFY_AUTH_TOKEN` and `NETLIFY_SITE_ID` in the environment: `npx netlify-cli@<pinned major> deploy --dir=site --no-build --json --message "..." [--prod | --alias daily]` (reference YAML in `02_PHASE1_BUILD_PLAN.md` step 1.15a). (`--prod` "Deploy to production"; without it the CLI "Creates a draft deploy by default"; `--alias` gives "predictable deployment URLs" of the form `https://<alias>--<site>.netlify.app`; `--no-build` because the site is already built. https://cli.netlify.com/commands/deploy/)
- **Credit budget rules, enforced in the workflow, not by memory:**
  1. **Production deploys: at most 8 per calendar month** (= 120 credits, leaving ≥ 180 for bandwidth/requests and the other site on the account). The workflow keeps `data/deploy_log.json` (`[{utc, kind: prod|alias, run_url, message, deploy_url}]`, sorted by `utc`), committed after each deploy; before a production deploy it counts this month's `prod` entries and **refuses** (exit 1, clear message) at 8 unless the manual input `override_budget: true` is given.
  2. **One scheduled production deploy a week** — Monday 08:00 UTC (after the 06:30 rain run and the 07:15 classify run). That is 4–5 a month, leaving 3–4 for manual "major update" deploys via `workflow_dispatch` (input `kind: prod`).
  3. **Fresh data daily at a fixed preview URL, only if it is free.** A daily alias deploy (`--alias daily` → `https://daily--<site>.netlify.app`, private like everything else) at 08:00 UTC Tue–Sun. Step 1.15b measures its credit cost by reading the account's *credits remaining* in the Netlify UI before and after each of two alias deploys; the daily alias job is enabled **only if neither deploy moved the balance**, otherwise its cron stays disabled and the site updates weekly.
  4. **Never** deploy from a laptop with `--prod`; never enable Netlify's Git integration, build hooks, or "auto publishing"; never add Netlify Functions, Forms, Identity, Blobs or any other Netlify feature (they consume credits and are not needed for a static site).
  5. The classify job **does not deploy**. It commits classification CSVs hourly; the site on Netlify is whatever the last production (or alias) deploy contained.
- **Bandwidth.** The built site is small (tens of MB including CSVs); a single private viewer uses a few MB a month. If `site/` grows past 100 MB (Phase 3 CSVs), gzip the large CSVs and link the `.gz`.

9.3 **Workflows.**
- `poll.yml` — `schedule: cron: "*/10 * * * *"` + `workflow_dispatch`. Steps: checkout (fetch-depth 1), Python 3.12, `pip install -r requirements.txt`, `python scripts/collect.py`, then commit-if-changed (`git add data && git diff --cached --quiet || git commit -m "poll: $(date -u +%FT%TZ)" && git push`). `concurrency: {group: data-writers, cancel-in-progress: false}`. Timeout 8 minutes.
- `rain.yml` — `cron: "30 6 * * *"` + manual. Run step: `python scripts/rain.py --days 15 $([ "$(date -u +%u)" = 7 ] && echo --refresh-gauges)` (Sundays also refresh the gauge list). Same concurrency group and commit pattern.
- `classify.yml` — `cron: "15 * * * *"` (hourly) + `workflow_run` (`workflows: [rain]`, plus `radar` from phase 2 — `workflow_run` keys on the workflow *name*) + manual. Runs `classify.py` and commits classification CSVs (concurrency group `data-writers`). **No deploy.**
- `deploy-netlify.yml` — `schedule` Monday 08:00 UTC (production) and, only if enabled at step 1.15b, Tue–Sun 08:00 UTC (alias) + `workflow_dispatch` with inputs `kind` (`alias` | `prod`, default `alias`) and `override_budget` (boolean, default false). `KIND` is derived in the workflow `env` (schedule `0 8 * * 1` → `prod`; other schedules → `alias`; manual → the input). One job: checkout fresh `main`, Python, `build_site.py`, `check.py --step 1.11` (the build must pass before anything reaches Netlify), `actions/setup-node@v5` with Node 22, `deploy_guard.py --kind --override` (refuses the 9th `prod` of a calendar month), the CLI deploy, `deploy_guard.py --record` and a one-file commit of `data/deploy_log.json`. Concurrency group `netlify-deploy` only (not `data-writers`), `cancel-in-progress: false`; `permissions: contents: write`. Secrets `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID` as environment variables. Full reference YAML: `02_PHASE1_BUILD_PLAN.md` step 1.15a.
- `radar.yml` (phase 2) — `cron: "30 7 * * *"` + manual with inputs `start_date`, `end_date` (inclusive; ≤ 10 days) for back-fill.
- `thames-history.yml` (phase 3) — manual only (`workflow_dispatch` with inputs `job` ∈ {`pull-alerts`, `rain-backfill`} and `month` as `YYYY-MM`); the `rain-backfill` job converts `month` to `--range YYYY-MM-01 <first day of next month>`; each job runs only when `inputs.job` matches (`if:` condition); both jobs use concurrency group `data-writers` and the commit-if-changed pattern; `pull-alerts` reads the two Thames secrets.

**Action versions** (latest majors on 15 Sep 2026 — pin these): `actions/checkout@v7`, `actions/setup-python@v7`, `actions/setup-node@v5` (verify the current major at step 1.15a with `gh api repos/actions/setup-node/releases/latest`); Node 22 (Node 20 reached end-of-life in April 2026). Pin the Netlify CLI major found at step 1.15a. No GitHub Pages actions are used.

9.4 **Known platform behaviour to state in NOTES**: GitHub schedules can be delayed at busy times and the minimum interval is 5 minutes; scheduled workflows are disabled after 60 days without repository activity (our commits prevent this); with `concurrency` and `cancel-in-progress: false`, when a third run queues the *pending* one is cancelled — cancelled runs are expected and are **not** failures in any check. `gh` (GitHub CLI) is required locally: checks that count runs use `gh run list`. Netlify credits are shared by every site on the account (Jaimin has at least one other site on this team); the monthly budget here assumes the other sites deploy rarely.

9.5 **Secrets.** Phase 1: `NETLIFY_AUTH_TOKEN` (a Netlify personal access token: User settings → Applications → Personal access tokens), `NETLIFY_SITE_ID` (Project configuration → General → Project details → Project ID). Phase 3: `TW_CLIENT_ID`, `TW_CLIENT_SECRET`.

## 10. Non-goals (do not build)

Live map with tiles; email/push alerts; user accounts; comments; predictions; any per-company "score" beyond the counts and rates defined above; anything for Wales/Scotland in phases 1–3; any statement about legality.
