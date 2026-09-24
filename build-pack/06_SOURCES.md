# 06 — Verified sources and verbatim quotes

Every link below was opened and the quote copied from the page on the date shown. Items tagged `[method]` must appear verbatim (quote) and as an `href` (link) on the site's Method page — CHECK 1.14 enforces this. Do not paraphrase a tagged quote. If a page changes and a quote no longer appears, do not "fix" the quote: report it.

---

## The rule

1. `[method]` **Environment Agency blog, "What are dry day spills?", 28 August 2024** — https://environmentagency.blog.gov.uk/2024/08/28/what-are-dry-day-spills (fetched 2026-09-14 and 2026-09-15)
   - `[method]` "A dry day spill is when a storm overflow is used on a 'dry day' – which is defined as no rainfall above 0.25mm on that day and the preceding 24 hours."
   - `[method]` "Storm overflows should not spill on dry days, but there are exceptions."
   - `[method]` "rainfall data from local rain gauges as well as rainfall radar information"
   - `[method]` "treat them as a potential breach until we have confirmed through further investigation"

2. `[method]` **Environment Agency, storm overflow spill data for 2024, published 27 March 2025** — https://www.gov.uk/government/news/environment-agency-storm-overflow-spill-data-for-2024 (fetched 2026-09-15)
   - `[method]` "since January, all day dry spills – no matter how small – are now classified as pollution incidents"

3. `[method]` **EA permit guidance for storm and emergency overflows (updated 13 September 2018)** — https://www.gov.uk/government/publications/water-companies-environmental-permits-for-storm-overflows-and-emergency-overflows/water-companies-environmental-permits-for-storm-overflows-and-emergency-overflows (fetched 2026-09-15)
   - `[method]` "operate in dry weather conditions" (first item in the list of conditions under which "The Environment Agency classes storm overflows as unsatisfactory when they:")
   - Spill counting (context): "Start counting when the first discharge occurs. Any discharge (or discharges) in the first 12-hour block are counted as one spill. Any discharge (or discharges) in the next, and subsequent 24-hour blocks, are each counted as one additional spill per block."

## The legal duty to publish

4. `[method]` **Environment Act 2021, section 81 (inserting s.141DA Water Industry Act 1991)** — https://www.legislation.gov.uk/ukpga/2021/30/section/81 (fetched 2026-09-15)
   - `[method]` "The information referred to in subsection (1)(a) to (c) must be published within an hour of the discharge beginning; and that referred to in subsection (1)(d) within an hour of it ending."
   - Duty items: "(a)that there has been a discharge from the storm overflow; (b)the location of the storm overflow; (c)when the discharge began; (d)when the discharge ended."
   - Commencement: "S. 81 in force at 1.1.2025 in so far as not already in force by S.I. 2024/639, reg. 4"

## The discharge data

5. `[method]` **National Storm Overflow Hub (Stream)** — https://www.streamwaterdata.co.uk/pages/the-national-storm-overflow-hub (fetched 2026-09-15). The page is JavaScript-rendered; its text is served from the ArcGIS item `https://www.arcgis.com/sharing/rest/content/items/74aa218d6ce94c75aec9d0a2a6006aea/data?f=json`, which is where these sentences were read (re-verified 2026-09-15).
   - "The Hub shows near real-time discharge data from over 14,000 storm overflows in England."
   - "The National Storm Overflow Hub (the Hub) brings together near real-time discharge data for all the storm overflows in England in one interactive map for the first time in the world."
6. `[method]` **Hub data page** — https://www.streamwaterdata.co.uk/pages/storm-overflows-data (fetched 2026-09-15)
   - `[method]` "Data provided on the map and in the API is near real-time data and has not undergone an audit process required to comply with the Environment Agency regulatory EDM Annual Return dataset."
   - "Companies aim to transmit data on a discharge within an hour of the outfall operating."
7. `[method]` **Hub FAQ** — https://www.streamwaterdata.co.uk/pages/storm-overflows-faqs (fetched 2026-09-15)
   - `[method]` "The Hub does not have access to data from before its date of publication."
   - "For the purposes of publishing EDM data, near real-time means within the hour."
   - "While arrangements differ across companies, all monitors take measurements at least every 15 minutes."
