# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Plain-text 'where are we at' status: latest pass/fail + drift flag per scenario for
one or all declared pipeline stages. Reuses generate_test_report.load_run_rows() (the
existing 'latest fresh row per scenario' rule) and baseline_monitor.check_run() (the
existing drift comparison) — no new query logic. Reused in three places: standalone
CLI, the Claude Code SessionStart hook, and a CI stage-5 console-log step (deliberately
not $GITHUB_STEP_SUMMARY — see docs/superpowers/specs/2026-07-28-local-llm-diagnosis-
design.md for why that's unreliable).

Run: python -m tools.fleet_status [--stage sim|hil|real]
"""
import argparse
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from tools.baseline_monitor import check_run  # noqa: E402
from tools.generate_test_report import load_run_rows, resolve_runner_and_scenarios  # noqa: E402
from tools.pipeline_matrix import list_stages, load_stage  # noqa: E402
from tools.telemetry_logger import DB_PATH  # noqa: E402


def build_status_summary(runner_type, scenarios, db_path=DB_PATH, config_path=None):
    """Plain-text status: one line per scenario (pass/fail + drift flag), using the
    same 'latest fresh row' rule as generate_test_report.load_run_rows()."""
    rows = load_run_rows(runner_type, scenarios, db_path=db_path)
    rows_by_scenario = {row["scenario"]: row for row in rows}

    lines = [f"Fleet status — {runner_type}"]
    any_flagged = False
    for scenario in scenarios:
        row = rows_by_scenario.get(scenario)
        if row is None:
            lines.append(f"  {scenario}: no recent run")
            continue
        flagged = [r for r in check_run(row["id"], db_path=db_path, config_path=config_path)
                   if r.flagged]
        if flagged:
            any_flagged = True
            detail = ", ".join(
                f"{r.metric} {r.sigma:.1f}σ {'below' if r.direction == 'down' else 'above'} baseline"
                for r in flagged
            )
            lines.append(f"  ⚠ {scenario}: {row['result']} — DRIFT: {detail}")
        else:
            lines.append(f"  {scenario}: {row['result']} — ok")

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
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    if args.stage is None and args.runner_type is None:
        for stage in list_stages():
            runner_type, scenarios = load_stage(stage)
            print(build_status_summary(runner_type, scenarios, db_path=args.db,
                                        config_path=args.config))
        return

    runner_type, scenarios = resolve_runner_and_scenarios(
        args.stage, args.runner_type, args.scenarios)
    print(build_status_summary(runner_type, scenarios, db_path=args.db,
                                config_path=args.config))


if __name__ == "__main__":
    main()
