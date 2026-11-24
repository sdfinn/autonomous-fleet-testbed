"""Compare sim and real fleet runs from the single fleet telemetry database.

Sim and real runs live in the SAME `runs` table (Session 12's design: one SQLite
store, `sim_engine` column distinguishes gazebo | isaac | real) — this filters
ONE database by `sim_engine` into two comparable subsets, rather than expecting
two separate database files. The original two-DB design (`FLEET_SIM_DB`/
`FLEET_REAL_DB`) never matched how `telemetry_logger.log_run()` actually writes,
and its unfiltered query would have silently compared identical rows against
themselves even if pointed at one file by hand. Fixed 2026-07-27 (Session 18
prep) — see Release1Todo.md Session 18 for the history.
"""

import argparse
import sqlite3

import pandas as pd

from tools.telemetry_logger import DB_PATH

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


def load_run_metrics(db_path: str, sim_engine: str) -> pd.DataFrame:
    """Load rows for one `sim_engine` value (gazebo | isaac | real) from `db_path`."""
    available = _get_available_columns(db_path)
    selected = ["scenario"] + [m for m in METRIC_KEYS if m in available]

    if len(selected) <= 1:
        raise ValueError(f"No supported fleet metrics found in {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        query = f"SELECT {', '.join(selected)} FROM runs WHERE sim_engine = ?"
        return pd.read_sql(query, conn, params=(sim_engine,))
    finally:
        conn.close()


def compare_metrics(db_path: str, sim_engine: str = "gazebo", real_engine: str = "real") -> dict:
    sim = load_run_metrics(db_path, sim_engine)
    real = load_run_metrics(db_path, real_engine)

    results = {
        "db": db_path,
        "sim_engine": sim_engine,
        "real_engine": real_engine,
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


def success_by_scenario(db_path: str, sim_runner: str = "local",
                        real_runner: str = "real_robot") -> list:
    """Pass rate of each scenario in the simulator and on the real robot, for the
    scenarios BOTH have run. Rows are chosen by `runner_type` (where the run happened),
    not by `sim_engine`: Jetson-in-CI rows also carry sim_engine 'real'.

    Added 2026-11-23: the real robot grades itself and records only PASS or FAIL per
    mission part, so the pass rate per part is what can honestly be compared today.
    Returns [(scenario, sim_runs, sim_pass_rate, real_runs, real_pass_rate), ...]."""
    conn = sqlite3.connect(db_path)
    try:
        def rates(runner):
            return {scenario: (runs, passed / runs) for scenario, runs, passed in conn.execute(
                "SELECT scenario, COUNT(*), SUM(result = 'PASS') FROM runs "
                "WHERE runner_type = ? GROUP BY scenario", (runner,))}
        sim, real = rates(sim_runner), rates(real_runner)
    finally:
        conn.close()
    return [(name, sim[name][0], sim[name][1], real[name][0], real[name][1])
            for name in sorted(set(sim) & set(real))]


def print_success_by_scenario(rows: list) -> None:
    print("\nPass rate by scenario (simulator vs real robot)")
    print("-----------------------------------------------")
    if not rows:
        print("No scenario has been run both in the simulator and on the real robot.")
        print("(Real-robot rows live on the Jetson: python -m tools.pull_robot_runs)")
        return
    print(f"{'scenario':<22}{'sim runs':>9}{'sim pass':>10}"
          f"{'real runs':>11}{'real pass':>11}{'delta':>8}")
    for name, sim_n, sim_rate, real_n, real_rate in rows:
        print(f"{name:<22}{sim_n:>9}{sim_rate:>10.0%}{real_n:>11}{real_rate:>11.0%}"
              f"{real_rate - sim_rate:>+8.0%}")


def print_comparison(results: dict) -> None:
    print("Sim vs Real Comparison")
    print("-----------------------")
    print(f"DB:          {results['db']}")
    print(f"sim_engine:  {results['sim_engine']}")
    print(f"real_engine: {results['real_engine']}")
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
    parser = argparse.ArgumentParser(description="Compare sim and real fleet run metrics.")
    parser.add_argument(
        "--db",
        default=DB_PATH,
        help="Path to the fleet telemetry SQLite database (default: FLEET_DB / "
             "tools.telemetry_logger.DB_PATH — the single DB every tool reads/writes).",
    )
    parser.add_argument(
        "--sim-engine",
        default="gazebo",
        help="sim_engine value to treat as the 'sim' side (default: gazebo).",
    )
    parser.add_argument(
        "--real-engine",
        default="real",
        help="sim_engine value to treat as the 'real' side (default: real).",
    )
    args = parser.parse_args()

    results = compare_metrics(args.db, args.sim_engine, args.real_engine)
    print_comparison(results)
    print_success_by_scenario(success_by_scenario(args.db))


if __name__ == "__main__":
    main()
