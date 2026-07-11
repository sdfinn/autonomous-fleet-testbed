# Copyright 2026 Mike. Licensed under MIT.
"""Agentic test loop: diagnose failures, propose fixes, await human approval."""
import json
import os
import sqlite3
from pathlib import Path

import anthropic

from tools.baseline_monitor import check_run
# Canonical map lives in the nav_fleet package (Session 15) — the workspace overlay
# (auto-sourced by .bashrc) makes it importable here.
from nav_fleet.semantic_map import SEMANTIC_MAP

client = anthropic.Anthropic()

FLEET_DB = os.environ.get("FLEET_DB", "reports/fleet_runs.db")

TOOLS = [
    {
        'name': 'propose_nav_param_change',
        'description': 'Propose a change to nav2_params.yaml to address a navigation failure.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'param_path': {'type': 'string', 'description': 'Dot-separated param key'},
                'current_value': {'type': 'string'},
                'proposed_value': {'type': 'string'},
                'rationale': {'type': 'string'},
            },
            'required': ['param_path', 'proposed_value', 'rationale'],
        },
    },
    {
        'name': 'generate_world_variant',
        'description': (
            'Generate a new SDF world file with different obstacle positions '
            'for broader test coverage.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'variant_name': {'type': 'string'},
                'obstacle_layout': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'name': {'type': 'string'},
                            'x': {'type': 'number'},
                            'y': {'type': 'number'},
                            'size_x': {'type': 'number'},
                            'size_y': {'type': 'number'},
                        },
                    },
                },
                'rationale': {'type': 'string'},
            },
            'required': ['variant_name', 'obstacle_layout', 'rationale'],
        },
    },
    {
        'name': 'propose_mission_plan',
        'description': (
            'Generate a sequence of Nav2 goal poses from a natural language mission description. '
            'Prefer named locations from SEMANTIC_MAP over raw coordinates.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'mission_description': {'type': 'string'},
                'goals': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'location': {
                                'type': 'string',
                                'description': 'Named location from SEMANTIC_MAP, or "custom"',
                            },
                            'label': {
                                'type': 'string',
                                'description': 'Human-readable step label',
                            },
                            'x': {'type': 'number', 'description': 'Only if location is "custom"'},
                            'y': {'type': 'number', 'description': 'Only if location is "custom"'},
                        },
                        'required': ['location', 'label'],
                    },
                },
                'rationale': {'type': 'string'},
            },
            'required': ['mission_description', 'goals', 'rationale'],
        },
    },
]


def load_latest_run(db_path=FLEET_DB):
    """Load the most recent row from the `runs` table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    if row is None:
        raise FileNotFoundError(f'No runs found in {db_path}')
    return dict(row)


def resolve_goals(goals):
    """Resolve named locations to (x, y) coordinates."""
    resolved = []
    for g in goals:
        loc = g.get('location', 'custom')
        if loc in SEMANTIC_MAP:
            x, y = SEMANTIC_MAP[loc]
        else:
            x, y = g.get('x', 0.0), g.get('y', 0.0)
        resolved.append({'x': x, 'y': y, 'label': g.get('label', loc)})
    return resolved


def diagnose(run_data, db_path=FLEET_DB):
    """Call Claude with telemetry + drift context; get structured diagnosis and proposed action."""
    locations_str = '\n'.join(f'  {k}: {v}' for k, v in SEMANTIC_MAP.items())

    # Reuse the real drift detector (Session 12) instead of re-deriving pass/fail from
    # hardcoded thresholds — it compares against a rolling baseline of past PASS runs.
    drift_reports = check_run(run_data['id'], db_path=db_path)
    if drift_reports:
        drift_str = '\n'.join(
            f'  {r.metric}: current={r.current:.2f} baseline_mean={r.mean:.2f} '
            f'sigma={r.sigma:.1f} {"FLAGGED" if r.flagged else "ok"}'
            for r in drift_reports
        )
    else:
        drift_str = '  Not enough baseline history yet (need 3+ prior PASS runs).'

    prompt = f"""You are an autonomous robotics test engineer.

