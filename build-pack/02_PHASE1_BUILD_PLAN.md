# 02 — Phase 1 build plan: the general site

Read `CLAUDE.md` and `01_SPEC.md` first. Work the steps in order. Each step ends with a **CHECK** you must run and whose output you must paste into your report. A **GATE** means: stop, report, wait for Jaimin to say "continue". Mark each step `[x]` here when its CHECK passes.

Conventions in this file: `$REPO` is the local clone of `storm-water-tracker`. Commands are run from `$REPO`. "Report" means a short plain-English message to Jaimin: what you did, the CHECK output, anything unexpected.

---

## Step 0 — Pre-flight (Jaimin does this; Claude Code verifies)

Jaimin will have:
1. Created a **public** GitHub repository named `storm-water-tracker` (empty, no README).
2. In the repo: Settings → Actions → General → Workflow permissions = **Read and write permissions** (needed so workflows can commit data). GitHub Pages is **not** used.
3. Cloned it locally and copied `CLAUDE.md` from this pack into the repo root and the pack into `build-pack/`.
4. Python 3.12, `git`, Node 20+ (`node --version`) and the GitHub CLI `gh` (logged in: `gh auth status`) available locally. `gh` is required — later checks count workflow runs with it.
5. **Netlify (the site host, private, Free plan):**
   a. Logged in to the Netlify CLI locally: `npx netlify-cli@latest login`.
   b. Created a **manual-deploy** project, not connected to any Git repository: `npx netlify-cli@latest sites:create --name storm-water-tracker` (if the name is taken, pick another and use it consistently). Never use "Import an existing project" / "Add new project from Git" for this site.
   c. In the Netlify UI: Project configuration → General → Visitor access → **Project visibility** → set **production deploys = Private** and **previews = Private**. (Free plan: "private projects can only be seen by the Team Owner" — that is Jaimin.)
   d. Created a Netlify **personal access token** (User settings → Applications → Personal access tokens) and added two GitHub Actions secrets: `NETLIFY_AUTH_TOKEN` (the token) and `NETLIFY_SITE_ID` (Project configuration → General → Project details → Project ID).
   e. Noted the current **credits remaining** shown in the Netlify UI (Team → Billing/Usage) and written it in `NOTES_FOR_JAIMIN.md` as `Netlify credits remaining at start: N of 300 (date)`.

- [x] **0.1 Verify pre-flight.**
  Run: `git remote -v`, `python3 --version`, `node --version`, `gh auth status`, `gh repo view --json isPrivate,name`, `gh secret list`, `npx netlify-cli@latest status` and `npx netlify-cli@latest sites:list --json` (look for the project and confirm it has **no** linked repository: the JSON `build_settings.repo_url` is empty/null).
  **CHECK 0.1:** remote points at `storm-water-tracker`; Python ≥ 3.12; Node ≥ 20; `gh` authenticated; `isPrivate` is `false`; secrets `NETLIFY_AUTH_TOKEN` and `NETLIFY_SITE_ID` exist; the Netlify project exists with no linked repo; the credit balance line is in NOTES. If any item fails, stop and tell Jaimin exactly which.

- [x] **0.2 Note the site name** from `sites:list` (e.g. `storm-water-tracker`); step 1.1 writes it into `data/meta.json.site_url` as `https://<site-name>.netlify.app/`.

---

## Step 1 — Scaffold

- [x] **1.1 Create the skeleton** exactly as in `README.md` ("Repository that Claude Code will create"), with empty `__init__.py` files, an empty `data/` tree, and these files:
  - `requirements.txt` (installed by every workflow):
    ```
    requests==2.32.*
    jinja2==3.1.*
    html5lib==1.1
    ```
    and `requirements-dev.txt` (local only): `-r requirements.txt`, `pytest==8.*`, `playwright==1.*` (Playwright is used only for design QA screenshots in step 1.13; the browser is installed then).
  - `.gitignore`: `.env`, `__pycache__/`, `*.pyc`, `site/`, `.cache/`, `.pytest_cache/`, `screenshots/`.
  - A `.gitkeep` file in every empty directory of the tree (`data/events/`, `data/offline/`, `data/rain/daily/`, `data/classification/`, `tests/fixtures/`, `static/`, `templates/`, `.github/workflows/`) so the directories exist in git.
  - `README.md`: two paragraphs (what the site is; how to run locally) plus a pointer to `CLAUDE.md`.
  - `NOTES_FOR_JAIMIN.md`: heading and a first dated line "Scaffold created".
  - `data/meta.json`: `{"launch_utc": null, "rule_version": "dry-day-v1", "site_url": "https://<site-name>.netlify.app/"}` — the site name from step 0.1's `sites:list`.
  - `data/deploy_log.json`: `[]`.
  Create a virtualenv (`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`).
  **CHECK 1.1:** `find . \( -path ./.venv -o -path ./.git \) -prune -o -type f -print | sort` lists the `.gitkeep`s (proving every directory of the README tree exists: scripts/, swt/, templates/, static/, data/…, tests/fixtures/, .github/workflows/) and the files listed for step 1.1; files belonging to later steps are expected to be absent. `python -c "import requests, jinja2, html5lib; print('ok')"` prints `ok`. Commit: `step 1.1: scaffold`.

