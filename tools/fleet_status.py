# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Plain-text 'where are we at' status: latest pass/fail + drift flag per scenario for
one or all declared pipeline stages. Reuses generate_test_report.load_run_rows() (the
existing 'latest fresh row per scenario' rule) and baseline_monitor.check_run() (the
existing drift comparison) — no new query logic. Reused in three places: standalone
CLI, the Claude Code SessionStart hook, and a CI stage-5 console-log step (deliberately
not $GITHUB_STEP_SUMMARY — see docs/superpowers/specs/2026-07-28-local-llm-diagnosis-
design.md for why that's unreliable).

Run: python -m tools.fleet_status [--stage sim|hil|real] [--max-age-minutes N]
"""
import argparse
import os
import sys
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from tools.baseline_monitor import check_run  # noqa: E402
from tools.generate_test_report import load_run_rows, resolve_runner_and_scenarios  # noqa: E402
from tools.pipeline_matrix import list_stages, load_stage  # noqa: E402
from tools.telemetry_logger import DB_PATH  # noqa: E402

# "What's the fleet's last known state" (CLI / SessionStart hook) is a different
# question from generate_test_report's "this CI run's own result" (its own 30-minute
# MAX_ROW_AGE_MINUTES default) — default to a much wider window here. CI callers pass
# --max-age-minutes 30 explicitly to get that tighter, CI-correct behavior back.
DEFAULT_STATUS_MAX_AGE_MINUTES = 60 * 24 * 30  # ~30 days


def _row_age_str(timestamp_str):
    """Human-readable age of a run row's timestamp, e.g. '2h ago', '3d ago'."""
    row_dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S")
    minutes = (datetime.now() - row_dt).total_seconds() / 60
    if minutes < 60:
        return f"{int(minutes)}m ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    return f"{int(hours / 24)}d ago"


def build_status_summary(runner_type, scenarios, db_path=DB_PATH, config_path=None,
                          max_age_minutes=DEFAULT_STATUS_MAX_AGE_MINUTES):
    """Plain-text status: one line per scenario (pass/fail + drift flag + age), using
    the same 'latest fresh row' rule as generate_test_report.load_run_rows() — but
    with a much wider default freshness window than that function's own 30-minute
    default, since 'what's the fleet's last known state' (this tool's job) is a
    different question from 'this CI run's own result' (that function's original job)."""
    rows = load_run_rows(runner_type, scenarios, db_path=db_path,
                          max_age_minutes=max_age_minutes)
    rows_by_scenario = {row["scenario"]: row for row in rows}

    lines = [f"Fleet status — {runner_type}"]
    any_flagged = False
    for scenario in scenarios:
        row = rows_by_scenario.get(scenario)
        if row is None:
            lines.append(f"  {scenario}: no recent run")
            continue
        age = _row_age_str(row["timestamp"])
        flagged = [r for r in check_run(row["id"], db_path=db_path, config_path=config_path)
                   if r.flagged]
        if flagged:
            any_flagged = True
            detail = ", ".join(
                f"{r.metric} {r.sigma:.1f}σ {'below' if r.direction == 'down' else 'above'} baseline"
                for r in flagged
            )
            lines.append(f"  ⚠ {scenario}: {row['result']} — DRIFT: {detail} ({age})")
        else:
            lines.append(f"  {scenario}: {row['result']} — ok ({age})")

    if any_flagged:
        lines.append(
            "  Drift flagged — run `python -m tools.agentic_validate` (compare local "
            "vs Claude) or `python -m tools.agentic_loop` (propose a fix) to diagnose."
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Print a plain-text fleet status summary (pass/fail + drift per scenario)"
    )
    parser.add_argument("--stage", choices=["sim", "hil", "real"], default=None,
                         help="one declared stage (config/pipeline_matrix.yaml); "
                              "omit to print all declared stages")
    parser.add_argument("--runner-type", default=None)
    parser.add_argument("--scenario", action="append", default=None, dest="scenarios",
                         help="repeatable — used with --runner-type for ad hoc queries")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--config", default=None,
                         help="override drift_config.yaml path (does not affect "
                              "pipeline_matrix.yaml resolution)")
    parser.add_argument("--max-age-minutes", type=int, default=DEFAULT_STATUS_MAX_AGE_MINUTES,
                         help="how old a row can be and still count as 'the latest' "
                              "(default: ~30 days, 'last known state'; CI passes 30 "
                              "here to mean 'this run's own result')")
    args = parser.parse_args()

    try:
        if args.stage is None and args.runner_type is None:
            for stage in list_stages():
                runner_type, scenarios = load_stage(stage)
                print(build_status_summary(runner_type, scenarios, db_path=args.db,
                                            config_path=args.config,
                                            max_age_minutes=args.max_age_minutes))
            return

        runner_type, scenarios = resolve_runner_and_scenarios(
            args.stage, args.runner_type, args.scenarios)
        print(build_status_summary(runner_type, scenarios, db_path=args.db,
                                    config_path=args.config,
                                    max_age_minutes=args.max_age_minutes))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
