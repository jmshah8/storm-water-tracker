# Storm Water Tracker

Storm Water Tracker is a personal, non-commercial website that records every storm-overflow discharge published by England's water companies through the National Storm Overflow Hub, joins each discharge to Environment Agency rainfall, and flags the discharges that started on a "dry day" under the Environment Agency's own definition — with the evidence shown for every flag. GitHub Actions does all the collecting, classifying and building; the static site is hosted as a private Netlify project.

To run locally: create a virtualenv with Python 3.12 (`python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`), then run the scripts under `scripts/` (each has `--help`) and the tests with `pytest -q`. The rules for building this project are in [`CLAUDE.md`](CLAUDE.md); the specification and build plans are in [`build-pack/`](build-pack/).

## Phase status

| Phase | What it delivers | Status |
|---|---|---|
| 1 | The site: collector, rainfall, dry-day classifier, static site, private Netlify deploy | **done (2026-09-20)** |
| 2 | Met Office radar as a second opinion, back-filled to November 2024 | archive complete; acceptance (GATE 2.7) outstanding |
| 3 | Thames Water's own history back to 1 April 2022, run through the same classifier | steps 3.1–3.4 done; back-test page next |
