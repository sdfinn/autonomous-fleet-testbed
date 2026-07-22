# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""
Drift detection against historical baselines.

Compares a run's key metrics against a rolling window of past PASS runs from the SAME
(runner_type, power_mode) slice and flags any metric that deviates in its configured
WORSE direction beyond the configured sigma bands.

All thresholds, watched metrics, and directions live in config/drift_config.yaml —
never here (CR-01/CR-02, Session 17 code review: this module previously hardcoded its
own scheme and ignored direction, so a 2-sigma IMPROVEMENT flagged as drift).

Usage:
    python -m tools.baseline_monitor              # checks latest run
    python -m tools.baseline_monitor --run-id 42  # checks a specific run
"""
import argparse
import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from tools.telemetry_logger import DB_PATH
# Canonical config: repo-root config/drift_config.yaml (overridable for tests/tools).
DEFAULT_CONFIG_PATH = str(Path(__file__).resolve().parent.parent / "config" / "drift_config.yaml")

# Severity bands ordered worst-last; report.severity is the highest band reached.
_SEVERITY_ORDER = ("info", "warning", "error", "critical")
_MIN_BASELINE_SAMPLES = 3


def load_config(path=None):
    """Load drift configuration (history window, sigma bands, watched metrics).

    Path resolution: explicit arg > DRIFT_CONFIG env var > repo config/drift_config.yaml.
    Raises on a missing/invalid file — a broken drift config must be loud, not a silent
    fall-through to defaults (the Session 11 params-file lesson).
    """
    path = path or os.environ.get("DRIFT_CONFIG", DEFAULT_CONFIG_PATH)
    with open(path) as f:
        cfg = yaml.safe_load(f)
    for key in ("history_window", "sigma", "metrics"):
        if key not in cfg:
            raise ValueError(f"drift config {path} missing key {key!r}")
    for name, spec in cfg["metrics"].items():
        if spec.get("direction") not in ("up", "down"):
            raise ValueError(f"drift config metric {name!r}: direction must be up|down")
    return cfg


@dataclass
class BaselineReport:
    metric: str
    mean: float
    stddev: float
    current: float
    sigma: float
    flagged: bool
    direction: str = "up"      # which way is worse, from config
    severity: str = None       # None (fine/improvement) or info|warning|error|critical


def _stddev(values: list) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def _severity(sigma_value: float, bands: dict) -> str:
    """Highest configured band this worse-direction deviation reaches, or None."""
    reached = None
    for band in _SEVERITY_ORDER:
        if band in bands and sigma_value >= bands[band]:
            reached = band
    return reached


def _available_columns(conn: sqlite3.Connection) -> set:
    rows = conn.execute("PRAGMA table_info(runs)").fetchall()
    return {row[1] for row in rows}


def check_run(
    run_id: int,
    db_path: str = DB_PATH,
    n: int = None,
    config_path: str = None,
) -> list:
    """Compare a run against historical PASS baselines (config-driven).

    Returns a list of BaselineReport, one per configured metric with enough history.
    flagged=True means the deviation is in the metric's WORSE direction and reaches the
    config's `info` sigma band; `severity` names the highest band reached. Deviations in
    the good direction (improvements) never flag. Skips metrics absent from the schema
    or with fewer than 3 baseline samples.
    """
    cfg = load_config(config_path)
    window = n if n is not None else cfg["history_window"]
    bands = cfg["sigma"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    available = _available_columns(conn)
    metrics = {m: spec for m, spec in cfg["metrics"].items() if m in available}
    if not metrics:
        conn.close()
        return []

    # Compare like with like (Session 16 finding I4, extended Session 17 Piece 4): the
    # baseline window must only contain runs from the SAME execution context AND the
    # SAME mission scenario as the run under check — otherwise a mission2_red row
    # (which stops after one step) would drift-compare against mission2_no_ball history
    # (a full round trip), or a 15W hil_jetson row against 25W sim history, and every
    # metric would flag on the context/scenario delta, not on real drift. Slice on
    # (runner_type, power_mode, scenario). power_mode is NULL on all pre-Session-16 sim
    # rows, so a NULL-power run must baseline against NULL-power history: use `IS ?`
    # (NULL-safe equality in SQLite) rather than `= ?` (which never matches NULL).
    slice_cols = [c for c in ("runner_type", "power_mode", "scenario") if c in available]

    metric_names = list(metrics)
    col_list = ", ".join(metric_names)
    select_list = ", ".join(metric_names + slice_cols)
    current_row = conn.execute(
        f"SELECT {select_list} FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    if current_row is None:
        conn.close()
        raise ValueError(f"Run {run_id} not found in {db_path}")

    where = ["result = 'PASS'", "id != ?"]
    params = [run_id]
    for col in slice_cols:
        where.append(f"{col} IS ?")
        params.append(current_row[col])
    params.append(window)
    baseline_rows = conn.execute(
        f"SELECT {col_list} FROM runs "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY id DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()

    reports = []
    for metric, spec in metrics.items():
        current_val = current_row[metric]
        if current_val is None:
            continue
        history = [r[metric] for r in baseline_rows if r[metric] is not None]
        if len(history) < _MIN_BASELINE_SAMPLES:
            continue
        mean = sum(history) / len(history)
        sd = _stddev(history)
        if sd == 0.0:
            # Baseline has no variance — cannot establish a meaningful threshold
            continue
        deviation = abs(current_val - mean) / sd
        # Direction-aware (CR-01): only a deviation toward WORSE can flag. 'down'
        # means lower is worse; 'up' means higher is worse. Improvements report
        # sigma for visibility but carry severity=None and flagged=False.
        worse = (current_val < mean) if spec["direction"] == "down" else (current_val > mean)
        severity = _severity(deviation, bands) if worse else None
        reports.append(
            BaselineReport(
                metric=metric,
                mean=mean,
                stddev=sd,
                current=current_val,
                sigma=deviation,
                flagged=severity is not None,
                direction=spec["direction"],
                severity=severity,
            )
        )
    return reports


def check_latest_run(db_path: str = DB_PATH, n: int = None, config_path: str = None):
    """Check the most recently logged run. Returns None if DB is empty."""
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row is None:
        return None
    return check_run(row[0], db_path=db_path, n=n, config_path=config_path)


def _print_report(reports: list, run_id: int) -> None:
    print(f"\nBaseline drift report — run {run_id}")
    print("-" * 64)
    if not reports:
        print("  No metrics available for comparison.")
        return
    for r in reports:
        status = (r.severity or "ok").upper() if r.flagged else "OK"
        print(
            f"  {status:<8}  {r.metric:<28} "
            f"current={r.current:.2f}  mean={r.mean:.2f}  "
            f"sd={r.stddev:.2f}  sigma={r.sigma:.1f}"
        )
    print("-" * 64)
    flagged = [r for r in reports if r.flagged]
    if flagged:
        worst = max(flagged, key=lambda r: r.sigma)
        print(f"  {len(flagged)} metric(s) flagged (worst: {worst.metric} "
              f"{worst.severity}) — investigate before release.")
    else:
        print("  All metrics within baseline. No drift detected.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check run against historical baseline")
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--config", default=None, help="drift config YAML "
                        "(default: DRIFT_CONFIG env or config/drift_config.yaml)")
    args = parser.parse_args()

    if args.run_id is not None:
        reports = check_run(args.run_id, db_path=args.db, config_path=args.config)
        _print_report(reports, args.run_id)
    else:
        conn = sqlite3.connect(args.db)
        row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        if row is None:
            print("Database is empty — no runs to check.")
            return
        reports = check_latest_run(db_path=args.db, config_path=args.config)
        _print_report(reports, row[0])


if __name__ == "__main__":
    main()
