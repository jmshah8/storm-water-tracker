# 05 — Checks and acceptance

Two kinds of checks exist in this project. **Step CHECKs** live in the plan files and run after each step. **Acceptance** (this file) runs at the end of each phase and is reported at the phase's final GATE as a table with one row per item: `item | expected | observed | pass/fail`. Every item must pass, or be listed under "Known exceptions" with Jaimin's explicit acceptance.

All of this is implemented in `scripts/check.py --acceptance phase1|phase2|phase3` so it can be re-run at any time. Where an item says "by inspection", Claude Code performs the inspection and writes what it saw.

---

## Phase 1 acceptance

### A. Correctness of the rule
| # | Item | Expected |
|---|---|---|
| A1 | `tests/test_rule.py` boundary cases | pass, incl. total = 0.25 → dry, 0.26 → not dry |
| A2 | Independent recomputation of 10 random `dry_day` events from the Hydrology API | all within 0.01 mm and ≤ 0.25 |
| A3 | Independent recomputation of 10 random `not_dry` events | all within 0.01 mm and > 0.25 |
| A4 | Timezone verification (step 1.8) recorded in NOTES and on Method page | present, offset 0 h |
| A5 | No `dry_day` verdict uses fewer than 176 readings; no `is_final` verdict violates §5.3's finality conditions | 0 violations |
| A6 | No `dry_day` verdict uses a gauge > 10.0 km away | 0 violations |
| A7 | Every event has exactly one classification row | counts equal |

### B. Correctness of the collector
| # | Item | Expected |
|---|---|---|
| B1 | Overflow count vs live feed counts (re-query now) | within ±2% |
| B2 | Event IDs unique across all monthly files | yes |
| B3 | No event with `end_utc` < `start_utc` | 0 |
| B4 | Share of events with `end_observed = false` | report; expect < 5% |
| B5 | Idempotence: run `collect.py` twice with `--fixture` | identical output |
| B6 | Poll workflow: share of runs with conclusion `success` among runs that were not `cancelled`, last 48 h (`gh run list`) | ≥ 97% |
| B7 | `verdict_changes.csv` reviewed: number of `dry_day`→`not_dry` flips since launch | report (expect few; each explained by late rain data) |

### C. Site integrity
| # | Item | Expected |
|---|---|---|
| C1 | HTML parses with html5lib strict, all pages | 0 errors |
| C2 | Internal links resolve | 0 broken |
| C3 | Numbers on pages equal CSV recomputation (`data-value`) | exact |
| C4 | Forbidden words (`illegal`, `criminal`, `guilty`) | 0 |
| C5 | Each `dry_day` and `pending_rain_data` event has a page; no others | yes |
| C6 | Every quote/link marked `[method]` in `06_SOURCES.md` present verbatim in `method.html` | 0 missing |
| C7 | Footer timestamps on the most recent deploy (production, or daily alias if enabled) are consistent with its `deploy_log.json` time (poll within 2 h of the deploy; rain within 26 h) | yes |
| C8 | Production URL: when logged out of Netlify the response body is Netlify's access page (no `storm water tracker` wordmark; paste the HTTP status, whatever it is); when Jaimin is logged in the site renders; CSVs downloadable | yes |
| C10 | Netlify project has **no** linked Git repository (`netlify sites:list --json` → `build_settings.repo_url` empty); visibility Private for production and previews (by inspection in the UI) | yes |
| C11 | `data/deploy_log.json`: production deploys this calendar month ≤ 8; every entry has `utc, kind, run_url, message, deploy_url`; `deploy_guard.py` tests pass | yes |
| C12 | Credits remaining read by Jaimin in the Netlify UI at acceptance, written in NOTES; expected ≈ 300 − 15 × (production deploys by every site on the team this month) − 20 (requests/bandwidth) — report the figure and explain any larger gap | report |
| C9 | No periods before `launch_utc` shown as complete; launch month labelled partial | by inspection |

### D. Design
| # | Item | Expected |
|---|---|---|
| D1 | Contrast ratios (text, muted, flag on bg and surface) | all ≥ 4.5:1 |
| D2 | No horizontal scroll at 390 px | yes |
| D3 | Hero headline and nav visible above the fold at 1440×900 | yes |
| D4 | Only the eleven colour literals of §7.1 appear in `static/style.css` and `templates/` | grep for `#[0-9a-fA-F]{3,8}`, `rgb(`, `rgba(`, `hsl(` — every hit is one of the eleven §7.1 values |
| D5 | No external scripts except Google Fonts CSS | yes |
| D6 | Screenshots reviewed by Jaimin at GATE 3 | accepted |

### E. Hygiene
| # | Item | Expected |
|---|---|---|
| E1 | No secrets in repo (`git grep -iE "client_secret|netlify_auth|nfp_"`, `.env` ignored) | clean |
| E2 | `NOTES_FOR_JAIMIN.md` contains no `[OPEN]` marker | 0 |
| E3 | Method page states: UTC assumption (with the BST-day verification date), 10 km assumption, total-vs-max choice, provisional-vs-final rule, lag, what can be missed, Hub "not audited" caveat, launch-date caveat, ST Connect placeholder feed | all present |
| E4 | Data page states licences: site CC BY 4.0; Hub CC BY 4.0; EA OGL v3 | present |

---

## Phase 2 acceptance

| # | Item | Expected |
|---|---|---|
| R1 | Radar reader unit tests | pass |
| R2 | Geographic sanity (5 cities in bounds and ordered correctly) | pass |
| R3 | Radar-vs-gauge rank correlation on a wet day (40 points) | > 0.6 |
| R4 | Daily radar files: no missing UTC day from oldest available to yesterday | 0 missing (gaps listed if any) |
| R5 | Every `dry_day` event page with `radar_status = complete` shows the radar block | yes |
| R6 | "Radar agrees" columns equal CSV recomputation | exact |
| R7 | Verdicts unchanged by radar: on a frozen copy of `data/`, run `classify.py` with the radar files present and with them temporarily moved away; compare `verdict` per `event_id` | 0 differences |
| R8 | Data page states CC BY-SA for radar-derived columns; Met Office attribution in footer | present |
| R9 | Radar workflow: share of non-cancelled runs with conclusion `success` over 7 days | ≥ 90% |
| R10 | `always_xy=True` present in the Transformer construction; five-city test still passes | yes |

## Phase 3 acceptance

| # | Item | Expected |
|---|---|---|
| T1 | API contract recorded in NOTES (endpoints, headers, pagination, earliest date, `DateTime` timezone finding) | present |
| T2 | Location mapping matched (ID or ≤ 100 m) | ≥ 90% |
| T3 | Overlap validation: Thames API events vs Hub events within ±15 min | ≥ 90% |
| T4 | Historic rainfall: every day 2022-03-31 → launch has a daily file | yes |
| T5 | Ten random pre-launch Thames `dry_day` events recomputed from Hydrology API | all within 0.01 mm and ≤ 0.25 |
| T6 | Back-test page numbers equal CSV recomputation | exact |
| T7 | Back-test page carries both cautions and the "method, not reconciliation" line | present |
| T8 | No secrets in repo; secrets present in Actions | yes |

---

## Standing rule for all checks

A check that fails is fixed at its cause. A check is never edited, weakened, skipped or marked "flaky" to make the table green. If a check is genuinely wrong, say so at the GATE and propose the correction; Jaimin decides.
