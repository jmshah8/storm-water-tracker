"""Tests for scripts/deploy_guard.py (01_SPEC.md §9.2 budget rules)."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import deploy_guard as g  # noqa: E402

NOW = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


def entries(kind, utcs):
    return [{"utc": u, "kind": kind, "run_url": "r", "message": "m", "deploy_url": "d"} for u in utcs]


def test_month_boundary():
    log = entries("prod", [f"2026-09-{d:02d}T08:00:00Z" for d in range(1, 11)])  # 10 in September
    log += entries("prod", ["2026-10-01T07:59:59Z"])
    assert g.prod_this_month(log, NOW) == 1
    assert g.check(log, "prod", False, NOW)[0] is True


def test_seven_allowed_eight_refused():
    seven = entries("prod", [f"2026-10-01T0{h}:00:00Z" for h in range(7)])
    assert g.check(seven, "prod", False, NOW)[0] is True
    eight = seven + entries("prod", ["2026-10-01T07:30:00Z"])
    allowed, message = g.check(eight, "prod", False, NOW)
    assert allowed is False and "refused" in message


def test_override_true_allows_ninth():
    eight = entries("prod", [f"2026-10-01T0{h}:00:00Z" for h in range(8)])
    assert g.check(eight, "prod", True, NOW)[0] is True


def test_alias_never_counts_or_refuses():
    log = entries("prod", [f"2026-10-01T0{h}:00:00Z" for h in range(8)]) + entries("alias", ["2026-10-01T07:00:00Z"] * 20)
    assert g.prod_this_month(log, NOW) == 8
    assert g.check(log, "alias", False, NOW)[0] is True


def test_record_appends_and_sorts(tmp_path):
    log_path = tmp_path / "deploy_log.json"
    log_path.write_text(json.dumps(entries("prod", ["2099-01-01T00:00:00Z"])))
    cli = tmp_path / "deploy.json"
    cli.write_text(json.dumps({"site_id": "x", "deploy_id": "y", "deploy_url": "https://daily--site.netlify.app"}))
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "deploy_guard.py"), "--record", str(cli),
                             "--kind", "alias", "--run-url", "https://github.com/run/1", "--message", "swt alias",
                             "--log", str(log_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    log = json.loads(log_path.read_text())
    assert [e["kind"] for e in log] == ["alias", "prod"]  # sorted by utc: the new entry is now, before 2099
    assert set(log[0]) == {"utc", "kind", "run_url", "message", "deploy_url"}
    assert log[0]["deploy_url"] == "https://daily--site.netlify.app"
    assert log[0]["run_url"] == "https://github.com/run/1" and log[0]["message"] == "swt alias"


def test_cli_refuses_ninth_prod(tmp_path):
    log_path = tmp_path / "deploy_log.json"
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    log_path.write_text(json.dumps(entries("prod", [f"{month}-01T00:00:0{i}Z" for i in range(8)])))
    base = [sys.executable, str(ROOT / "scripts" / "deploy_guard.py"), "--kind", "prod", "--log", str(log_path)]
    assert subprocess.run(base + ["--override", "false"], capture_output=True).returncode == 1
    assert subprocess.run(base + ["--override", "true"], capture_output=True).returncode == 0
