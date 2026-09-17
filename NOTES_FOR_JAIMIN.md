# Notes for Jaimin

- 2026-09-16: Netlify credits remaining at start: 285 of 300 (2026-09-16). Jaimin reports the 30-day billing cycle has just started, so 15 credits were already used this cycle before any Storm Water Tracker deploy.
- 2026-09-16: Scaffold created.
- 2026-09-16: `python3` on this Mac is pyenv's 3.11.7; Python 3.12.14 was installed with Homebrew and the `.venv` is built with `python3.12`. Added `.venv/` to `.gitignore` (not in the step 1.1 list) so the virtualenv the plan creates in the repo root is never committed.
- 2026-09-16: Another Netlify site on the same team (`anticipationdesk`) is connected to Git, so its pushes trigger 15-credit production deploys that come out of the same 300-credit monthly pool.
- 2026-09-16: Step 1.2 — all ten feeds resolved (total 14,200 overflows). Southern's and Wessex's `licenseInfo` is a longer sentence ("… © 2026 by Southern Water is licensed under CC BY 4.0", "… © 2024 by Wessex Water is licensed under CC BY 4.0") rather than "Licensed under CC BY 4.0"; still CC BY 4.0. ST Connect: empty `licenseInfo`, 1 record (placeholder feed), as the spec expected.
