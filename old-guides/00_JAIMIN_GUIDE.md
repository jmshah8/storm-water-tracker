# 00 — Jaimin's guide: from here to a finished Storm Water Tracker

This is your file. It tells you what you do and what Claude Code does, from this moment until the site is live with all three phases done. The executive summary is first; the detail follows in the same order. Everything Claude Code needs is in the other files in this folder; you never have to explain the project to it — you point it at the files.

Cost of the whole thing: £0 (public GitHub repo for the data work, your free Netlify account for hosting, open data). Your time: about 3–4 hours of active work spread over 3–4 weeks — setup, reading GATE reports, design feedback, one registration — plus waiting for data to accumulate. The long back-fills in Phases 2 and 3 (roughly 65 radar runs and 55 rainfall runs) are triggered by Claude Code from the terminal, not by you clicking.

---

## Executive summary — the steps, in order

**Before Claude Code starts (you, ~35 minutes)**
1. Create a public GitHub repo called `storm-water-tracker` and give workflows read-and-write permission. On Netlify: create a manual-deploy project (not connected to Git), set its visibility to **Private**, create a personal access token, and add the token and the Project ID as two GitHub secrets.
2. Clone it to your Mac; copy this folder's `CLAUDE.md` into the repo root; copy the numbered files and the pack README into the repo as `build-pack/` (exact command below).
3. Open Claude Code in the repo and paste the starting prompt (below).

**Phase 1 — the general site (Claude Code, ~1 evening of building + 48 hours of waiting)**
4. Claude Code scaffolds the repo, then verifies all ten company data feeds are live and maps their field names (two companies spell fields differently, and one — "ST Connect" — is a one-row placeholder; the spec already knows this) (CHECK 1.2). If a feed has changed beyond that, it stops (GATE 0).
5. It writes the collector, tests it on fixtures, then runs it live once — this seeds the archive with the latest known discharge per overflow and records your launch date. **GATE 1:** it reports the numbers; you say "continue".
6. It sets up the 10-minute polling workflow on GitHub and proves two runs succeeded.
7. It builds the rainfall pipeline from the EA Hydrology API and — the important one — verifies the API's timestamps are UTC by cross-checking against the EA's other API (CHECK 1.8). If they are not, it stops (GATE 1.8) because every verdict depends on it.
8. It writes the dry-day rule as a pure, unit-tested function, classifies every event, and independently recomputes five flagged events straight from the EA API. **GATE 2:** it reports verdict counts and the five recomputations; you say "continue".
9. It builds the static site (Overview, Companies, Events, Method, Data, About) to the dark, monochrome design, generates the England-of-dashes hero visual, and runs automated checks (valid HTML, no broken links, page numbers equal CSV numbers, forbidden words absent, contrast ratios). **GATE 3:** it sends you eight screenshots; you give design feedback; it applies it.
10. It verifies the Method page contains every source quote verbatim, then writes the deploy workflow and deploys to your **private Netlify site** — two preview deploys first (to measure whether they really cost 0 credits), then one production deploy. It confirms the URL asks for a Netlify login when you're logged out and shows the site when you're logged in. You read your "credits remaining" figure in the Netlify UI at a few points (before, after each preview, after the production deploy) so it can tell what each costs.
11. **48-hour soak:** nothing to do; the workflows run. Then it runs the soak report.
12. It runs the Phase 1 acceptance table. **GATE 4:** you read it and say "accepted". Phase 1 done.

**Phase 2 — Met Office radar (Claude Code, ~1 evening + back-fill runs over a few days)**
13. It downloads one radar file, records its exact structure, and stops if it is not a rain-rate product (GATE 2.1).
14. It writes the radar reader with unit tests and a geographic sanity check (five cities land where they should).
15. It samples radar rainfall at every overflow for one day and checks, on a wet day, that it broadly agrees with the gauges (GATE 2.3 if it does not).
16. It adds a "radar second opinion" to every event page and a "radar agrees" column to the tables. Verdicts do not change.
17. It automates the daily radar job and back-fills the archive in 10-day chunks — about 65 runs back to November 2024, which Claude Code queues from the terminal over a few days. You can stop the back-fill early; anything not back-filled simply shows "radar: missing".
18. Phase 2 acceptance. **GATE 2.7:** you say "accepted".

