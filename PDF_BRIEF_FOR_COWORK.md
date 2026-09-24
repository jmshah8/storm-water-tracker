# Brief for Claude Cowork — build the Storm Water Tracker PDF

You are producing **one PDF** about a website called **Storm Water Tracker**. Everything you need is in
this file. Read it all before you start.

---

## 0. The rules that override everything else

These are not style preferences. Breaking any one of them makes the document wrong.

1. **Never invent a number.** Every figure in the PDF must come from §4 of this brief, which is a
   dated snapshot taken from the site's own data. If you want a number that is not in §4, leave it
   out. Do not estimate, round up into a rounder-sounding figure, annualise, or extrapolate.
2. **Never call anything "illegal".** Not illegal, not criminal, not guilty, not "broke the law",
   not "lawbreaking". The strongest permitted wording is the badge the site itself uses:
   **"Dry day spill · EA definition"** with the sub-line **"Potential breach; not confirmed."**
   Use those two strings exactly if you use them at all. Elsewhere the permitted vocabulary is:
   *dry day spill, potential breach, flagged, provisional, complete rain data, contested by radar.*
   The Environment Agency itself treats these "as a potential breach until we have confirmed through
   further investigation" — the PDF must not go further than the regulator does.
3. **Quote sources exactly.** Every quotation in §5 is verbatim. Copy them character for character.
   Do not paraphrase a quote and present it inside quotation marks.
4. **Label the snapshot.** Every page that carries figures must make clear they are as at the date in
   §4. Put "Figures as at 24 September 2026" in the footer of every page.
5. **No logos, no crests, no water company branding, no Environment Agency branding.** This is a
   personal, non-commercial project and must not look like an official or affiliated publication.
6. **Say what the method cannot do.** §6 is not optional. A document that only lists what the tracker
   catches, without §6, misrepresents it.

---

## 1. What the document is

A briefing document explaining what Storm Water Tracker is, what it measures, what it has found, and
where its limits are. The reader is intelligent and interested but knows nothing about sewage
monitoring, water regulation, or the Environment Agency. Assume no technical background. Do not
assume they know what a storm overflow is.

**Tone:** factual, calm, precise. This is a document whose credibility rests on being careful. It is
not campaign material. It should read like something a regulator's analyst would not object to.

---

## 2. Structure — this is a hard requirement

### Page 1 — Executive summary. Exactly one page. Not more, not less.

One page means one page. If it runs onto a second page, cut words until it fits — do not shrink the
type below 10pt or squeeze the margins below 15mm to make it fit. If it falls short of a full page,
add substance from §3 rather than padding with whitespace or larger type.

The executive summary must answer, in this order:

1. **What the problem is.** Sewage overflows are allowed to discharge into rivers and the sea when
   heavy rain would otherwise flood the system. They are not supposed to discharge on dry days.
2. **What the tracker is.** A website that records every storm overflow discharge published by
   England's ten water companies, checks each one against Environment Agency rainfall data, and
   flags the ones that started on a dry day.
3. **The one rule it applies.** Quote the Environment Agency's definition verbatim (§5, source 1)
   and state that the site implements that sentence and nothing else.
4. **The headline figures.** From §4. At minimum: overflows tracked, discharges recorded, dry day
   spills flagged, and the proportion of flags backed by complete rainfall data.
5. **What makes it different.** Per-event, permanent, evidence-shown-for-every-flag, and the full
   data published for download. See §3.5.
6. **The limits, in one short paragraph.** Drawn from §6. This belongs on page one, not only in the
   back pages.

Include a small "key numbers" block — four to six figures, large and scannable. Do not use a chart
on page one; there is not room for one that earns its space.

### Pages 2 onwards — supporting detail. As many pages as the material needs.

Suggested sections, in this order. Merge or split as the material dictates, but keep this sequence,
because it runs from *why* through *how* to *what it cannot do*:

- **2. Background: why this record exists** — the legal duty, and the gap it leaves (§3.1)
- **3. The rule, in full** — the definition, how it is applied, and the deliberately strict reading (§3.2)
- **4. How a discharge becomes a verdict** — the pipeline, step by step (§3.3)
- **5. The evidence behind every flag** — what each flagged discharge publishes (§3.4)
- **6. Checking the checker: rainfall radar** — the second opinion and contested flags (§3.6)
- **7. What the tracker has found** — the figures, by company and over time (§4)
- **8. What this method can miss** — the limits, in full (§6)
- **9. Sources** — every source, quoted, linked and dated (§5)

