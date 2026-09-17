# CLAUDE.md — standing rules for building Storm Water Tracker

You are building **Storm Water Tracker**, a personal, non-commercial website that records every storm-overflow discharge published by England's water companies and flags the ones that started on a "dry day" under the Environment Agency's own definition. Read this file first, every session. Then read `README.md`, then the plan file for the phase you are in.

## The one rule the whole project rests on

The Environment Agency's definition, quoted exactly from https://environmentagency.blog.gov.uk/2024/08/28/what-are-dry-day-spills (post dated 28 August 2024):

> "A dry day spill is when a storm overflow is used on a 'dry day' – which is defined as no rainfall above 0.25mm on that day and the preceding 24 hours."

Every classification this site makes implements that sentence and nothing else. The implementation is specified in `01_SPEC.md` §5. Do not invent a different threshold, a different window, or a "smarter" rule. If you believe the spec is wrong, stop and say so — do not silently change it.

## Non-negotiables

1. **Never invent data.** Every number on the site comes from a fetched source (Stream/National Storm Overflow Hub, EA Hydrology API, Met Office radar, Thames Water API). No placeholder figures, no sample data in production files. Test fixtures live only under `tests/fixtures/` and are never read by production code.
2. **Never call anything "illegal".** The site's strongest wording is the `dry_day` badge and sub-line defined in `01_SPEC.md` §5.6 (`Dry day spill · EA definition` / `Potential breach; not confirmed.`) — use those strings exactly. The EA itself says it treats these "as a potential breach until we have confirmed through further investigation." Use the words "dry day spill", "potential breach", "flagged", "provisional", "complete rain data". Never "illegal", "criminal", "guilty", "broke the law".
3. **Show the evidence on every flagged event**: overflow name/ID, company, receiving watercourse, start time, end time, the gauge used, its distance, the rainfall totals for the window, the number of readings present vs expected, the rule version, and the classification timestamp. No flag without its evidence.
4. **Every source is quoted, linked and dated** on the Method page. The verified quotes are in `06_SOURCES.md`. Copy them exactly; do not paraphrase a quote and present it as verbatim.
5. **Stop at every GATE.** The plan files contain `GATE` steps. At a GATE you stop, report what you did and what the checks showed, and wait for Jaimin to say "continue". Do not run past a GATE.
6. **Run every CHECK as written** and paste the actual output in your report. If a check fails, fix the cause, re-run, and only then continue. Never edit a check to make it pass.
7. **Do not add features that are not in the plan.** No maps libraries, no charts libraries, no analytics, no cookies, no accounts, no comments, no dark/light toggle, no animations beyond what `01_SPEC.md` §7 allows. If something seems missing, write it in `NOTES_FOR_JAIMIN.md` and carry on.
8. **Keep the stack exactly as specified**: Python 3.12, standard library + the packages in `requirements.txt`, Jinja2 templates, plain CSS, minimal vanilla JS, GitHub Actions for all processing, Netlify (private project, manual deploys via CLI) for hosting only. No frameworks (no React, Next, Tailwind, Bootstrap), no databases beyond SQLite built in-memory at build time, no paid services.
9. **Deterministic outputs.** Every CSV the pipeline writes is sorted by a stable key and written with `\n` line endings and UTF-8, so git diffs are small and reviewable. Every timestamp is ISO 8601 in UTC with a `Z` suffix.
10. **Netlify credits are finite (300/month, hard limit; a production deploy costs 15; at zero every site on the account is paused).** Production deploys happen only through `deploy-netlify.yml`, which enforces ≤ 8 per calendar month via `scripts/deploy_guard.py`. Never run `netlify deploy --prod` from a laptop, never connect the repo to Netlify's Git integration, never add Netlify Functions/Forms/Identity/Blobs. If you think a production deploy is needed, ask Jaimin; a manual `kind=prod` run counts against the budget.
11. **Time is UTC everywhere.** A "day" is a UTC calendar day (the EA reports EDM data in GMT). This is a documented assumption (see `01_SPEC.md` §5.4) and is stated on the Method page.

## Working style

- Work one numbered step at a time, in order. Before starting a step, print its number and title. After finishing, run its CHECK and print the output.
- When a step says "verify by fetching", actually fetch the URL with `curl -s` (or Python `requests`) and read the response. Do not assume.
- Prefer small, single-purpose scripts under `scripts/` with a `--help` and clear exit codes (0 ok, 1 check failed, 2 network error).
- Commit after each completed step with the message format `step 1.4: <what>`. Never commit secrets. `.env` is git-ignored.
- If a live source is unreachable, retry three times with backoff, then stop and report — do not substitute data.
- Keep `NOTES_FOR_JAIMIN.md` at the repo root: anything you were unsure about, any assumption you had to make, any source that behaved differently from `01_SPEC.md`. Plain English, dated entries. Prefix an entry that still needs Jaimin's decision with `[OPEN]` and remove the prefix once resolved — checks treat any remaining `[OPEN]` as unresolved.

## Files in the build pack and what they are for

In the repository the build pack lives in `build-pack/`; the file names below are relative to that folder (this `CLAUDE.md` is copied to the repo root).

| File | Read when |
|---|---|
| `README.md` | Start of every session — orientation and phase status |
| `01_SPEC.md` | Before writing any code — sources, schema, rule, design |
| `02_PHASE1_BUILD_PLAN.md` | Phase 1: the general site (collector, rain, classifier, static site, deploy) |
| `03_PHASE2_RADAR_PLAN.md` | Phase 2: Met Office radar second opinion |
| `04_PHASE3_THAMES_BACKTEST_PLAN.md` | Phase 3: Thames Water history back to April 2022 |
| `05_CHECKS_AND_ACCEPTANCE.md` | Final QA protocol before each phase is declared done |
| `06_SOURCES.md` | Verified links and verbatim quotes for the Method page |
| `00_JAIMIN_GUIDE.md` | Not for you — Jaimin's own guide. Do not edit it. |
