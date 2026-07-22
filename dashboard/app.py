# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Streamlit telemetry dashboard over FLEET_DB (reports/fleet_runs.db by default).

Session 17 code review fix wave (2026-07-19): AI-scenario tab and YOLO-era camera
metrics removed with the rest of that subsystem (CR-05); filters are now derived from
the data so new runner types (hil_jetson!) appear automatically (CR-07); Mission 2
telemetry (power_mode, seed, home_photo_similarity) is surfaced; goal zones come from
tools.goal_zones instead of a hardcoded rectangle (CR-12).
"""
import os
import sqlite3
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

# streamlit puts the SCRIPT's dir on sys.path, not the cwd — make repo-root imports work.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.goal_zones import end_zones  # noqa: E402
from tools.telemetry_logger import DB_PATH  # noqa: E402

COLOR_MAP = {
    "PASS":    "#2ecc71",
    "FAIL":    "#e74c3c",
    "STOPPED": "#e67e22",
    "TIMEOUT": "#95a5a6",
}
RESULT_ORDER = ("PASS", "FAIL", "STOPPED", "TIMEOUT")
# Mission 2 return-fidelity gross-failure guard — mirrors tools/mission2_harness.py.
HOME_PAIR_MAX_DIFF = 0.18


@st.cache_data(ttl=30)
def load_runs():
    conn = sqlite3.connect(DB_PATH)
    runs = pd.read_sql('SELECT * FROM runs ORDER BY id DESC', conn)
    steps = pd.read_sql('SELECT * FROM steps', conn)
    conn.close()
    return runs, steps


def _filter_options(df, column):
    """Sidebar options derived from the data — a new runner_type/sim_engine value shows
    up here automatically instead of waiting for a hardcoded list update (CR-07)."""
    if column not in df.columns:
        return ["All"]
    return ["All"] + sorted(v for v in df[column].dropna().unique())


st.set_page_config(page_title='Nav Test Dashboard', layout='wide')
st.title('Autonomous Navigation Test Dashboard')

runs, steps = load_runs()

robot_type_filter = st.sidebar.selectbox("Robot Type", _filter_options(runs, "robot_type"))
runner_type_filter = st.sidebar.selectbox("Runner", _filter_options(runs, "runner_type"))
sim_engine_filter = st.sidebar.selectbox("Sim Engine", _filter_options(runs, "sim_engine"))
power_mode_filter = st.sidebar.selectbox("Power Mode", _filter_options(runs, "power_mode"))

for column, choice in (("robot_type", robot_type_filter),
                       ("runner_type", runner_type_filter),
                       ("sim_engine", sim_engine_filter),
                       ("power_mode", power_mode_filter)):
    if choice != "All" and column in runs.columns:
        runs = runs[runs[column] == choice]

tab1, tab2, tab3, tab4 = st.tabs([
    'Overview', 'Scenarios', 'Telemetry', 'Sensor Health'
])

# ── Tab 1: Overview ──────────────────────────────────────────────────────────
with tab1:
    col1, col2, col3, col4 = st.columns(4)
    total = len(runs)
    passed = (runs['result'] == 'PASS').sum()
    col1.metric('Total Runs', total)
    col2.metric('Passed', passed)
    col3.metric('Failed', total - passed)
    col4.metric('Pass Rate', f'{passed / total * 100:.1f}%' if total else 'N/A')

    st.divider()

    scenario_stats = (
        runs.groupby('scenario')['result']
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in RESULT_ORDER:
        if col not in scenario_stats.columns:
            scenario_stats[col] = 0
    result_cols = [c for c in RESULT_ORDER if scenario_stats[c].sum() > 0]
    fig_bar = px.bar(
        scenario_stats,
        x='scenario',
        y=result_cols,
        color_discrete_map=COLOR_MAP,
        barmode='stack',
        title='Pass / Fail Count per Scenario',
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    if ('lidar_min_range' in runs.columns and runs['lidar_min_range'].notna().any()) or \
       ('camera_hz_mean' in runs.columns and runs['camera_hz_mean'].notna().any()) or \
       ('nav_success_rate' in runs.columns and runs['nav_success_rate'].notna().any()):
        st.divider()
        st.subheader('Sensor Health')
        metrics = []
        if 'lidar_min_range' in runs.columns and runs['lidar_min_range'].notna().any():
            metrics.append(('Avg LiDAR Min Range (m)', f"{runs['lidar_min_range'].mean():.2f}"))
        if 'num_obstacles_detected' in runs.columns and runs['num_obstacles_detected'].notna().any():
            metrics.append(('Avg Obstacles Detected', f"{runs['num_obstacles_detected'].mean():.1f}"))
        if 'camera_hz_mean' in runs.columns and runs['camera_hz_mean'].notna().any():
            metrics.append(('Avg Camera Hz', f"{runs['camera_hz_mean'].mean():.2f}"))
        if 'lidar_hz_mean' in runs.columns and runs['lidar_hz_mean'].notna().any():
            metrics.append(('Avg LiDAR Hz', f"{runs['lidar_hz_mean'].mean():.2f}"))
        if 'nav_success_rate' in runs.columns and runs['nav_success_rate'].notna().any():
            # 0-1 value rendered as percent (CR-06: was displayed as "1.0%" for perfect)
            metrics.append(('Avg Nav Success Rate',
                            f"{runs['nav_success_rate'].mean() * 100:.1f}%"))

        cols = st.columns(min(len(metrics), 4))
        for col, (label, value) in zip(cols, metrics):
            col.metric(label, value)

# ── Tab 2: Scenarios ─────────────────────────────────────────────────────────
with tab2:
    st.subheader('Pass Rate by Scenario')
    if not scenario_stats.empty:
        all_result_cols = [c for c in RESULT_ORDER if c in scenario_stats.columns]
        scenario_stats['total'] = scenario_stats[all_result_cols].sum(axis=1)
        scenario_stats['pass_rate'] = (
            scenario_stats['PASS'] / scenario_stats['total'].replace(0, float('nan')) * 100
        ).round(1)
        display_cols = ['scenario'] + all_result_cols + ['pass_rate']
        st.dataframe(
            scenario_stats[display_cols],
            use_container_width=True,
        )
    st.divider()
    st.subheader('Run Log')
    log_cols = ['id', 'scenario', 'timestamp', 'steps', 'final_x', 'final_y', 'result']
    # HIL-era columns (CR-07): show them whenever present.
    log_cols += [c for c in ('robot_id', 'sim_engine', 'runner_type', 'power_mode',
                             'seed', 'home_photo_similarity') if c in runs.columns]
    st.dataframe(
        runs[log_cols],
        use_container_width=True,
    )

# ── Tab 3: Telemetry ─────────────────────────────────────────────────────────
with tab3:
    st.subheader('Final Position Heatmap')
    nav_runs = runs[runs['scenario'] != 'ros2_telemetry_run']
    fig_scatter = px.scatter(
        nav_runs,
        x='final_x',
        y='final_y',
        color='result',
        color_discrete_map=COLOR_MAP,
        title='Final Robot Position per Run (navigation tests only)',
        labels={'final_x': 'X (m)', 'final_y': 'Y (m)'},
    )
    # End zones derived from mission data (CR-12) — one box per distinct final goal.
    for zone in end_zones():
        fig_scatter.add_shape(
            type='rect',
            x0=zone['x'] - zone['tol'], x1=zone['x'] + zone['tol'],
            y0=zone['y'] - zone['tol'], y1=zone['y'] + zone['tol'],
            line=dict(color='blue', width=2, dash='dash'),
        )
        fig_scatter.add_annotation(
            x=zone['x'], y=zone['y'] + zone['tol'] + 0.12,
            text=zone['label'], showarrow=False, font=dict(size=10, color='blue'))
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.divider()
    st.subheader('Steps to Complete per Scenario')
    fig_box = px.box(
        runs[runs['result'] == 'PASS'],
        x='scenario',
        y='steps',
        title='Step Count Distribution (PASS runs only)',
    )
    st.plotly_chart(fig_box, use_container_width=True)

    # Mission 2 return fidelity (CR-07): the home_ref-vs-home_arrival photo similarity
    # per run, against the gross-failure guard threshold.
    if 'home_photo_similarity' in runs.columns and runs['home_photo_similarity'].notna().any():
        st.divider()
        st.subheader('Mission 2 Return Fidelity (home photo pair)')
        m2 = runs[runs['home_photo_similarity'].notna()].sort_values('id')
        fig_sim = px.scatter(
            m2, x='id', y='home_photo_similarity', color='scenario',
            title=f'Home-pair similarity per run (guard: {HOME_PAIR_MAX_DIFF} — '
                  'lower is a more faithful return)',
            labels={'id': 'run id', 'home_photo_similarity': 'mean abs gray diff [0..1]'},
        )
        fig_sim.add_hline(y=HOME_PAIR_MAX_DIFF, line_dash='dash', line_color='red')
        st.plotly_chart(fig_sim, use_container_width=True)

# ── Tab 4: Sensor Health ──────────────────────────────────────────────────────
with tab4:
    st.subheader('Sensor Health')

    conn = sqlite3.connect(DB_PATH)
    df_lidar = pd.read_sql("""
        SELECT scenario, lidar_min_range, lidar_max_range, num_obstacles_detected
        FROM runs
        WHERE lidar_min_range IS NOT NULL
        ORDER BY id DESC LIMIT 20
    """, conn)
    conn.close()

    if df_lidar.empty:
        st.info('No LiDAR data yet — run scenarios with the LiDAR enabled.')
    else:
        lc1, lc2 = st.columns(2)
        lc1.metric('Avg Min Range (m)', f"{df_lidar['lidar_min_range'].mean():.2f}")
        lc2.metric('Avg Obstacles Detected', f"{df_lidar['num_obstacles_detected'].mean():.1f}")
        st.dataframe(df_lidar, use_container_width=True)