A simple table or two is welcome in the back pages (the company table in §4.4 especially). Keep any
chart plain — no 3D, no gradients, no decorative colour.

---

## 3. The substance

### 3.1 Background: why this record exists

Storm overflows exist so that when heavy rain overwhelms a combined sewer, the excess spills to a
river or the sea rather than backing up into homes and streets. That is their designed purpose. The
concern is overflows discharging when it has *not* been raining, which suggests a fault, a blockage,
or under-capacity rather than a storm.

Since the Environment Act 2021, water companies must publish each discharge within an hour of it
beginning, and again within an hour of it ending (§5, source 4). That creates a live public feed —
but the feed is a snapshot. It shows only each overflow's most recent discharge, and nothing keeps
the history. The National Storm Overflow Hub, which aggregates all ten companies, states plainly:
"The Hub does not have access to data from before its date of publication." (§5, source 6)

Separately, the Environment Agency publishes annual Event Duration Monitoring returns. Those are
kept, but they count spills per overflow per year and carry no per-event times. The House of Commons
Library notes the consequence: "there is at present no way to distinguish 'dry spills' (discharge of
sewage at times of little to no rainfall, normally in breach of permit conditions) within this
dataset." (§5, source 7)

**So the times exist but are not kept, and the kept records have no times.** Storm Water Tracker sits
in that gap: it reads the live feeds every ten minutes, keeps every discharge permanently, and
applies the dry-day test to each one as it arrives.

### 3.2 The rule, in full

The Environment Agency's own definition, quoted exactly (§5, source 1):

> "A dry day spill is when a storm overflow is used on a 'dry day' – which is defined as no rainfall
> above 0.25mm on that day and the preceding 24 hours."

How the site implements that sentence:

- **What is judged:** the moment a discharge *starts*. The relevant day is the UTC calendar day on
  which it started. A discharge that began in rain and continued into a dry day is not flagged.
- **The window:** "that day and the preceding 24 hours" is read as the 48 hours from 00:00 UTC on the
  day before the start to 00:00 UTC on the day after it.
- **The measurement:** every 15-minute rainfall total recorded in that window at the chosen gauge is
  added up. A complete window is 192 readings.
- **The verdict:** flagged as a dry day spill if, and only if, the 48-hour total is 0.25 mm or less.

**Why the total, and why that matters.** The EA's sentence can be read two ways: no *single* reading
above 0.25 mm, or no more than 0.25 mm *in all*. The site uses the total, which is the stricter test
for raising a flag. A window with three readings of 0.2 mm has no single reading above the threshold,
but totals 0.6 mm — flagged under the other reading, not flagged under this one. Using the total
therefore flags *fewer* discharges and minimises false flags. Both numbers are published for every
event, so anyone can recompute the other reading.

**Which rain gauge.** Rainfall comes from the Environment Agency's Hydrology API. For each overflow
the site uses the nearest gauge within 10 km that returned at least 176 of the expected 192 readings.
The 10 km limit is the site's own assumption — the EA publishes no distance — and is stated as such.
Where no gauge lies within 10 km, the site follows the only published regulatory instruction on the
point, from Natural Resources Wales (the Welsh regulator, not the EA), quoted at §5 source 8: the
three closest gauges within 20 km are combined, weighted by inverse distance.

**Broken gauges.** A failed rain gauge usually fails silently — a blocked funnel reports 0.00 mm
however hard it rains, which looks exactly like a dry day and would produce a false flag carrying the
site's strongest evidence line. The site therefore skips a gauge that has recorded nothing for days
while independent evidence says it rained, and moves to the next-nearest. Each flagged event states
how many gauges were skipped.

**Time zone.** Everything is UTC. This is a stated assumption, and it was verified rather than
assumed: on a British Summer Time day, eight gauges were compared against the EA's separate real-time
rainfall API, matching on 96 of 96 readings with no offset.

### 3.3 How a discharge becomes a verdict

1. **Collect.** Every ten minutes, the ten companies' feeds are read via the National Storm Overflow
   Hub. New discharges are written to a permanent record.
2. **Wait for the window.** A verdict cannot be reached until the 48-hour rainfall window has closed.
3. **Fetch rainfall.** Environment Agency 15-minute gauge totals are pulled for the window. The EA
   publishes some readings late, so the rainfall may arrive over the following days.
4. **Classify.** The rule in §3.2 is applied. Until the data can no longer change, the verdict is
   marked *provisional* and re-checked hourly.
