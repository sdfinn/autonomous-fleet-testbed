import json
import os
import sqlite3

from anthropic import Anthropic

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class AITestScenarioGenerator:
    def __init__(self, db_path=None):
        db_path = db_path or os.environ.get("FLEET_DB", "reports/fleet_runs.db")
        self.db_path = db_path
        self.client = Anthropic()
        self.model = "claude-sonnet-4-6"

    def query_recent_runs(self, limit=10):
        """Fetch recent run data from database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, scenario, steps, final_x, final_y, result,
                   nav_success_rate, mean_position_error, collision_rate,
                   odom_hz_mean, lidar_hz_mean, camera_hz_mean
            FROM runs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        runs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return runs

    def get_high_value_scenarios(self, limit=3) -> list:
        """Return top-scored AI scenarios to seed the next generation prompt."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT scenario_name, suggested_description, test_quality
            FROM ai_scenarios
            WHERE test_quality IS NOT NULL
            ORDER BY test_quality DESC LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def generate_scenarios(self, context_runs=None, num_scenarios=5):
        """Use Claude to generate edge case scenarios."""
        if context_runs is None:
            context_runs = self.query_recent_runs(limit=5)

        run_summary = json.dumps(context_runs[:3], indent=2)

        high_value = self.get_high_value_scenarios()
        seed_text = ""
        if high_value:
            seed_text = "\n\nHigh-value scenarios from previous runs (generate similar ones):\n"
            for s in high_value:
                seed_text += f"- {s['scenario_name']}: {s['suggested_description']}\n"

        prompt = f"""You are a QA engineer testing multi-robot fleet navigation in simulation.

The fleet operates under ROS2 Jazzy in Gazebo Harmonic. Robot topics and frames use the
/robot_001/ namespace, and scenarios should reflect a multi-robot fleet deployment.

Recent test run data:
{run_summary}

Based on this telemetry, generate {num_scenarios} edge case test scenarios for a multi-robot
fleet operating in Gazebo Harmonic with ROS2 Jazzy.
Each scenario should:
1. Have a unique, descriptive name
2. Include specific starting position (x, y)
3. Include obstacle configuration
4. Explain why this edge case is important

Respond as a JSON array with objects like:
{{
  "scenario_name": "...",
  "start_x": float,
  "start_y": float,
  "obstacle_count": int,
  "obstacle_positions": [[x1, y1], [x2, y2], ...],
  "reasoning": "Why this tests an important edge case"
}}{seed_text}
Generate {num_scenarios} creative, realistic scenarios:"""

        print(f"Calling Claude API with model {self.model}...")
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = response.content[0].text

        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]
            else:
                json_str = response_text

            scenarios = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Failed to parse Claude response: {e}")
            print(f"Raw response: {response_text}")
            return [], None

        return scenarios, response.usage

    def store_scenarios(self, scenarios, run_id, usage):
        """Store generated scenarios in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for scenario in scenarios:
            cursor.execute(
                """
                INSERT INTO ai_scenarios
                (run_id, scenario_name, suggested_description, ai_model,
                 prompt_tokens, response_tokens)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    scenario.get("scenario_name", "Unnamed"),
                    scenario.get("reasoning", "No description"),
                    self.model,
                    usage.input_tokens,
                    usage.output_tokens,
                ),
            )

        conn.commit()
        conn.close()
        print(f"Stored {len(scenarios)} scenarios in database.")

    def run_generation_pipeline(self, num_scenarios=5):
        """Full pipeline: query, generate, store."""
        print("Fetching recent run data...")
        context_runs = self.query_recent_runs(limit=5)

        if not context_runs:
            print("No runs found in database. Generating scenarios without context.")
            context_runs = []

        print(f"Generating {num_scenarios} scenarios...")
        scenarios, usage = self.generate_scenarios(context_runs, num_scenarios)

        if scenarios:
            recent_run_id = context_runs[0]["id"] if context_runs else 1
            self.store_scenarios(scenarios, recent_run_id, usage)
            print(
                f"Scenario generation complete. "
                f"Used {usage.input_tokens} input tokens, "
                f"{usage.output_tokens} output tokens."
            )
            return scenarios
        else:
            print("No scenarios generated.")
            return []


if __name__ == "__main__":
    generator = AITestScenarioGenerator()
    scenarios = generator.run_generation_pipeline(num_scenarios=5)

    print("\nGenerated Scenarios:")
    for scenario in scenarios:
        print(f"  - {scenario.get('scenario_name', 'Unnamed')}")
        print(f"    Start: ({scenario.get('start_x', 0)}, {scenario.get('start_y', 0)})")
        print(f"    Obstacles: {scenario.get('obstacle_count', 0)}")
        print(f"    Reasoning: {scenario.get('reasoning', 'N/A')}\n")
