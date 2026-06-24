import json
import os
import sqlite3

DB_PATH = os.environ.get("FLEET_DB", "reports/fleet_runs.db")

class ScenarioAnalyzer:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    def score_run(self, run: dict) -> float:
        """Score a run's learning value (0.0–1.0). Higher = more interesting."""
        score = 0.0

        # Complex runs with many steps are more likely to expose fleet-level edge cases.
        if run.get("steps", 0) > 400:
            score += 0.2

        # Failures that got close to the goal suggest coordination / coverage edge cases.
        if run.get("result") == "FAIL" and run.get("final_x", 0) > 1.0:
            score += 0.25

        bat_diff = (run.get("battery_percent_start") or 100) - \
                   (run.get("battery_percent_end") or 100)
        if bat_diff > 5:
            score += 0.15

        if (run.get("num_obstacles_detected") or 0) > 0:
            score += 0.1

        if run.get("camera_hz_mean") is not None and run.get("camera_hz_mean") < 15:
            score += 0.05

        if run.get("firmware_test_pass_rate") is not None and run["firmware_test_pass_rate"] < 0.9:
            score += 0.1

        coverage_pct = run.get("fleet_coverage_pct")
        if coverage_pct is not None:
            score += min(0.2, max(0.0, (100.0 - coverage_pct) / 100.0 * 0.2))

        if (run.get("coordination_failures") or 0) > 0:
            score += 0.15

        if run.get("runner_type") or run.get("robot_type"):
            score += 0.05

        stage_timings = run.get("stage_timings_sec")
        if isinstance(stage_timings, str):
            try:
                timings = json.loads(stage_timings)
                if any(value > 40 for value in timings.values() if isinstance(value, (int, float))):
                    score += 0.05
            except json.JSONDecodeError:
                pass

        return min(score, 1.0)

    def tag_high_value_scenarios(self, threshold=0.5):
        """Score all AI scenarios via their associated run and update test_quality."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ai.id, r.steps, r.result, r.final_x,
                   r.battery_percent_start, r.battery_percent_end,
                   r.num_obstacles_detected,
                   r.runner_type, r.robot_type, r.camera_hz_mean,
                   r.firmware_test_pass_rate, r.fleet_coverage_pct,
                   r.coordination_failures, r.stage_timings_sec
            FROM ai_scenarios ai
            JOIN runs r ON ai.run_id = r.id
        """)
        rows = cursor.fetchall()
        tagged = 0
        for row in rows:
            score = self.score_run(dict(row))
            cursor.execute("UPDATE ai_scenarios SET test_quality = ? WHERE id = ?",
                           (score, row["id"]))
            if score >= threshold:
                tagged += 1
        conn.commit()
        conn.close()
        print(f"Tagged {tagged}/{len(rows)} scenarios as high-value (threshold={threshold})")
        return tagged

if __name__ == "__main__":
    ScenarioAnalyzer().tag_high_value_scenarios()