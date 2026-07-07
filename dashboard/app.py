import os
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = os.environ.get("FLEET_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "fleet_runs.db"))

COLOR_MAP = {
    "PASS":    "#2ecc71",
    "FAIL":    "#e74c3c",
    "STOPPED": "#e67e22",
    "TIMEOUT": "#95a5a6",
}


@st.cache_data(ttl=30)
def load_runs():
    conn = sqlite3.connect(DB_PATH)
    runs = pd.read_sql('SELECT * FROM runs ORDER BY id DESC', conn)
    steps = pd.read_sql('SELECT * FROM steps', conn)
    conn.close()
    return runs, steps


@st.cache_data(ttl=30)
def load_ai_scenarios():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT scenario_name, test_status, ai_model,
                   prompt_tokens, response_tokens, generated_on
            FROM ai_scenarios
            ORDER BY generated_on DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


st.set_page_config(page_title='Nav Test Dashboard', layout='wide')
st.title('Autonomous Navigation Test Dashboard')

robot_type_filter = st.sidebar.selectbox("Robot Type", ["All", "jetson_ugv_pt"])
runner_type_filter = st.sidebar.selectbox("Runner", ["All", "qemu", "jetson", "local"])
sim_engine_filter = st.sidebar.selectbox("Sim Engine", ["All", "gazebo", "isaac", "real"])

runs, steps = load_runs()
ai_df = load_ai_scenarios()

filtered_runs = runs
if robot_type_filter != "All" and "robot_type" in filtered_runs.columns:
    filtered_runs = filtered_runs[filtered_runs["robot_type"] == robot_type_filter]
if runner_type_filter != "All" and "runner_type" in filtered_runs.columns:
    filtered_runs = filtered_runs[filtered_runs["runner_type"] == runner_type_filter]
if sim_engine_filter != "All" and "sim_engine" in filtered_runs.columns:
    filtered_runs = filtered_runs[filtered_runs["sim_engine"] == sim_engine_filter]

runs = filtered_runs

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    'Overview', 'Scenarios', 'Telemetry', 'AI-Generated Scenarios', 'Sensor Health'
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
    for col in ("PASS", "FAIL", "STOPPED", "TIMEOUT"):
        if col not in scenario_stats.columns:
            scenario_stats[col] = 0
    result_cols = [c for c in ("PASS", "FAIL", "STOPPED", "TIMEOUT") if scenario_stats[c].sum() > 0]
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
        if 'detections_per_frame_avg' in runs.columns and runs['detections_per_frame_avg'].notna().any():
            metrics.append(('Avg YOLO Detections/Frame', f"{runs['detections_per_frame_avg'].mean():.1f}"))
        if 'camera_hz_mean' in runs.columns and runs['camera_hz_mean'].notna().any():
            metrics.append(('Avg Camera Hz', f"{runs['camera_hz_mean'].mean():.2f}"))
        if 'lidar_hz_mean' in runs.columns and runs['lidar_hz_mean'].notna().any():
            metrics.append(('Avg LiDAR Hz', f"{runs['lidar_hz_mean'].mean():.2f}"))
        if 'nav_success_rate' in runs.columns and runs['nav_success_rate'].notna().any():
            metrics.append(('Avg Nav Success Rate', f"{runs['nav_success_rate'].mean():.1f}%"))

        cols = st.columns(min(len(metrics), 4))
        for col, (label, value) in zip(cols, metrics):
            col.metric(label, value)

# ── Tab 2: Scenarios ─────────────────────────────────────────────────────────
with tab2:
    st.subheader('Pass Rate by Scenario')
    if not scenario_stats.empty:
        all_result_cols = [c for c in ("PASS", "FAIL", "STOPPED", "TIMEOUT") if c in scenario_stats.columns]
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
    log_cols += [c for c in ('robot_id', 'sim_engine') if c in runs.columns]
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
    # Goal zone — bedroom floor centre (0.0, 3.7), +/- Nav2's xy_goal_tolerance (0.15 m)
    fig_scatter.add_shape(
        type='rect',
        x0=-0.15, x1=0.15, y0=3.55, y1=3.85,
        line=dict(color='blue', width=2, dash='dash'),
        name='Goal Zone',
    )
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

# ── Tab 4: AI-Generated Scenarios ────────────────────────────────────────────
with tab4:
    st.subheader('AI-Generated Test Scenarios')

    if ai_df.empty:
        st.info('No AI scenarios in database yet. Run `python src/ai_test_generator.py` to generate some.')
    else:
        ai_total = len(ai_df)
        ai_passed = (ai_df['test_status'] == 'passed').sum()
        ai_pending = (ai_df['test_status'] == 'pending').sum()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric('Total AI Scenarios', ai_total)
        col2.metric('Passed', ai_passed)
        col3.metric('Pending', ai_pending)
        col4.metric('Pass Rate', f'{ai_passed / ai_total * 100:.1f}%' if ai_total else 'N/A')

        st.divider()
        st.write('#### Recent AI-Generated Scenarios')
        st.dataframe(
            ai_df[['scenario_name', 'test_status', 'ai_model', 'prompt_tokens', 'response_tokens', 'generated_on']],
            use_container_width=True,
        )

        st.divider()
        st.write('#### AI-Generated vs Manual: Pass Rate Comparison')
        manual_total = len(runs)
        manual_passed = int((runs['result'] == 'PASS').sum())
        comparison = pd.DataFrame([
            {
                'source': 'Manual',
                'total': manual_total,
                'passed': manual_passed,
                'pass_rate': round(manual_passed / manual_total * 100, 1) if manual_total else 0,
            },
            {
                'source': 'AI-Generated',
                'total': ai_total,
                'passed': int(ai_passed),
                'pass_rate': round(int(ai_passed) / ai_total * 100, 1) if ai_total else 0,
            },
        ])
        fig_cmp = px.bar(
            comparison,
            x='source',
            y='pass_rate',
            text='pass_rate',
            color='source',
            color_discrete_map={'Manual': '#4ECDC4', 'AI-Generated': '#FF6B6B'},
            title='Pass Rate: AI-Generated vs Manual Scenarios',
            labels={'pass_rate': 'Pass Rate (%)'},
        )
        fig_cmp.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        st.plotly_chart(fig_cmp, use_container_width=True)

        st.write('#### Token Usage')
        token_df = ai_df[['ai_model', 'prompt_tokens', 'response_tokens']].dropna()
        if not token_df.empty:
            st.dataframe(token_df, use_container_width=True)
            total_in = int(token_df['prompt_tokens'].sum())
            total_out = int(token_df['response_tokens'].sum())
            st.caption(f'Total tokens used: {total_in:,} input / {total_out:,} output across {ai_total} scenarios')

# ── Tab 5: Sensor Health ──────────────────────────────────────────────────────
with tab5:
    st.subheader('Sensor Health')

    conn = sqlite3.connect(DB_PATH)

    # LiDAR metrics
    st.write('#### LiDAR')
    df_lidar = pd.read_sql("""
        SELECT scenario, lidar_min_range, lidar_max_range, num_obstacles_detected
        FROM runs
        WHERE lidar_min_range IS NOT NULL
        ORDER BY id DESC LIMIT 20
    """, conn)

    if df_lidar.empty:
        st.info('No LiDAR data yet — run scenarios with the LiDAR prim enabled.')
    else:
        lc1, lc2 = st.columns(2)
        lc1.metric('Avg Min Range (m)', f"{df_lidar['lidar_min_range'].mean():.2f}")
        lc2.metric('Avg Obstacles Detected', f"{df_lidar['num_obstacles_detected'].mean():.1f}")
        st.dataframe(df_lidar, use_container_width=True)

    # Camera / YOLO metrics — not part of this project's schema yet (no object-detection
    # pipeline built); query degrades gracefully if num_frames etc. don't exist.
    st.write('#### Camera & Object Detection')
    try:
        df_camera = pd.read_sql("""
            SELECT scenario, num_frames, detections_per_frame_avg, class_distribution
            FROM runs
            WHERE num_frames IS NOT NULL
            ORDER BY id DESC LIMIT 20
        """, conn)
    except Exception:
        df_camera = pd.DataFrame()

    if df_camera.empty:
        st.info('No camera detection data yet.')
    else:
        cc1, cc2 = st.columns(2)
        cc1.metric('Avg Frames per Run', f"{df_camera['num_frames'].mean():.0f}")
        cc2.metric('Avg Detections/Frame', f"{df_camera['detections_per_frame_avg'].mean():.2f}")
        st.dataframe(
            df_camera[['scenario', 'num_frames', 'detections_per_frame_avg']],
            use_container_width=True,
        )

    # AI scenario quality scores — ai_scenarios table doesn't exist until Session 13.
    st.write('#### AI Scenario Quality')
    try:
        df_quality = pd.read_sql("""
            SELECT scenario_name, test_quality, test_status, generated_on
            FROM ai_scenarios
            WHERE test_quality IS NOT NULL
            ORDER BY test_quality DESC LIMIT 10
        """, conn)
    except Exception:
        df_quality = pd.DataFrame()

    if df_quality.empty:
        st.info('No AI quality scores yet — run `python src/ai_test_generator.py`.')
    else:
        fig_quality = px.bar(
            df_quality, x='scenario_name', y='test_quality',
            title='AI Scenario Quality Scores (1.0 = highest learning value)',
            color='test_quality', color_continuous_scale='RdYlGn',
        )
        st.plotly_chart(fig_quality, use_container_width=True)

    conn.close()