5. **Finalise.** A verdict becomes final when it cannot change: when all 192 readings are present and
   72 hours have passed, or when 14 days have passed regardless.
6. **Publish.** The site is rebuilt and every flagged discharge gets its own page with its evidence.

A verdict typically appears one to three days after the discharge started — the delay is the rainfall
data, not the discharge data. Every change of verdict between "dry day spill" and "not a dry day" is
recorded in a public log that anyone can download.

### 3.4 The evidence behind every flag

No flag is published without its evidence. Each flagged discharge shows: the overflow's name and ID,
the water company, the receiving watercourse, the start and end times, the gauge used and its
distance, the rainfall totals for the window, how many of the 192 readings were present, the rule
version that produced the verdict, and the timestamp of the classification. The complete dataset is
downloadable as CSV.

State this plainly in the PDF: **a reader can check any single flag against the Environment Agency's
own public API and reproduce it.**

### 3.5 What makes it different

Other organisations publish storm overflow data. Describe the difference neutrally, without
disparaging anyone:

- It applies **the Environment Agency's own published definition, exactly**, rather than a rule of its
  own devising.
- It keeps a **permanent, per-event forward record** — the official live feeds do not.
- It **publishes the evidence for every flag**, and the full underlying data.
- It **counts conservatively**, using the stricter reading of the rule and separating out flags that
  radar contests (§3.6).

### 3.6 Checking the checker: rainfall radar

Rain gauges measure rain falling into one funnel, up to 10 km from the overflow. Met Office rainfall
radar estimates rain over every square kilometre, including the overflow's own. The two are
independent, and the EA says it uses both: it checks "rainfall data from local rain gauges as well as
rainfall radar information" (§5, source 1).

For each flagged discharge the site adds up radar rainfall over the same 48-hour window, for the
overflow's own square kilometre and the nine squares around it, and publishes it beside the gauge
evidence.

**Contested flags.** Where radar recorded materially more rain than the gauge did — more than 1 mm,
four times the rule's own threshold — the flag is called **contested** and counted *separately* from
the headline figure rather than added into it. This is a counting decision, not a rule change:

- A contested flag is **still published**, still has its page and its evidence, still sits in every
  data file. Nothing is hidden; it is counted in its own column.
- A flag the radar **cannot** check is **not** contested. The radar archive only reaches back about
  two years, and an older discharge must not be demoted for something the archive cannot speak to.
- A contested flag is **not a withdrawn one**. The EA's definition is written around rainfall
  measurements, and the site implements that definition. A contest is a reason to look closer.

The 1 mm bar is deliberate: across the archive the median disagreement is 0.79 mm, meaning most
disagreements are simply a radar estimate landing on the other side of the same line — noise, not
evidence.

**Radar never decides a verdict.** This was tested, not assumed: every event was classified twice,
once with the radar data present and once with it removed, and every verdict was identical.

---

## 4. The figures — use these and only these

**Snapshot taken 24 September 2026, 03:24 UTC.** The site collects new discharges every ten minutes,
so these figures drift from the moment they were taken — that is expected and is why every figure page
must be labelled **"Figures as at 24 September 2026"**. Every number below was checked against the
site's own data file at that moment; they are internally consistent with each other and should be used
as one set. Do not mix them with numbers read off the live site on a different day.

*To refresh this snapshot before a later rebuild of the PDF, run `python scripts/snapshot_figures.py`
in the Storm Water Tracker repository and replace §4 with its output.*

### 4.1 Scale of the record
| | |
|---|---|
| Water companies covered | 10 (all of England) |
| Storm overflows tracked | 14,200 |
| Total discharges classified | 93,326 |
| Of which: since the site's own record began (17 September 2026) | 3,088 |
| Of which: Thames Water's own published history, back to April 2022 | 90,238 |
| Date the permanent record began | 17 September 2026 |
| Rule version in force | dry-day-v3 |
| Radar archive held | 669 days, from 21 November 2024 |

### 4.2 Verdicts across everything classified (93,326 discharges)
| Verdict | Count |
|---|---|
| Not a dry day | 78,003 |
| **Dry day spill** | **12,025** (of which 693 contested by radar) |
| Insufficient rain data | 2,537 |
| Rain check pending | 520 |
| No gauge within 10 km | 241 |