8. **Water UK launch release, 22 November 2024** — https://www.water.org.uk/news-views-publications/news/water-industry-launches-world-first-interactive-storm-overflows-map (fetched 2026-09-15)
   - "The 'National Storm Overflows Hub' will show the operation of all 14,187 storm overflows in England."
   - "An Application Programming Interface (API) has been created to allow third parties, such as charities and campaign groups, to access the data and broaden its reach by making it available via their websites."
9. **Hub live map** — https://experience.arcgis.com/experience/cb89b71c060f40d394dca026445da4bc/
10. **Company feed licence and start** (Thames item metadata, https://www.arcgis.com/sharing/rest/content/items/216f455c4435450693cf1d0d0ecf6023?f=json; Anglian item https://www.arcgis.com/sharing/rest/content/items/333c5c0600f94757b134b276ac4ad8b0?f=json; fetched 2026-09-15): `licenseInfo` "Licensed under CC BY 4.0" on both; Anglian description: "The data used in this map started to be collected on 1st November 2024, if a monitor shows a null value in the history, that is because that monitor has not been triggered from that date." and "Anglian Water Services' data is refreshed at intervals of 60 minutes." ST Connect item (`63295ca00e8741fd9d0cd02bd5301d9d`) has an empty `licenseInfo` and its layer holds 1 record (verified 2026-09-15).

## Rainfall

11. `[method]` **EA Hydrology API reference** — https://environment.data.gov.uk/hydrology/doc/reference (fetched 2026-09-15). Licence OGL v3. Live probe 2026-09-15: measure `…-rainfall-t-900-mm-qualified`, `periodName` "15min", `unitName` "mm", `valueType` "total"; latest reading for a sample gauge `2026-09-13T00:15:00`, quality "Unchecked".
12. `[method]` **EA real-time rainfall API** — https://environment.data.gov.uk/flood-monitoring/doc/rainfall (fetched 2026-09-15)
   - "The Environment Agency has approximately 1000 real time rain gauges which are connected by telemetry."
   - "The data reported here gives accumulated totals for each 15 min period."
   - "The data is typically transfered once or twice per day." (sic — the typo is in the source)
   - "These APIs are provided as open data under the Open Government Licence with no requirement for registration."
   - "If you need a full historic supply of a single site, or for data more than 12 months old, you would need to make a request for an offline supply via enquiries@environment-agency.gov.uk"

## Official annual figures (context)

13. `[method]` **EA EDM annual returns dataset** — https://www.data.gov.uk/dataset/19f6064d-7356-466f-844e-d20ea10ae9fd/event-duration-monitoring-storm-overflows-annual-returns (fetched 2026-09-15) — files EDM_2020 … EDM_2025, Open Government Licence, last updated 21 August 2026.
14. `[method]` **EA 2025 EDM release, 26 March 2026** — https://www.gov.uk/government/news/fewer-and-shorter-storm-overflow-spills-in-2025-new-monitoring-data-shows (fetched 2026-09-15)
   - `[method]` "There were 291,492 spill events in 2025, a 35% reduction on 2024."
   - `[method]` "Every single storm overflow in England now has an event duration monitor fitted, providing the most complete national picture to date."
15. `[method]` **House of Commons Library, CBP-10027 "Sewage discharges", 31 March 2026** — https://researchbriefings.files.parliament.uk/documents/CBP-10027/CBP-10027.pdf (fetched 2026-09-15)
   - `[method]` "there is at present no way to distinguish 'dry spills' (discharge of sewage at times of little to no rainfall, normally in breach of permit conditions) within this dataset."

## Why this matters (About page)

16. `[method]` **The Guardian (Sandra Laville), 1 September 2026, via AOL syndication** — https://www.aol.co.uk/articles/dry-weather-sewage-discharges-soar-050045000.html (fetched 2026-09-14 and 2026-09-15)
   - `[method]` "In 2025, water companies in England and Wales reported 8,576 dry spill pollution discharges."
   - "Between January and May this year alone, water companies discharged raw sewage into rivers and seas during dry weather 7,280 times."
   - "According to freedom of information requests submitted by Environment Agency whistleblower Robert Forrester, the pollution is getting worse, not better, despite the regulator's promise of tougher action."
   - Water UK response: "These are unverified figures, and it is too early to describe them as dry day spills."
   - Note: the article says "England and Wales"; the FOI was to the Environment Agency, which covers England. Quote it as written; do not resolve the discrepancy on the site.

## Radar (phase 2)

17. `[method]` **Met Office UK radar observations on AWS Open Data** — https://registry.opendata.aws/met-office-uk-radar-observations/ (fetched 2026-09-15)
   - "Four images per hour (every 15 minutes). The data is available within 20 minutes of the validity time of the product."
   - "British Crown copyright 2024-2025, the Met Office, is licensed under CC BY-SA"
   - Bucket `met-office-radar-obs-data`, region `eu-west-2`; key pattern observed `radar/YYYY/MM/DD/YYYYMMDDHHMM_ODIM_ng_radar_rainrate_composite_1km_UK.h5`; oldest key seen `radar/2024/11/21/…`.

## Thames Water (phase 3)

18. **Thames Water storm discharge data page** — https://www.thameswater.co.uk/about-us/performance/river-health/storm-discharge-and-flow-data (fetched 2026-09-15)
   - "We've set up an application programme interface (API) to connect third parties to our publicly open storm discharge data."
   - Portal: https://data.thameswater.co.uk/
19. **Third-party client details (unverified against Thames's own docs)** — https://leo037.quarto.pub/leos-blog/posts/opendata%20thamesEDM/opendata%20thamesEDM.html and https://raw.githubusercontent.com/mpinder0/thameswater-edm-fetch/main/thames_water.py (fetched 2026-09-15): base `https://prod-tw-opendata-app.uk-e1.cloudhub.io/data/STE/v1/`, endpoints `DischargeCurrentStatus`, `DischargeAlerts`; headers `client_id`, `client_secret`; params `limit`, `col_1`/`operand_1`/`value_1`; "limited to return a maximum of 1000 records per call"; "it appears that the Thames Water API only publishes data from 1st April 2022."

## Prior art (About page, neutral wording)

20. **River Truth (Nexfort Data Limited)** — https://rivertruth.co.uk/ and https://rivertruth.co.uk/discrepancies (fetched 2026-09-15)
   - "Currently 3,471 open discrepancies, including 335 dry-weather spills this week." (front page, 15 Sep 2026)
   - Their rule: "Spill occurred with effectively no rainfall in the preceding 24 h — storm overflows are not legally permitted to discharge in dry weather."
21. **Top of the Poops** — https://top-of-the-poops.org/ (fetched 2026-09-15) — "Rainfall data is delayed by up to two days."
22. **Scottish Water overflow API (future port)** — https://www.scottishwater.co.uk/Help-and-Resources/Open-Data/Overflow-Map-Data (fetched 2026-09-15) — "It provides near real-time information on monitor activations and is updated every 60 minutes." / "No authentication is required, but users should respect rate limits and cache data where possible."

---

## Company feeds verified 2026-09-15 (layer 0 of each Feature Service)

| Company | Feature Service | Notes |
|---|---|---|
| Thames | `https://services2.arcgis.com/g6o32ZDQ33GpCIu3/arcgis/rest/services/Thames_Water_Storm_Overflow_Activity_(Production)_view/FeatureServer` | canonical fields; maxRecordCount 2000; CC BY 4.0 |
| Anglian | `https://services3.arcgis.com/VCOY1atHWVcDlvlJ/arcgis/rest/services/stream_service_outfall_locations_view/FeatureServer` | canonical fields; maxRecordCount 1000; CC BY 4.0 |
| South West | `https://services-eu1.arcgis.com/OMdMOtfhATJPcHe3/arcgis/rest/services/NEH_outlets_PROD/FeatureServer` | camelCase fields (`status`, `statusStart`, `latestEventStart`, `latestEventEnd`, …); maxRecordCount 2000; CC BY 4.0 |
| ST Connect | `https://services-eu1.arcgis.com/zat3uNEZelYVksuM/arcgis/rest/services/STREAM_Data/FeatureServer` | `LatestEventFinish` instead of `LatestEventEnd`; extra `GlobalID`; empty licence; **1 record** |
| Other six | resolve via item JSON (`01_SPEC.md` §2.1) | canonical field spelling per the 15 Sep 2026 review; re-verified by `sources.py` at step 1.2 |

## Hosting (Netlify) — verified 2026-09-16; for the build plan, not for the site's Method page

23. **Netlify project visibility** — https://docs.netlify.com/manage/security/secure-access-to-sites/project-visibility/
   - "A project can be public (anyone with the URL can view it), private (only your team and people you invite can view it), or password protected (public, but requires a shared password to view)."
   - "Private projects are enforced with Netlify login: only your team and people you invite can view a private project."
   - "This feature is available on Credit-based Free, Personal, and Pro plans only."
   - "On a Free and Personal plan, private projects can only be seen by the Team Owner."
   - Visitors without access "see a Netlify-branded page explaining they don't have access and prompting them to ask the owner for access."
   - Setting path: "Project configuration > General > Visitor access > Project visibility"; production deploys and previews are set separately.
24. **Netlify password protection (not used — Pro only)** — https://docs.netlify.com/manage/security/secure-access-to-sites/password-protection/ — "Basic password protection for your entire site is available on all Pro plans."
25. **How Netlify credits work** — https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work/ — Free plan 300 credits/month, hard limit; production deploy 15 credits; Deploy Previews/branch deploys 0 credits; bandwidth 20 credits/GB; web requests 2 credits per 10,000; "Once your credit balance is completely used up, all of your web projects (sites/apps) are paused and visitors to your web projects will find a `Site not available` page at each of your web project's URLs."; monthly credits reset each billing cycle and do not roll over on Free.
26. **Netlify CLI `deploy`** — https://cli.netlify.com/commands/deploy/ — `--prod` "Deploy to production"; without it the command "Creates a draft deploy by default"; `--alias` "Specifies the alias for deployment, the string at the beginning of the deploy subdomain. Useful for creating predictable deployment URLs."; `--dir` "Specify a folder to deploy"; `--site` "A project name or ID to deploy to"; `--auth` "Netlify auth token - can be used to run this command without logging in"; `--no-build` "Do not run build command before deploying."; `--message` "A short message to include in the deploy log"; `--json` "Output deployment data as JSON".

## Gauge representativeness and faulty-gauge detection (researched 20 September 2026 for dry-day-v3)

27. **Natural Resources Wales, "How to classify storm overflow performance", Guidance note GN066, version 1.0, published 26 October 2023** — https://afonyddcymru.org/wp-content/uploads/2024/03/GN066-How-to-classify-storm-overflow-performance.pdf (fetched 2026-09-20). **This is the Welsh regulator, not the Environment Agency**; it is the closest published prescription either regulator has issued for choosing rainfall data for a dry-day test.
   - Test 1, Dry day discharges: "Use rain gauge data that is the most representative for the SO. Where there is no nearby rain gauge, the three closest gauges can be triangulated. Radar data can be used where the approach is agreed with us."
   - Heavy rainfall (§2.7): "Radar data may be used in the absence of representative rain gauge data where the approach is agreed with us."
   - Its own dry-day definition (§2.6), which differs from the EA's: "A “dry day” is a day (midnight-midnight) with total rainfall accumulation not exceeding 0.25 millimetres." and "A “dry day discharge” is any discharge that occurs or continues on a “dry day”, allowing “one dry day” after rainfall ends. This provides allowance for network drain-down for the first dry day after rainfall or snowmelt."
   - Reporting template, item 12: "Representative rain gauge/s identification — Include station name and number".
   - No distance in kilometres appears anywhere in the document; "representative" is left to judgement.

28. **Environment Agency, "Storm overflow assessment framework 2025"** — https://www.gov.uk/government/publications/storm-overflow-assessment-framework-2025/storm-overflow-assessment-framework-2025 (fetched 2026-09-20). Negative finding, recorded so it is not re-researched: SOAF 2025 discusses rainfall only under Stage 1a "Exceptional Rainfall" (water situation reports, long-term averages, the 5% exceptional band). It sets **no** rain-gauge selection criteria, no distance threshold, no radar rule and no dry-day rainfall method.

29. **K. Ośródka, J. Szturc et al., "Automatic quality control of telemetric rain gauge data providing quantitative quality information (RainGaugeQC)", Atmospheric Measurement Techniques 15, 5581–5597, 2022** — https://amt.copernicus.org/articles/15/5581/2022/ (fetched 2026-09-20). Peer-reviewed precedent for using radar to catch a gauge that wrongly reports no rain, with the same 3x3 one-kilometre box this project already samples.
   - Radar conformity check (§3.5): "RCC compares each gauge observation lower than 0.2 mm/10 min with radar observations at the gauge location and its surrounding of 3×3 pixels (the pixel size is 1 km × 1 km). If the radar data for the vicinity of the station are above a predefined threshold, then a “no precipitation” result measured by the sensor is assumed to be false and the QI is reduced to 0.0."
   - Spatial consistency check (§3.7): "SCC is applied to identify outliers based on a comparison with neighbouring stations. Additionally, radar data are introduced to assess the level of QI reduction for outliers."

30. **L. de Vos et al., "Quality Control for Crowdsourced Personal Weather Stations to Enable Operational Rainfall Monitoring", Geophysical Research Letters 46, 2019** (https://doi.org/10.1029/2019GL083731), as implemented in **pypwsqc** — https://pypwsqc.readthedocs.io/en/stable/notebooks/merged_filters.html (fetched 2026-09-20; the Wiley page itself returned HTTP 403 to an automated fetch, so the rule and its parameters are quoted from the reference implementation's documentation).
   - Faulty Zero filter: "Median rainfall of neighbouring stations within range max_distance is larger than zero for at least nint time intervals while the station itself reports zero rainfall."
   - Parameters in the documented example: `fz_filter(ds_pws, nint=6, n_stat=5)` with `max_distance = 10e3` — neighbours within **10 km**, at least **5** neighbouring stations, **6** consecutive intervals (at 5-minute resolution, 30 minutes).
   - The filter uses the **median** of the neighbours, not a count of wet ones, which is what makes it robust to a single unrepresentative neighbour.

## Map regions (added 23 September 2026 for the Map page)

28. **Office for National Statistics, Open Geography Portal, "Regions (December 2022) Boundaries EN BUC"** — https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Regions_December_2022_EN_BUC/FeatureServer/0 (fetched 2026-09-23). The nine regions of England (ITL1, formerly the Government Office Regions): North East, North West, Yorkshire and The Humber, East Midlands, West Midlands, East of England, London, South East, South West. BUC is the ultra-generalised, coastline-clipped version. Stored at `data/geo/regions.geojson` by `scripts/geo_regions.py` so the build never needs the network.
29. **ONS geography licences** — https://www.ons.gov.uk/methodology/geography/licences (fetched 2026-09-23). Supplied under the Open Government Licence; the page requires both of these statements verbatim when the boundaries are reproduced, and both are in the site footer:
   - "Source: Office for National Statistics licensed under the Open Government Licence v.3.0"
   - "Contains OS data © Crown copyright and database right 2022"

## Could not verify (do not state these as fact anywhere on the site)

- The exact column headers inside the EDM annual-return zips.
- Thames Water's API launch date (Jan 2023) and history start (1 Apr 2022) — third-party blogs only; step 3.1 confirms.
- Whether Stream's feeds formally require no key (none was needed in practice on 15 Sep 2026).
- River Truth's rainfall threshold and retention period.
- The earliest year of rainfall in the EA Hydrology API.
- The Guardian's "England and Wales" scope for the 8,576 figure.
- Whether a CLI draft/alias deploy is billed as a "Deploy Preview" (0 credits) — Netlify's table names Deploy Previews and branch deploys; step 1.15b measures it empirically before enabling daily alias deploys.
- Whether `netlify sites:list --json` exposes `build_settings.repo_url` under exactly that key — CHECK 0.1 says what field it found; the requirement is simply that the project shows no linked repository.