**Phase 3 — Thames Water back-test to April 2022 (you 15 minutes + Claude Code ~1 evening + monthly rain back-fill runs)**
19. You register on Thames Water's open-data portal, create API credentials, and add them as two GitHub secrets.
20. Claude Code probes the API, confirms endpoints, pagination and the earliest date, and records the contract (GATE 3.1 only if the documented details do not work).
21. It pulls the full alert stream, turns Start/Stop alerts into events, maps locations onto the Hub's overflows, and validates the mapping against the overlap period where both sources exist (GATE 3.3 if agreement is poor).
22. It back-fills EA rainfall month by month back to March 2022 (about 55 monthly runs, queued from the terminal) and classifies the historic events with the unchanged rule.
23. It builds the back-test page (per-year and per-month dry-day spills for Thames, with the two cautions written in). Phase 3 acceptance. **GATE 3.6:** you say "accepted". Project complete.

**After that:** nothing. The workflows keep collecting. Glance at the Actions tab monthly; if a feed changes its field names, the collector stops with a clear error (red "poll" runs) instead of writing bad data, and you re-open Claude Code with `build-pack/02_PHASE1_BUILD_PLAN.md` → "If something in the feeds changes".

---

## The detail

### What you do first (Step 0)

1. **GitHub repo.** On github.com: New repository → name `storm-water-tracker` → **Public** → do not add a README or .gitignore → Create.
   - Settings → Actions → General → "Workflow permissions": **Read and write permissions** → Save.
   - Why public: the collector runs every 10 minutes; that is ~4,000 Actions minutes a month, and only public repos get unlimited free minutes. Nothing sensitive goes in the repo.
   - You do **not** enable GitHub Pages; the site is hosted on Netlify.
