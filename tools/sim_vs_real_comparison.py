"""Compare sim and real fleet runs using the new fleet schema.

This tool accepts two SQLite databases, one for simulation runs and one for
real-world runs, and computes metric deltas and optional scenario-level
correlation where scenario names align.
"""

import os
import sqlite3
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_SIM_DB = os.environ.get(
    "FLEET_SIM_DB",
    str(_PROJECT_ROOT.parent / "reports" / "fleet_runs.db"),
)
DEFAULT_REAL_DB = os.environ.get(
    "FLEET_REAL_DB",
    str(_PROJECT_ROOT.parent / "reports" / "fleet_real_runs.db"),
)

METRIC_KEYS = [
    "nav_success_rate",
    "mean_position_error",
    "mean_time_to_goal",
    "collision_rate",
    "odom_hz_mean",
    "lidar_hz_mean",
    "camera_hz_mean",
]


def _get_available_columns(db_path: str) -> set:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(runs)").fetchall()
        return {row[1] for row in rows}
    finally:
        conn.close()


def load_run_metrics(db_path: str) -> pd.DataFrame:
    available = _get_available_columns(db_path)
    selected = ["scenario"] + [m for m in METRIC_KEYS if m in available]

    if len(selected) <= 1:
        raise ValueError(f"No supported fleet metrics found in {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        query = f"SELECT {', '.join(selected)} FROM runs"
        return pd.read_sql(query, conn)
    finally:
        conn.close()


def compare_metrics(sim_db: str, real_db: str) -> dict:
    sim = load_run_metrics(sim_db)
    real = load_run_metrics(real_db)

    results = {
        "sim_db": sim_db,
        "real_db": real_db,
        "metrics": {},
        "scenario_matches": 0,
    }

    common_metrics = [m for m in METRIC_KEYS if m in sim.columns and m in real.columns]
    matched = pd.merge(sim, real, on="scenario", suffixes=("_sim", "_real"))
    results["scenario_matches"] = len(matched)

    for metric in common_metrics:
        sim_series = sim[metric].dropna()
        real_series = real[metric].dropna()
        sim_mean = float(sim_series.mean()) if len(sim_series) else float("nan")
        real_mean = float(real_series.mean()) if len(real_series) else float("nan")
        delta = real_mean - sim_mean
        percent_delta = float("nan")
        if pd.notna(sim_mean) and sim_mean != 0.0:
            percent_delta = 100.0 * delta / sim_mean

        entry = {
            "sim_mean": sim_mean,
            "real_mean": real_mean,
            "delta": delta,
            "percent_delta": percent_delta,
            "sim_count": int(len(sim_series)),
            "real_count": int(len(real_series)),
        }

        if metric in matched.columns:
            sim_match = matched[f"{metric}_sim"].dropna()
            real_match = matched[f"{metric}_real"].dropna()
            if len(sim_match) > 1 and len(real_match) > 1:
                entry["scenario_correlation"] = float(sim_match.corr(real_match))
            else:
                entry["scenario_correlation"] = None
        else:
            entry["scenario_correlation"] = None

        results["metrics"][metric] = entry

    return results


def print_comparison(results: dict) -> None:
    print("Sim vs Real Comparison")
    print("-----------------------")
    print(f"Sim DB:  {results['sim_db']}")
    print(f"Real DB: {results['real_db']}")
    print(f"Scenario matches: {results['scenario_matches']}\n")

    for metric, entry in results["metrics"].items():
        print(f"Metric: {metric}")
        print(f"  sim_mean:  {entry['sim_mean']:.4g}")
        print(f"  real_mean: {entry['real_mean']:.4g}")
        print(f"  delta:     {entry['delta']:.4g}")
        if pd.notna(entry["percent_delta"]):
            print(f"  pct_delta: {entry['percent_delta']:.2f}%")
        if entry["scenario_correlation"] is not None:
            print(f"  scenario correlation: {entry['scenario_correlation']:.3f}")
        print()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compare sim and real fleet run metrics.")
    parser.add_argument(
        "--sim-db",
        default=DEFAULT_SIM_DB,
        help="Path to the simulation runs SQLite database.",
    )
    parser.add_argument(
        "--real-db",
        default=DEFAULT_REAL_DB,
        help="Path to the real runs SQLite database.",
    )
    args = parser.parse_args()

    results = compare_metrics(args.sim_db, args.real_db)
    print_comparison(results)


if __name__ == "__main__":
    main()