---

## Step 2 — Verify the discharge feeds are exactly as specified

- [x] **1.2 Write `scripts/sources.py`.** It contains the ten `(company_slug, company_name, item_id)` tuples from `01_SPEC.md` §2.1 and a function `resolve_all()` that, for each item: fetches `https://www.arcgis.com/sharing/rest/content/items/{item_id}?f=json`, reads `url` and `licenseInfo`; fetches `{url}/0?f=pjson`; builds a **field-alias map** from the layer's actual field names to the ten logical names (`Id, Company, Status, StatusStart, LatestEventStart, LatestEventEnd, Longitude, Latitude, ReceivingWaterCourse, LastUpdated`) by case-insensitive match, additionally accepting `LatestEventFinish` for `LatestEventEnd` (see §2.1 — South West Water is camelCase; ST Connect uses `LatestEventFinish`); fails the company if any logical field is unmapped; checks the status field's coded-value domain case-insensitively for codes `{1: "Start", 0: "Stop", -1: "Offline"}` (if a service publishes no domain, report `domain=absent` and continue — the codes are assumed identical; if it publishes a *different* domain, fail the company); records `maxRecordCount` and `supportsPagination`; fetches `{url}/0/query?where=1%3D1&returnCountOnly=true&f=json` for the record count; writes `scripts/sources_resolved.json` (sorted keys) including the alias map per company. Also export `load_sources()` that reads the resolved JSON (used by `collect.py`).
  Run `python scripts/sources.py`.
  **CHECK 1.2:** output table shows 10 rows; every row `fields=mapped domain=ok pagination=true` with the alias map printed where it is not the canonical spelling (expect two: `south-west` camelCase, `st-connect` `LatestEventFinish`); the `licenseInfo` text for each (expect "CC BY 4.0" on nine; ST Connect's is empty — report it, not a failure); a count per company (expect ST Connect = 1 — a placeholder feed — report it). Sum of counts should be roughly 13,000–15,500 (the Hub says 14,187 overflows). If any company cannot be mapped/resolved or the sum is outside that range → **GATE 0** (report; the data page may have changed). Commit: `step 1.2: sources verified`.

---

## Step 3 — The collector

- [x] **1.3 Write `swt/io.py`, `swt/timeutil.py`, and `scripts/collect.py`** implementing `01_SPEC.md` §4 exactly.
  - `swt/io.py`: `read_csv(path) -> list[dict]`, `write_csv(path, rows, fieldnames, sort_key)` (UTF-8, `\n`, sorted, no trailing spaces), `read_json/write_json` (sorted keys, 2-space indent, trailing newline).
  - `swt/timeutil.py`: `ms_to_iso(ms) -> "YYYY-MM-DDTHH:MM:SSZ"`, `iso_to_ms`, `now_iso()`, `utc_day(iso) -> "YYYY-MM-DD"`.
  - `scripts/collect.py --sources scripts/sources_resolved.json --data data/ [--dry-run] [--fixture PATH] [--now ISO]`. `--fixture` reads a JSON file shaped exactly like the ArcGIS query responses (`{"<company_slug>": {"features": [{"attributes": {...}}]}}`) instead of the network (tests only) and **requires** `--now`; `--now` fixes the clock so outputs are reproducible. If `data/meta.json` is absent in the target `--data` directory, create it with `launch_utc: null`. On first ever run (when `launch_utc` is null) set `launch_utc` to now and write it. Exit code 0 always unless a network/parse error (exit 2).
  - Tests must not touch the network: they pass `--sources tests/fixtures/sources_fixture.json` (a hand-written resolved-sources file with alias maps for a canonical company, a camelCase company and a `LatestEventFinish` company).
  - Write `tests/test_collect.py` with fixtures under `tests/fixtures/` covering: new overflow; new event with end; new event ongoing then end appears; near-duplicate start within 15 min keeps the original `event_id`; inferred end when a newer event appears; offline open/close; camelCase and `LatestEventFinish` aliases normalised; determinism (running twice with the same `--now` on the same fixture produces byte-identical outputs).
  **CHECK 1.3:** `pytest -q` → all pass. Idempotence, explicitly:
  ```
  rm -rf /tmp/swt_a /tmp/swt_a_copy
  python scripts/collect.py --sources tests/fixtures/sources_fixture.json --fixture tests/fixtures/snapshot_a.json --data /tmp/swt_a --now 2026-01-01T00:00:00Z
  cp -r /tmp/swt_a /tmp/swt_a_copy
  python scripts/collect.py --sources tests/fixtures/sources_fixture.json --fixture tests/fixtures/snapshot_a.json --data /tmp/swt_a --now 2026-01-01T00:10:00Z
  diff -r /tmp/swt_a /tmp/swt_a_copy && echo IDEMPOTENT
  ```
  prints `IDEMPOTENT` — note the second run uses a *later* `--now`: with an unchanged feed, no CSV may change; only `status_snapshot.json`'s `observed_utc` may differ, so exclude it: `diff -r -x status_snapshot.json /tmp/swt_a /tmp/swt_a_copy && echo IDEMPOTENT`. Commit: `step 1.3: collector + tests`.

- [x] **1.4 First live collection.** Run `python scripts/collect.py`. This seeds the archive with the latest known event per overflow.
  **CHECK 1.4:** (a) `wc -l data/overflows.csv` minus 1 equals the sum of counts from CHECK 1.2 within ±2%; (b) `python - <<'EOF'` script prints: number of overflows, number of events created, number with empty `end_utc` (ongoing), earliest and latest `start_utc`, number of offline periods; (c) `data/meta.json.launch_utc` is now set; (d) every `event_id` is unique across all `data/events/*.csv`; (e) report the number of overflow rows with empty `latitude`/`longitude` (expected 0; if not 0, report which companies — those overflows cannot be classified and are counted on the Method page). Paste the numbers. Commit: `step 1.4: first live collection (launch)`.

  > Note for the Method page (write it into `NOTES_FOR_JAIMIN.md` now): events with `start_utc` earlier than `launch_utc` are only "the most recent event per overflow at launch", not a complete record. The site must not show league tables or monthly counts for any period before `launch_utc`'s month, and must label that month "partial (from {launch date})".

- [ ] **1.5 GATE 1.** Report: CHECK 1.2 and 1.4 numbers, anything odd in the feeds (companies with zero events, records without coordinates, duplicate `Id`s). Wait.

---

## Step 4 — Automate the collector

- [ ] **1.6 Write `.github/workflows/poll.yml`** per `01_SPEC.md` §9.3. Reference:
  ```yaml
  name: poll
  on:
    schedule: [{cron: "*/10 * * * *"}]
    workflow_dispatch:
  concurrency: {group: data-writers, cancel-in-progress: false}
  permissions: {contents: write}
  jobs:
    poll:
      runs-on: ubuntu-latest
      timeout-minutes: 8
      steps:
        - uses: actions/checkout@v7
          with: {fetch-depth: 1}
        - uses: actions/setup-python@v7
          with: {python-version: "3.12", cache: pip}
        - run: pip install -r requirements.txt
        - run: python scripts/collect.py
        - name: commit if changed
          run: |
            git config user.name "swt-bot"
            git config user.email "swt-bot@users.noreply.github.com"
            git add data
            if git diff --cached --quiet; then echo "no changes"; exit 0; fi
            git commit -m "poll: $(date -u +%FT%TZ)"
            for i in 1 2 3; do git pull --rebase && git push && break || sleep 5; done
  ```
  Push, then trigger once manually (`workflow_dispatch`) and wait for one scheduled run.
  **CHECK 1.6:** `gh run list --workflow poll --limit 5` shows two `success` runs (one manual, one scheduled); `git log --oneline -5` on `main` shows at least one `poll:` commit (or "no changes" in the log if nothing changed — then wait for the next run in which something did). Paste the run URLs. Commit: `step 1.6: poll workflow`.

---

## Step 5 — Rainfall

- [x] **1.7 Write `scripts/rain.py`** per `01_SPEC.md` §6 with `--refresh-gauges` and `--days N` (default 15) flags. Gauges: stations with a 15-min rainfall measure and non-null `lat`/`long`. Readings: one request per gauge per run, `mineq-date = today−N`, `max-date = today`, CSV format; pace ≤ 5 requests/second; retry ×3 with backoff on 5xx; on persistent failure record the gauge in the run log and continue. Write `data/rain/daily/{date}.csv` for each day in the window (rewrite whole files; unchanged content → no diff).
  Run `python scripts/rain.py --refresh-gauges --days 15`.
  **CHECK 1.7:** (a) `data/rain/gauges.csv` has ≥ 600 rows (the EA lists ~1,000 telemetered gauges; the Hydrology API may list more, including closed ones — report the exact number); (b) fifteen daily files exist; (c) for ≈ today−3 (the most recent day that is normally complete given the ~2-day lag), print the distribution of `n_readings`: share of gauges with 96, with 88–95, with < 88 — expect a clear majority at 96; also print the same for today−1 and today−2 so the lag is visible; (d) print the 5 gauges with the highest `total_mm` on today−3 and eyeball that values are plausible (0–60 mm). Record the observed lag in `NOTES_FOR_JAIMIN.md`. Commit: `step 1.7: rainfall pipeline`.

- [x] **1.8 Verify the timezone assumption (this decides correctness of every verdict).**
  Write `scripts/check.py --step 1.8`. Method: take the 15-min rainfall stations from the real-time API (`https://environment.data.gov.uk/flood-monitoring/id/stations?parameter=rainfall&_limit=5000`, fields `stationReference`, `lat`, `long`, measure `@id`), match ≥ 5 stations to Hydrology gauges by `stationReference` (both APIs expose it; fall back to coordinates within 100 m only if a reference is missing), pick a recent day **that falls in British Summer Time** (late March → late October; the test is only discriminating when local time ≠ UTC) on which each matched gauge recorded ≥ 5 mm, fetch both series for that day (real-time: `.../id/measures/{id}/readings?date=YYYY-MM-DD&_limit=500`, timestamps end in `Z`; Hydrology: `.../hydrology/id/measures/{measure}/readings?mineq-date=YYYY-MM-DD&max-date=<next day>`), and align them. Report, per gauge, the time offset that maximises agreement (0 h ⇒ Hydrology is UTC; +1 h ⇒ Hydrology is local time).
  **CHECK 1.8:** the offset is consistent across the ≥ 5 gauges **and** the sample day is in BST. If 0 h: record "Hydrology API dateTime confirmed UTC on {date} (BST day)" in `NOTES_FOR_JAIMIN.md` and on the Method page. **If not 0 h, or if no BST day with ≥ 5 mm is available inside the real-time API's ~4-week window: STOP — GATE 1.8** — report as "inconclusive", never as "confirmed", and do not proceed until Jaimin decides (options: wait for a BST rain day; or request an offline historic supply from the EA for one gauge). Commit: `step 1.8: timezone verified`.

---

## Step 6 — The rule and the classifier

- [x] **1.9 Write `swt/geo.py`, `swt/rule.py`, `scripts/classify.py`.**
  - `swt/geo.py`: `haversine_km(lat1, lon1, lat2, lon2)`; `nearest_gauges(lat, lon, gauges, max_km=10.0) -> list sorted by distance`.
  - `swt/rule.py`: `classify_event(start_utc, gauge_candidates, rain_lookup, now_utc, rule_version="dry-day-v1") -> dict` implementing `01_SPEC.md` §5.2–5.3 as a pure function (no I/O). `rain_lookup(gauge_id, date) -> {total_mm, max15_mm, n_readings} | None`.
  - `tests/test_rule.py` covering at least: window total exactly 0.25 → `dry_day`; 0.26 → `not_dry`; max15 0.30 but total 0.30 → `not_dry` (total rule); nearest gauge has 170 readings, second-nearest has 192 → second chosen; no gauge within 10 km → `no_gauge_within_10km`; candidates all < 176 readings and `now < window_end + 72 h` → `pending_rain_data`; same but `now ≥ window_end + 72 h` → `insufficient_readings`; event on a UTC-day boundary (23:59:59Z vs 00:00:00Z) lands in the right day and window; `verdict_basis == "total"`, `rule_version` echoed; `is_final` false at 180 readings within 14 days, true at 192 readings, true at 180 readings after 14 days.
  - `scripts/classify.py`: loads all events, gauges and daily rain files, classifies **every** event per §5.3 (re-evaluating everything that is not `is_final`; never changing a final verdict unless `--force`), appends flips between `dry_day` and `not_dry` to `verdict_changes.csv`, writes `all_events_classified.csv` and `dry_day_spills.csv` deterministically.
  Run `pytest -q` then `python scripts/classify.py`.
  Expect at this point: only events whose 48-hour window falls inside the 15 days of rain fetched can get a real verdict; the thousands of seeded events older than that will be `insufficient_readings` (their rain is fetched in Phase 3's historic back-fill) — say so in the report, it is expected. Also expect `is_final` to be false for almost everything at this stage.
  **CHECK 1.9:** (a) tests pass; (b) print verdict counts and `is_final` counts; every event has exactly one row and a verdict; (c) every `dry_day` row has non-empty `gauge_id, gauge_distance_km, rain_day_mm, rain_prev24_mm, rain_window_total_mm, rain_window_max15_mm, n_readings_present`; (d) **independent recomputation**: `scripts/check.py --step 1.9` picks up to 5 random `dry_day` events (if fewer than 5 exist yet, use all that exist and say so), re-fetches the two days of readings for their gauge directly from the Hydrology API, recomputes the window total, and asserts it matches `rain_window_total_mm` within 0.01 mm and is ≤ 0.25 — print the URLs and totals; (e) `verdict_changes.csv` exists with its header. Commit: `step 1.9: rule + classifier`.

- [ ] **1.10 GATE 2.** Report verdict counts, the five recomputed events with their URLs, the timezone result, and the share of events still `pending_rain_data`. Wait.

---

## Step 7 — The site

- [x] **1.11 Templates, CSS and `scripts/build_site.py`** per `01_SPEC.md` §7–8. Build into `site/`. Every number shown on a page must also be present as a `data-value` attribute on its element (used by the check). Period logic: "last 30 days" = the 30 UTC days ending yesterday; "this year" = from max(1 Jan, `launch_utc`) — label accordingly. Suppress any period before `launch_utc`.
  Run `python scripts/build_site.py`.
  **CHECK 1.11:** `python scripts/check.py --step 1.11` does all of: (a) parse every HTML file with `html5lib` in strict mode — zero parse errors; (b) every internal `href`/`src` is **relative** (none starts with `/`) and resolves to a file in `site/`; (c) apart from `events/index*.html`, there is one `events/*.html` per `dry_day` and per `pending_rain_data` event and no others; (d) recompute the four index tiles and the league table from the CSVs and compare with the `data-value` attributes — exact match; (e) grep the whole `site/` for the words `illegal`, `criminal`, `guilty` (case-insensitive) — zero hits; (f) every page has `<title>`, meta description, and `noindex`. Commit: `step 1.11: site builder`.

- [x] **1.12 Hero visual.** `scripts/build_site.py --hero-only` generates `static/england-overflows.svg` from `data/overflows.csv`: project lon/lat with a simple equirectangular scaling (cos of mean latitude for x) into a 900×1100 viewBox, take a deterministic stratified sample of ≤ 4,500 overflows (sort by `overflow_key`, take every k-th), draw each as `<rect width="3" height="1">` in `--faint`, and draw overflows with a `dry_day` verdict in the last 30 days as width 5 in `--flag`. Include `role="img"` and `aria-label="Storm overflows in England drawn as dashes; highlighted dashes are dry day spills in the last 30 days"`.
  **CHECK 1.12:** file size ≤ 400 KB; rect count 3,500–4,500 (+ the flagged ones); all projected coordinates fall inside the viewBox; the outline is recognisably England (open the SVG and look at it — say what you see). Commit: `step 1.12: hero visual`.

- [x] **1.13 Design QA.** `playwright install chromium`; `python scripts/check.py --step 1.13` serves `site/` locally, screenshots `index.html`, one company page, one dry-day event page (or a `pending_rain_data` page if no dry-day event exists yet) and `method.html` at 1440×900 and 390×844 into `screenshots/`, and computes WCAG contrast ratios for the palette pairs in `01_SPEC.md` §7.8 from the CSS variables.
  **CHECK 1.13:** all contrast pairs ≥ 4.5:1 (print the ratios); no horizontal scrollbar at 390 px (check `document.documentElement.scrollWidth <= 390`); the hero headline is fully visible above the fold at 1440×900; the nav pill is visible. Then **GATE 3**: send Jaimin the eight screenshots and wait for design feedback. Apply feedback, re-run CHECK 1.13, commit `step 1.13: design QA`.

- [x] **1.14 Method page content check.** `scripts/check.py --step 1.14`: for every quote in `06_SOURCES.md` marked `[method]`, assert the exact string appears in the **HTML-unescaped** text of `site/method.html` (Jinja2 autoescaping turns `'` into `&#39;`; compare after `html.unescape()` and whitespace-normalisation of runs of spaces only — never alter the quote), and every link marked `[method]` appears as an `href`.
  **CHECK 1.14:** zero missing quotes, zero missing links. Commit: `step 1.14: method page verified`.

---

## Step 8 — Deploy

- [x] **1.15a Write `.github/workflows/rain.yml`, `classify.yml` and `deploy-netlify.yml`** per `01_SPEC.md` §9.3. `classify.yml` commits classification CSVs and **does not deploy**. Write `scripts/deploy_guard.py` with unit tests (month boundary; 7 vs 8 `prod` entries; `--override true`; `--record` appends `{utc, kind, run_url, message, deploy_url}` from the CLI's JSON output and keeps the file sorted by `utc`). `check.py` must import Playwright lazily inside `--step 1.13` only, because the deploy job installs `requirements.txt` alone. Reference for `deploy-netlify.yml` (adapt only names, not logic):
  ```yaml
  name: deploy-netlify
  on:
    schedule:
      - cron: "0 8 * * 1"        # Monday: production
      # - cron: "0 8 * * 0,2-6"  # Tue–Sun: alias — enable only after step 1.15b
    workflow_dispatch:
      inputs:
        kind: {type: choice, options: [alias, prod], default: alias}
        override_budget: {type: boolean, default: false}
  concurrency: {group: netlify-deploy, cancel-in-progress: false}
  permissions: {contents: write}
  env:
    KIND: ${{ github.event_name == 'schedule' && (github.event.schedule == '0 8 * * 1' && 'prod' || 'alias') || inputs.kind }}
    OVERRIDE: ${{ github.event_name == 'workflow_dispatch' && inputs.override_budget || 'false' }}
    NETLIFY_AUTH_TOKEN: ${{ secrets.NETLIFY_AUTH_TOKEN }}
    NETLIFY_SITE_ID: ${{ secrets.NETLIFY_SITE_ID }}
  jobs:
    deploy:
      runs-on: ubuntu-latest
      timeout-minutes: 15
      steps:
        - uses: actions/checkout@v7
        - uses: actions/setup-python@v7
          with: {python-version: "3.12", cache: pip}
        - run: pip install -r requirements.txt
        - run: python scripts/build_site.py
        - run: python scripts/check.py --step 1.11
        - uses: actions/setup-node@v5
          with: {node-version: "22"}
        - name: budget guard
          run: python scripts/deploy_guard.py --kind "$KIND" --override "$OVERRIDE"
        - name: deploy
          run: |
            set -euo pipefail
            if [ "$KIND" = prod ]; then TARGET="--prod"; else TARGET="--alias daily"; fi
            npx --yes netlify-cli@latest deploy --dir=site --no-build --json \
              --message "swt $KIND $(date -u +%FT%TZ) ${GITHUB_SHA::7}" $TARGET > deploy.json
            cat deploy.json
        - name: record and commit
          run: |
            python scripts/deploy_guard.py --record deploy.json --kind "$KIND" \
              --run-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
            git config user.name "swt-bot"; git config user.email "swt-bot@users.noreply.github.com"
            git add data/deploy_log.json
            git diff --cached --quiet && exit 0
            git commit -m "deploy: $KIND $(date -u +%FT%TZ)"
            for i in 1 2 3; do git pull --rebase && git push && break || sleep 5; done
  ```
  Notes: the Netlify CLI reads `NETLIFY_AUTH_TOKEN` and `NETLIFY_SITE_ID` from the environment, so the token never appears on a command line; at this step run `npx netlify-cli@latest --version`, then **pin that major** (e.g. `netlify-cli@<major>`) in the workflow and note it in NOTES; the deploy job is in its own concurrency group (`netlify-deploy`) and **not** in `data-writers`, so a queued Monday deploy cannot be cancelled by the poller — the `git pull --rebase` retry handles the race for the one-file commit.
  Trigger `rain.yml` and `classify.yml` manually; then trigger `deploy-netlify.yml` manually with `kind=alias`.
  **CHECK 1.15a:** three green runs; `data/deploy_log.json` has one `alias` entry with `deploy_url` of the form `https://daily--<site>.netlify.app`; opening that URL **while logged out of Netlify** shows Netlify's access page (text says you don't have access — paste the HTTP status `curl -sI` returns, whatever it is, and confirm the page body does not contain the wordmark `storm water tracker`); opening it while logged in shows the site with the footer's "last poll" within 2 hours. Commit: `step 1.15a: workflows + first alias deploy`.

- [x] **1.15b Decide whether daily alias deploys are free.** Jaimin reads the **credits remaining** figure in the Netlify UI (Team → Billing/Usage) now — after the one alias deploy in 1.15a — and writes it in NOTES; compare it with the Step 0(e) reading (which bracketed alias deploy #1). Then run `deploy-netlify.yml` manually with `kind=alias` once more, wait 10 minutes, read the balance again and write it down (brackets alias deploy #2).
  **CHECK 1.15b:** if neither alias deploy moved the balance → un-comment the Tue–Sun alias cron and write `Alias deploys verified 0 credits on {date}` in NOTES. If either did → leave the alias cron commented out (manual alias deploys stay available for testing), write the observed cost in NOTES, and the site updates weekly only. Commit: `step 1.15b: alias policy decided`.

- [ ] **1.15c First production deploy.** Run `deploy-netlify.yml` manually with `kind=prod`.
  **CHECK 1.15c:** green run; `deploy_log.json` has one `prod` entry; `https://<site>.netlify.app/` requires Netlify login when logged out and shows the site when logged in; `data/classification/dry_day_spills.csv` is downloadable from the site (copied into `site/data/` at build); Netlify credits remaining dropped by 15 (Jaimin reads it; write it in NOTES). Commit: `step 1.15c: first production deploy`.

- [ ] **1.16 Soak for 48 hours.** Do nothing except observe. After 48 h run `python scripts/check.py --step 1.16` (uses `gh run list --workflow poll --limit 300 --json status,conclusion,createdAt`): counts of poll runs in the last 48 h (expect ≥ 250), runs with conclusion `failure` (expect ≤ 3 — `cancelled` runs are expected under the concurrency rule and are not failures), events added since launch, verdicts that moved from `pending_rain_data` to `dry_day`/`not_dry` (expect most events with `window_end` older than 3 days to have moved), rows in `verdict_changes.csv`, and the observed Hydrology lag (latest complete rain day vs today).
  Also: number of Netlify deploys in `deploy_log.json` this month by kind, and the credits remaining Jaimin reads now (write it in NOTES) — expect about 300 − 15 × (production deploys by every site on the team this month) − a few credits of requests.
  **CHECK 1.16:** the numbers above; no workflow is disabled (`gh workflow list` shows all `active`); `grep -c "\[OPEN\]" NOTES_FOR_JAIMIN.md` is 0; `prod` deploys this month ≤ 8.

- [ ] **1.17 Phase 1 acceptance.** Run the full protocol in `05_CHECKS_AND_ACCEPTANCE.md` §Phase 1. **GATE 4**: report the acceptance table. When Jaimin says "accepted", set Phase 1 status to `done (YYYY-MM-DD)` in this pack's `README.md` and in the repo README.

---

## If something in the feeds changes mid-build

Feed field renamed or a company's dataset moved → `collect.py` exits 2 (§4.2a) and `sources.py` fails its mapping when re-run. Do not patch around it: re-run `python scripts/sources.py`, report the exact difference, propose the minimal change to `01_SPEC.md` §2.1 (usually one more alias), and wait for Jaimin.