### 4.3 The live record only (since 17 September 2026 — 3,088 discharges)
| Verdict | Count |
|---|---|
| Not a dry day | 1,958 |
| **Dry day spill** | **400** (of which 59 contested by radar) |
| Rain check pending | 520 |
| No gauge within 10 km | 109 |
| Insufficient rain data | 101 |

### 4.4 Dry day spills by company, live record since 17 September 2026
Uncontested flags only. **Carry the warning in §6.3 wherever this table appears.**

| Company | Dry day spills |
|---|---|
| South West Water | 83 |
| Severn Trent Water | 79 |
| Anglian Water | 72 |
| Northumbrian Water | 33 |
| United Utilities | 21 |
| Wessex Water | 17 |
| Thames Water | 15 |
| Yorkshire Water | 14 |
| Southern Water | 7 |
| ST Connect | 0 |

### 4.5 Quality of the evidence
| | |
|---|---|
| Dry day flags resting on a complete 48-hour rainfall window (192 of 192 readings) | 98.6% |
| Dry day flags the radar archive can independently check | 5,472 |
| Of those, flags the radar agrees with | 3,785 (69.2%) |

### 4.6 Figures you may NOT state
- Any national annual total of dry day spills produced by this site. The record began on
  17 September 2026; there is no full year.
- Any comparison between companies as a measure of performance. See §6.3.
- Any trend, increase or decrease over time from the live record. It is days old.
- Any per-overflow or per-company rate not listed above.

---

## 5. Sources — quote these exactly

Each was fetched and checked on the date shown. Reproduce the quotes character for character.

1. **Environment Agency blog, "What are dry day spills?", 28 August 2024** (fetched 14–15 Sep 2026) —
   https://environmentagency.blog.gov.uk/2024/08/28/what-are-dry-day-spills
   - "A dry day spill is when a storm overflow is used on a 'dry day' – which is defined as no rainfall above 0.25mm on that day and the preceding 24 hours."
   - "Storm overflows should not spill on dry days, but there are exceptions."
   - "rainfall data from local rain gauges as well as rainfall radar information"
   - "treat them as a potential breach until we have confirmed through further investigation"
2. **Environment Agency, storm overflow spill data for 2024, 27 March 2025** (fetched 15 Sep 2026) —
   https://www.gov.uk/government/news/environment-agency-storm-overflow-spill-data-for-2024
   - "since January, all day dry spills – no matter how small – are now classified as pollution incidents"
3. **Environment Agency, 2025 monitoring data release, 26 March 2026** (fetched 15 Sep 2026) —
   https://www.gov.uk/government/news/fewer-and-shorter-storm-overflow-spills-in-2025-new-monitoring-data-shows
   - "There were 291,492 spill events in 2025, a 35% reduction on 2024."
   - "Every single storm overflow in England now has an event duration monitor fitted, providing the most complete national picture to date."
4. **Environment Act 2021, section 81** (fetched 15 Sep 2026) —
   https://www.legislation.gov.uk/ukpga/2021/30/section/81
   - "The information referred to in subsection (1)(a) to (c) must be published within an hour of the discharge beginning; and that referred to in subsection (1)(d) within an hour of it ending."
5. **National Storm Overflow Hub data page (Stream)** (fetched 15 Sep 2026) —
   https://www.streamwaterdata.co.uk/pages/storm-overflows-data
   - "Data provided on the map and in the API is near real-time data and has not undergone an audit process required to comply with the Environment Agency regulatory EDM Annual Return dataset."
6. **National Storm Overflow Hub FAQ** (fetched 15 Sep 2026) —
   https://www.streamwaterdata.co.uk/pages/storm-overflows-faqs
   - "The Hub does not have access to data from before its date of publication."
7. **House of Commons Library, CBP-10027 "Sewage discharges", 31 March 2026** (fetched 15 Sep 2026) —
   https://researchbriefings.files.parliament.uk/documents/CBP-10027/CBP-10027.pdf
   - "there is at present no way to distinguish 'dry spills' (discharge of sewage at times of little to no rainfall, normally in breach of permit conditions) within this dataset."
8. **Natural Resources Wales, guidance note GN066, 26 October 2023** (fetched 20 Sep 2026) —
   https://afonyddcymru.org/wp-content/uploads/2024/03/GN066-How-to-classify-storm-overflow-performance.pdf
   - "Use rain gauge data that is the most representative for the SO. Where there is no nearby rain gauge, the three closest gauges can be triangulated."
   - **Note in the PDF that this is the Welsh regulator, not the Environment Agency.** It is used because it is the closest published prescription either regulator has issued on the point.
