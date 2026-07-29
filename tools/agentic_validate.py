# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Manual comparison harness: run the same synthetic drift scenario through both the
Claude and Ollama diagnose() backends and print both proposals side by side, for a
human to judge whether the local model is good enough to cut over. Dev-only tool, not
wired into CI — matches R1's decoupled-canary pattern (see the Jetson GPU inference
canary in Release1Todo.md). Design:
docs/superpowers/specs/2026-07-28-local-llm-diagnosis-design.md.

Run: python -m tools.agentic_validate
"""
import tempfile

from tools.agentic_loop import diagnose
from tools.telemetry_logger import init_db, log_run

# Each case seeds a real, small-variance PASS baseline (never identical values — see
# root CLAUDE.md's zero-variance baseline test trap) plus one flagged run. Case 1
# recreates the one real incident already on record: diagnose() once hallucinated
# inflation_radius=0.55 when the real value is 0.25 — the local model must not repeat
# that mistake either.
CASES = [
    {
        "name": "collision_rate_spike (inflation_radius regression check)",
        "baseline_collision_rate": [0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02],
        "flagged_collision_rate": 0.25,
    },
    {
        "name": "nav_success_rate_drop",
        "baseline_nav_success_rate": [0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94],
        "flagged_nav_success_rate": 0.55,
    },
]


def _seed_case(db_path, case):
    for key, values in case.items():
        if not key.startswith("baseline_"):
            continue
        metric = key[len("baseline_"):]
        for v in values:
            log_run(scenario="agentic_validate", steps=100, final_x=1.0, final_y=1.0,
                    result="PASS", step_log=[], db_path=db_path, runner_type="local",
                    **{metric: v})
    flagged_metrics = {
        key[len("flagged_"):]: v for key, v in case.items() if key.startswith("flagged_")
    }
    return log_run(scenario="agentic_validate", steps=100, final_x=1.0, final_y=1.0,
                    result="FAIL", step_log=[], db_path=db_path, runner_type="local",
                    **flagged_metrics)


def _summarize(response):
    lines = []
    for block in response.content:
        if block.type == "text":
            lines.append(f"  [analysis] {block.text}")
        elif block.type == "tool_use":
            lines.append(f"  [proposal] {block.name}({block.input})")
    return "\n".join(lines) or "  (no output)"


def main():
    for case in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = f"{tmp}/validate.db"
            init_db(db_path)
            run_id = _seed_case(db_path, case)
            run_data = {"id": run_id, "scenario": "agentic_validate", "result": "FAIL",
                        "sim_engine": "gazebo"}

            print(f"\n{'=' * 70}\nCase: {case['name']}\n{'=' * 70}")

            print("\n[claude]")
            try:
                print(_summarize(diagnose(run_data, db_path=db_path, backend="claude")))
            except Exception as exc:
                print(f"  ERROR: {exc}")

            print("\n[ollama]")
            try:
                print(_summarize(diagnose(run_data, db_path=db_path, backend="ollama")))
            except Exception as exc:
                print(f"  ERROR: {exc}")


if __name__ == "__main__":
    main()
