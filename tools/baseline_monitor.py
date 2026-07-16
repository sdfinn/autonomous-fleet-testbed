"""
Drift detection against historical baselines.

Compares a run's key metrics against a rolling window of past PASS runs and
flags any metric that deviates more than SIGMA_THRESHOLD standard deviations
from the historical mean.

Usage:
    python src/baseline_monitor.py              # checks latest run
    python src/baseline_monitor.py --run-id 42  # checks a specific run
"""
import argparse
import math
import os
import sqlite3
from dataclasses import dataclass

DB_PATH = os.environ.get("FLEET_DB", "reports/fleet_runs.db")
BASELINE_N = 20        # rolling window of PASS runs used as baseline
SIGMA_THRESHOLD = 2.0  # standard deviations before flagging

METRICS = {
    "nav_success_rate":        "down",
    "mean_position_error":     "up",
    "mean_time_to_goal":       "up",
    "collision_rate":          "up",
    "odom_hz_mean":            "down",
    "lidar_hz_mean":           "down",
    "camera_hz_mean":          "down",
}
WATCHED_METRICS = list(METRICS.keys())
HARD_THRESHOLD_METRICS = {"firmware_test_pass_rate"}


@dataclass
class BaselineReport:
    metric: str
    mean: float
    stddev: float
    current: float
    sigma: float
    flagged: bool


def _stddev(values: list) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def _available_columns(conn: sqlite3.Connection) -> set:
    rows = conn.execute("PRAGMA table_info(runs)").fetchall()
    return {row[1] for row in rows}


def check_run(
    run_id: int,
    db_path: str = DB_PATH,
    n: int = BASELINE_N,
    sigma_threshold: float = SIGMA_THRESHOLD,
) -> list:
    """Compare a run against historical PASS baselines.

    Returns a list of BaselineReport, one per metric with enough history.
    Reports with flagged=True exceed sigma_threshold standard deviations.
    Skips metrics absent from the schema or with fewer than 3 baseline samples.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    available = _available_columns(conn)
    metrics = [m for m in WATCHED_METRICS if m in available]
    if not metrics:
        conn.close()
        return []

    # Compare like with like (Session 16, review finding I4): the baseline window must
    # only contain runs from the SAME execution context as the run under check —
    # otherwise a 15W hil_jetson row would drift-compare against 25W sim history (or
    # vice versa) and every metric would flag on the platform delta, not on real drift.
    # Slice on (runner_type, power_mode). power_mode is NULL on all pre-Session-16 sim
    # rows, so a NULL-power run must baseline against NULL-power history: use `IS ?`
    # (NULL-safe equality in SQLite) rather than `= ?` (which never matches NULL).
    slice_cols = [c for c in ("runner_type", "power_mode") if c in available]

    col_list = ", ".join(metrics)
    select_list = ", ".join(metrics + slice_cols)
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
    params.append(n)
    baseline_rows = conn.execute(
        f"SELECT {col_list} FROM runs "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY id DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()

    reports = []
    for metric in metrics:
        current_val = current_row[metric]
        if current_val is None:
            continue
        history = [r[metric] for r in baseline_rows if r[metric] is not None]
        if len(history) < 3:
            continue
        mean = sum(history) / len(history)
        sd = _stddev(history)
        if sd == 0.0:
            # Baseline has no variance — cannot establish a meaningful threshold
            continue
        deviation = abs(current_val - mean) / sd
        reports.append(
            BaselineReport(
                metric=metric,
                mean=mean,
                stddev=sd,
                current=current_val,
                sigma=deviation,
                flagged=deviation > sigma_threshold,
            )
        )
    return reports


def check_latest_run(
    db_path: str = DB_PATH,
    n: int = BASELINE_N,
    sigma_threshold: float = SIGMA_THRESHOLD,
):
    """Check the most recently logged run. Returns None if DB is empty."""
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row is None:
        return None
    return check_run(row[0], db_path=db_path, n=n, sigma_threshold=sigma_threshold)


def _print_report(reports: list, run_id: int) -> None:
    print(f"\nBaseline drift report — run {run_id}")
    print("-" * 56)
    if not reports:
        print("  No metrics available for comparison.")
        return
    for r in reports:
        status = "FLAGGED" if r.flagged else "OK     "
        print(
            f"  {status}  {r.metric:<28} "
            f"current={r.current:.2f}  mean={r.mean:.2f}  "
            f"sd={r.stddev:.2f}  sigma={r.sigma:.1f}"
        )
    print("-" * 56)
    flagged = [r for r in reports if r.flagged]
    if flagged:
        print(f"  {len(flagged)} metric(s) flagged — investigate before release.")
    else:
        print("  All metrics within baseline. No drift detected.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check run against historical baseline")
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    if args.run_id is not None:
        reports = check_run(args.run_id, db_path=args.db)
        _print_report(reports, args.run_id)
    else:
        conn = sqlite3.connect(args.db)
        row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        if row is None:
            print("Database is empty — no runs to check.")
            return
        reports = check_latest_run(db_path=args.db)
        _print_report(reports, row[0])


if __name__ == "__main__":
    main()