1b. **Netlify (your free account) — the site host.**
   - In Terminal: `npx netlify-cli@latest login` (opens a browser to authorise), then `npx netlify-cli@latest sites:create --name storm-water-tracker`. If the name is taken, choose another; the site URL becomes `https://<name>.netlify.app`. This creates a **manual-deploy** project with no Git connection — keep it that way. **Never** use "Add new project → Import an existing project" for this site: a Git-connected site rebuilds on every data commit, and the poller commits every 10 minutes, which would burn 15 credits each and empty your month in about two hours.
   - In the Netlify UI open the project → Project configuration → General → Visitor access → **Project visibility** → set production deploys to **Private** and previews to **Private**. Netlify's docs: "Private projects are enforced with Netlify login" and on the Free plan "private projects can only be seen by the Team Owner" — that is you. Anyone else sees a Netlify page saying they don't have access. (Password protection is a Pro feature; you don't need it.)
   - Create a personal access token: click your avatar → User settings → Applications → Personal access tokens → New access token (name it `storm-water-tracker-actions`). Copy it once.
   - Find the Project ID: Project configuration → General → Project details → Project ID.
   - In the GitHub repo: Settings → Secrets and variables → Actions → New repository secret → `NETLIFY_AUTH_TOKEN` (the token) and `NETLIFY_SITE_ID` (the Project ID).
   - Note your current **credits remaining** (Team → Billing/Usage) — Claude Code will ask for it at step 0 and again after each of the first deploys, at the end of the 48-hour soak, and at acceptance.
2. **Clone and seed.** In Terminal:
   ```
   cd ~/Documents/Claude/Projects
   git clone https://github.com/<your-username>/storm-water-tracker.git
   cp "Diplomacy Building/storm-water/CLAUDE.md" storm-water-tracker/CLAUDE.md
   mkdir -p storm-water-tracker/build-pack
   cp "Diplomacy Building/storm-water/"0*.md "Diplomacy Building/storm-water/README.md" storm-water-tracker/build-pack/
   cd storm-water-tracker && git add . && git commit -m "build pack" && git push
   ```
   (That copies `00_…` to `06_…` and the pack README into `build-pack/`, and `CLAUDE.md` to the repo root only — one copy, so it cannot drift.) You also need the GitHub CLI: `brew install gh && gh auth login` if you do not have it.
3. **Start Claude Code** in that folder (`claude`) and paste this as your first message:

   > Read CLAUDE.md, then build-pack/README.md, then build-pack/01_SPEC.md. Then open build-pack/02_PHASE1_BUILD_PLAN.md and start at step 0.1. Work one step at a time, run every CHECK exactly as written and paste its output, and stop at every GATE and wait for me. Do not add anything the plan does not ask for.

   That prompt is all it needs. At each GATE it will report; you reply "continue" (or ask questions). If it drifts — starts inventing features, skipping checks, or "fixing" a check — say: *"Re-read CLAUDE.md rules 5, 6 and 7 and go back to the last completed step."*

### What each GATE is for, and what to look at

- **GATE 0 (only if triggered)** — a company's feed didn't resolve or the overflow count is far from ~14,000. Ask Claude Code to show you the exact difference before agreeing to any spec change.
- **GATE 1 — after the first live collection.** You will see: overflow count (~14,000), events created (roughly the same number — one "latest event" per overflow), how many are ongoing, the earliest event date (it will be old — some overflows last spilled a year ago; that is expected), offline count. Also the launch timestamp. Ask one question: "Any company with zero events or missing coordinates?" Then "continue".
- **GATE 1.8 (only if triggered)** — the Hydrology API turned out not to be in UTC. Stop and think with Claude Code about the fix before changing `01_SPEC.md` §5.4. This is the one place a silent error would poison every verdict.
- **GATE 2 — after classification.** You will see verdict counts. Expect: events from the last two weeks get real verdicts (`dry_day` / `not_dry`, or `pending_rain_data` for the newest); the thousands of old seeded events show `insufficient_readings` because their rainfall has not been fetched yet — Phase 3's historic back-fill fills that in. You will also see up to five recomputed dry-day events with the EA URLs (fewer if fewer exist yet). Click one URL, look at the readings, confirm they are zeros. Then "continue".
- **GATE 3 — design.** Eight screenshots (four pages × desktop and phone). Judge against the inspiration: black, quiet, one large headline, dashes visual, one accent colour only on dry-day markers. Typical feedback: headline size, spacing, the hero visual's density. Say what to change; it re-runs the checks after.
- **GATE 4 — Phase 1 acceptance table.** Every row should say pass. If a row says fail, ask why before accepting anything.
- **GATE 2.1 / 2.3 / 2.7 and GATE 3.1 / 3.3 / 3.6** — same pattern: read the table, click one or two links, say "continue" or "accepted".

### The waiting periods, and why

- **48-hour soak after Phase 1 deploys.** The site needs real events to have flowed through the whole pipeline (poll → rain two days later → classify → deploy). The soak report shows that pending events received verdicts (some still marked provisional until their rain data is complete). Do nothing during it.
- **Radar back-fill.** Each 10-day chunk downloads ~1.35 GB inside GitHub's runners, and there are about 65 chunks back to November 2024. Claude Code queues them from the terminal with the GitHub CLI, a batch at a time, over a few days. You can tell it to stop at any point.
- **Historic rainfall back-fill (Phase 3).** One month per workflow run, about 55 runs (March 2022 to launch). Claude Code queues them a few at a time; each takes a few minutes.

### Phase 3: the only registration you need to do

Go to https://data.thameswater.co.uk/ → register → APIs (`/s/apis`) → subscribe to the storm discharge API → create an application to get a `client_id` and `client_secret` (`/s/application-listing`). Then in the repo: Settings → Secrets and variables → Actions → New repository secret → `TW_CLIENT_ID`, then `TW_CLIENT_SECRET`. Locally, create a file `.env` in the repo with the two lines `TW_CLIENT_ID=...` and `TW_CLIENT_SECRET=...` (it is git-ignored). If the portal shows API documentation, copy its text into the chat for Claude Code — it will use it in step 3.1 instead of the third-party details in the spec.

### What "done" looks like

- The live site at `https://<site-name>.netlify.app/` asks for your Netlify login and then shows four numbers, a league table, the latest dry-day spills, and the dashes visual of England. If the daily preview turned out to be free, `https://daily--<site-name>.netlify.app/` shows yesterday's data every morning; the main URL updates every Monday.
- Every dry-day event page shows the gauge, distance, rainfall totals, readings count, the EA's sentence, the rule version, and a "reproduce this" link to the EA API.
- The Method page quotes the EA verbatim, states the assumptions (UTC, 10 km, total ≤ 0.25, launch-date caveat, Hub not audited), and lists every source with its quote.
- The Actions tab shows green runs every 10 minutes (poll), daily (rain, radar), hourly (classify), weekly on Monday mornings (deploy-netlify production) and — if the free-preview test passed — daily preview deploys the other six mornings. You will also see some grey "cancelled" runs — that is the queue rule working (a third run waiting behind two others gets cancelled), not a failure.
- `NOTES_FOR_JAIMIN.md` in the repo has a dated line for every assumption Claude Code had to make. Read it once at the end.

### Things to know so nothing surprises you

- **History starts on your launch day.** The Hub has no past data. Events dated before launch are only "the last thing each overflow did" — the site labels them as such and does not count them in period totals.
- **Verdicts arrive two to three days after a spill.** The EA's rainfall API lags about two days, and the rule needs the whole day plus the previous day. "Rain check pending" is the honest state until then. A verdict made with a few readings still missing is marked "provisional" and can change until the data is complete; every such change is logged in a file you can inspect.
- **The timezone check (step 1.8) can only be done on a summer-time day.** If Claude Code reaches it after late October, it may have to wait for the EA to publish a rainy BST day or ask for a historic file — it will tell you. Starting Phase 1 before mid-October avoids this.
- **The rule is strict on purpose.** We flag a dry day only if the *total* rain over 48 hours at the nearest gauge with enough readings (within 10 km) is at most 0.25 mm. That is the reading of the EA's sentence that produces the fewest false accusations.
- **Someone else already flags dry-weather spills** (River Truth). Our difference is the EA-exact rule, the evidence per event, the archive and the per-company totals. The About page says this neutrally.
- **No one will find the site** unless you send the link; every page carries a `noindex` tag. Remove it later if you ever want it found.
- **How the Netlify credit budget works, and what it means for you.** Your Free plan has 300 credits a month with a hard limit; a production deploy costs 15; when the balance hits zero Netlify pauses *every* site on your account until the monthly reset. So the site is deployed to production **once a week (Monday 08:00 UTC)** plus at most a few manual "major update" deploys — the workflow refuses a ninth production deploy in a calendar month unless you explicitly override it. Netlify lists preview/branch deploys at 0 credits, so Claude Code tests a daily preview at a fixed URL (`daily--…`) and keeps it only if your balance genuinely does not move. Data collection never touches Netlify; it all runs on GitHub. If you ever want the very latest data on the main URL, ask Claude Code for a manual production deploy (`kind=prod`) — it counts against the 8. The other site already on your Netlify team shares the same 300 credits.
- **If GitHub ever disables the schedules** (it does after 60 days with no repository activity — our commits prevent this), Actions → the workflow → "Enable workflow".

### If you want to change something later

Change the spec first (`build-pack/01_SPEC.md`), then tell Claude Code which section changed and which plan step to redo. If the rule itself changes, it must become `dry-day-v2` with a Method-page changelog and full re-classification — Claude Code knows this from CLAUDE.md and `01_SPEC.md` §5.7.