The latest nav test run (id={run_data['id']}, scenario={run_data['scenario']},
result={run_data['result']}, sim_engine={run_data.get('sim_engine')}):
{json.dumps(run_data, indent=2)}

Drift report against the rolling baseline (config/drift_config.yaml sigma thresholds):
{drift_str}

Available named locations in this environment (use these in mission plans):
{locations_str}

Analyse the results. If any metric is FLAGGED, diagnose the likely cause and use ONE
tool to propose a concrete action. If nothing is flagged, use propose_mission_plan
with semantic location names to create a more challenging multi-waypoint mission
(e.g. "visit the bedroom goal, then the desk, then return to home_base") or use
generate_world_variant to propose a harder obstacle layout."""

    response = client.messages.create(
        model='claude-sonnet-5',
        max_tokens=2048,
        tools=TOOLS,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response


def apply_world_variant(layout, name):
    """Write a new SDF world file from Claude's obstacle layout."""
    obstacles_sdf = ''
    for obs in layout:
        obstacles_sdf += f"""
    <model name="{obs['name']}">
      <static>true</static>
      <pose>{obs['x']} {obs['y']} 0.25 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>{obs['size_x']} {obs['size_y']} 0.5</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>{obs['size_x']} {obs['size_y']} 0.5</size></box></geometry>
          <material><diffuse>0.5 0.3 0.1 1</diffuse></material>
        </visual>
      </link>
    </model>"""

    world_path = Path(f'src/nav_fleet/worlds/{name}.sdf')
    # Read the base world template and inject obstacles
    base = Path('src/nav_fleet/worlds/bedroom_simple.sdf').read_text()
    # Insert before </world>
    new_world = base.replace('  </world>', obstacles_sdf + '\n  </world>')
    world_path.write_text(new_world)
    print(f'[agentic] Created world variant: {world_path}')
    return world_path


def human_approval(action_type, details):
    """Print the proposed action and ask for human approval."""
    separator = '=' * 60
    print(f'\n{separator}')
    print(f'PROPOSED ACTION: {action_type}')
    print(json.dumps(details, indent=2))
    print(separator)
    answer = input('\nApprove? [y/N]: ').strip().lower()
    return answer == 'y'


def run_loop():
    run_data = load_latest_run()
    print(f"[agentic] Loaded run {run_data['id']}: "
          f"{run_data['scenario']} ({run_data['result']})")

    response = diagnose(run_data)

    for block in response.content:
        if block.type == 'tool_use':
            tool = block.name
            inputs = block.input
            print(f'\n[agentic] Claude proposes: {tool}')

            if not human_approval(tool, inputs):
                print('[agentic] Proposal rejected by human. Exiting.')
                return

            if tool == 'generate_world_variant':
                apply_world_variant(inputs['obstacle_layout'], inputs['variant_name'])
                print(f'[agentic] World variant created. Re-run: '
                      f'ros2 launch nav_fleet sim_launch.py world:={inputs["variant_name"]}')

            elif tool == 'propose_nav_param_change':
                print('[agentic] Apply this change to config/nav2_params.yaml:')
                print(f'  {inputs["param_path"]}: {inputs["proposed_value"]}')
                print(f'  Rationale: {inputs["rationale"]}')

            elif tool == 'propose_mission_plan':
                resolved = resolve_goals(inputs['goals'])
                plan = {**inputs, 'goals_resolved': resolved}
                plan_path = Path('reports/mission_plan.json')
                plan_path.write_text(json.dumps(plan, indent=2))
                print(f'[agentic] Mission plan saved to {plan_path}')
                print(f'  Mission: {inputs["mission_description"]}')
                for step in resolved:
                    print(f'    → {step["label"]}: ({step["x"]}, {step["y"]})')

        elif block.type == 'text':
            print(f'\n[Claude analysis]\n{block.text}')


if __name__ == '__main__':
    run_loop()