9. **Environment Agency Hydrology API** (fetched 15 Sep 2026) —
   https://environment.data.gov.uk/hydrology/doc/reference — Open Government Licence v3.0. The source
   of the 15-minute rainfall totals behind every verdict.
10. **Met Office UK radar observations, AWS Open Data** (fetched 15 Sep 2026) —
    https://registry.opendata.aws/met-office-uk-radar-observations/
    - "British Crown copyright 2024-2025, the Met Office, is licensed under CC BY-SA"

**Required attribution block — reproduce on the sources page:**

> Storm overflow data: the ten water companies via the National Storm Overflow Hub (Stream), CC BY 4.0.
> Rainfall: Environment Agency Hydrology API, Open Government Licence v3.0.
> Contains Met Office radar data © British Crown copyright, CC BY-SA.

---

## 6. Limits — this section is mandatory

### 6.1 What the method can miss
- The feeds show only each overflow's **most recent** discharge. If a discharge starts and ends
  between two ten-minute reads, and another begins before the next read, the first is never seen.
- Where a discharge's end is never observed, it is inferred from the start of the next one and
  labelled as inferred.
- Where a company publishes an end time earlier than its start time, the end is left blank rather
  than guessed.
- A gauge up to 10 km away can miss a local shower, or record one that missed the overflow.
- Monitors go offline. An overflow discharging while its monitor is offline never appears at all.
- Overflows with no gauge within range cannot be classified under this method.

### 6.2 What a flag is, and is not
A dry day spill flag means: **the rainfall measured near this overflow, over the 48 hours defined by
the Environment Agency, was at or below the Environment Agency's own threshold.** It does not mean an
offence occurred. The EA lists exceptions, and says it treats dry day spills as a potential breach
until confirmed by investigation. Only the regulator can confirm a breach.

### 6.3 Why the company table must not be read as a league table
**Reproduce this warning wherever company figures appear.** Differences between companies in §4.4
reflect, in unknown proportion: how many overflows each company operates, where those overflows sit
relative to working rain gauges, the local geography and rainfall, differences in how companies
detect and report discharges, and monitor reliability. They are **not** a ranking of environmental
performance, and the PDF must not present them as one. Do not use language like "worst offender",
"top of the table", or "league table".

### 6.4 The record is young
The site's own permanent record began on **17 September 2026**. Most of the classified volume in §4.2
is Thames Water's own published history, which no other company provides — so the totals in §4.2 are
weighted heavily toward one company's geography and must never be described as a national picture.
Where a national statement is needed, use §4.3, and say how short the period is.

---

## 7. Design and output

- **Format:** A4 portrait, PDF.
- **Margins:** 18–20 mm.
- **Type:** one clean sans-serif throughout. Body 10–11pt, minimum 10pt. Generous line spacing.
- **Colour:** restrained and mostly monochrome, with a single accent used only for the key numbers
  and to mark flagged figures. Light background — this is a printable document, not a copy of the
  website's dark theme.
- **Page furniture:** page numbers on every page after page 1; footer on every page reading
  *"Storm Water Tracker · a personal, non-commercial project · Figures as at 24 September 2026"*.
- **Title:** "Storm Water Tracker". Subtitle: "Recording every storm overflow discharge in England,
  and flagging the ones that started on a dry day."
- **Front matter:** no cover page. Page one *is* the executive summary.
- **Tables:** plain rules, no heavy fills, no zebra striping.
- **Do not include** any logo, crest, photograph, stock image, or decorative illustration.

**Required disclaimer, verbatim, at the foot of page one:**

> A personal, non-commercial project. Not affiliated with any water company, regulator or campaign
> group. Flagged discharges are potential breaches of the Environment Agency's dry day definition;
> only the Environment Agency can confirm a breach.

---

## 8. Before you deliver, check each of these

1. The executive summary is **exactly one page**.
2. The words "illegal", "criminal", "guilty" and "broke the law" appear **nowhere**.
3. Every figure in the document traces to §4. No figure was invented, rounded for effect, or
   extrapolated.
4. Every quotation matches §5 character for character.
5. §6.3's warning appears wherever company figures appear.
6. The disclaimer in §7 is on page one, verbatim.
7. Every page carries the "Figures as at 24 September 2026" footer.
8. The limits section is present and substantial — not a single line.
9. No logos or branding of any organisation.
10. The document never claims a national annual total, a trend, or a performance ranking.
