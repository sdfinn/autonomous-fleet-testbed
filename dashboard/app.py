# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Streamlit telemetry dashboard over FLEET_DB (~/fleet-ci-data/fleet_runs.db by default).

Session 17 code review fix wave (2026-07-19): AI-scenario tab and YOLO-era camera
metrics removed with the rest of that subsystem (CR-05); filters are now derived from
the data so new runner types (hil_jetson!) appear automatically (CR-07); Mission 2
telemetry (power_mode, seed, home_photo_similarity) is surfaced; goal zones come from
tools.goal_zones instead of a hardcoded rectangle (CR-12).
"""
import os
import sqlite3
import sys
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# streamlit puts the SCRIPT's dir on sys.path, not the cwd — make repo-root imports work.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.baseline_monitor import build_trend_summary, check_history, is_trending_worse, load_config  # noqa: E402
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
scenario_filter = st.sidebar.selectbox("Scenario", _filter_options(runs, "scenario"))

for column, choice in (("robot_type", robot_type_filter),
                       ("runner_type", runner_type_filter),
                       ("sim_engine", sim_engine_filter),
                       ("power_mode", power_mode_filter),
                       ("scenario", scenario_filter)):
    if choice != "All" and column in runs.columns:
        runs = runs[runs[column] == choice]

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    'Overview', 'Scenarios', 'Telemetry', 'Sensor Health', 'Drift'
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

# ── Tab 5: Drift ─────────────────────────────────────────────────────────────
with tab5:
    st.subheader('Drift Detection — Big Picture')
    st.caption(
        'Every watched metric over time against its own rolling baseline — not just '
        'the last run. Filters above (Runner, Power Mode, Scenario) scope this view.'
    )

    _drift_runner_type = None if runner_type_filter == "All" else runner_type_filter
    _drift_power_mode = None if power_mode_filter == "All" else power_mode_filter
    _drift_scenario = None if scenario_filter == "All" else scenario_filter

    history = check_history(
        runner_type=_drift_runner_type,
        power_mode=_drift_power_mode,
        scenario=_drift_scenario,
        db_path=DB_PATH,
    )

    if not history:
        st.info('No runs match the current filters — widen them to see drift trends.')
    else:
        _cfg = load_config()
        _bands = _cfg['sigma']
        _severity_order = ('critical', 'error', 'warning', 'info')  # widest drawn first
        _severity_colors = {
            'info': 'rgba(255, 235, 59, 0.15)',
            'warning': 'rgba(255, 152, 0, 0.15)',
            'error': 'rgba(244, 67, 54, 0.15)',
            'critical': 'rgba(183, 28, 28, 0.15)',
        }

        # Runs metadata (timestamp) for the x-axis — `runs` here is already filtered
        # by the sidebar, so this join is scoped consistently with `history`.
        _runs_by_id = runs.set_index('id')

        by_metric = {}
        for run_id in sorted(history):
            if run_id not in _runs_by_id.index:
                continue
            for r in history[run_id]:
                by_metric.setdefault(r.metric, []).append((run_id, r))

        _trending_metrics = []
        for metric, points in by_metric.items():
            _values = [r.current for _, r in points]
            _direction = points[-1][1].direction
            _already_flagged = points[-1][1].flagged
            if not _already_flagged and is_trending_worse(_values, _direction):
                _trending_metrics.append(metric)
        if _trending_metrics:
            st.warning(
                f'⚠️ Trending toward drift (not yet flagged): '
                f'{", ".join(_trending_metrics)}'
            )

        for metric, points in by_metric.items():
            xs = [_runs_by_id.loc[run_id, 'timestamp'] for run_id, _ in points]
            means = [r.mean for _, r in points]
            stddevs = [r.stddev for _, r in points]
            currents = [r.current for _, r in points]
            flagged_flags = [r.flagged for _, r in points]

            fig = go.Figure()
            for severity in _severity_order:
                threshold = _bands.get(severity)
                if threshold is None:
                    continue
                upper = [m + threshold * sd for m, sd in zip(means, stddevs)]
                lower = [m - threshold * sd for m, sd in zip(means, stddevs)]
                fig.add_trace(go.Scatter(x=xs, y=upper, mode='lines',
                                          line=dict(width=0), showlegend=False,
                                          hoverinfo='skip'))
                fig.add_trace(go.Scatter(x=xs, y=lower, mode='lines',
                                          line=dict(width=0), fill='tonexty',
                                          fillcolor=_severity_colors[severity],
                                          name=severity, hoverinfo='skip'))

            fig.add_trace(go.Scatter(x=xs, y=means, mode='lines',
                                      line=dict(color='blue', dash='dash'),
                                      name='baseline mean'))

            point_colors = ['#e74c3c' if f else '#2ecc71' for f in flagged_flags]
            fig.add_trace(go.Scatter(
                x=xs, y=currents, mode='markers+lines',
                marker=dict(color=point_colors, size=8),
                line=dict(color='rgba(100,100,100,0.3)'),
                name=metric,
                text=[f'run {run_id}' for run_id, _ in points],
                hovertemplate='%{text}<br>%{y:.3f}<extra></extra>',
            ))
            fig.update_layout(title=metric, showlegend=False, height=250,
                               margin=dict(l=40, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader('Run Detail (drill-down)')
        detail_rows = []
        for run_id in sorted(history, reverse=True):
            if run_id not in _runs_by_id.index:
                continue
            row = _runs_by_id.loc[run_id]
            flagged_metrics = [r.metric for r in history[run_id] if r.flagged]
            detail_rows.append({
                'run_id': run_id,
                'scenario': row['scenario'],
                'timestamp': row['timestamp'],
                'result': row['result'],
                'flagged_metrics': ', '.join(flagged_metrics) if flagged_metrics else '—',
            })
        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True)

        st.divider()
        st.subheader('AI Diagnosis')
        st.caption(
            'Feeds this filtered view\'s trend to the configured diagnosis backend '
            '(a local Ollama model by default, or Claude) for a proposed diagnosis. '
            'Logs this diagnosis automatically for future review — applies nothing.'
        )
        # 2026-07-29: second "Experimental AI" button, same pipeline, different
        # Ollama model — for side-by-side comparison of response quality AND
        # response time (Mike's explicit ask). PRIMARY_MODEL/EXPERIMENTAL_MODEL
        # are the only things that change between the two buttons; everything
        # else (offer_tools=False, describe_potential_changes(), rendering) is
        # 100% shared code, not duplicated, so the two paths can't drift out of
        # sync with each other. Landed here 2026-07-29 after a full live
        # comparison across 8 local models (see
        # docs/local-llm-diagnosis-model-comparison-2026-07-29.md for the full
        # table, methodology, and decision writeup) — PRIMARY_MODEL went
        # qwen2.5:14b-instruct -> gemma2:27b -> phi4; EXPERIMENTAL_MODEL went
        # qwen2.5:32b -> llama3.3:70b -> llama3.1:8b -> gemma3:12b ->
        # gemma3:27b -> llama3.3:70b -> gemma2:27b (2026-07-29, Mike's
        # explicit call after the JSON-envelope redesign landed — swapped off
        # Llama 3.3 70B's ~4min latency and thinner-under-JSON-constraint
        # output, discussed live, in favor of Gemma 2 27B's still-strong
        # grounding at a fraction of the time, ~45s in the original
        # comparison).
        PRIMARY_MODEL = 'phi4'
        EXPERIMENTAL_MODEL = 'gemma2:27b'

        def _render_diagnosis_result(response, model_label, elapsed_seconds):
            from tools.agentic_loop import describe_potential_changes  # local import,
            # same reasoning as the diagnose() import below.
            analysis_text = '\n'.join(
                block.text for block in response.content if block.type == 'text') or None

            st.markdown(f'#### Results — `{model_label}` ({elapsed_seconds:.1f}s)')

            # Distinct heading from the model's own — the model tends to write its
            # own "Metrics Analysis"/"Recommendations" headings inside this same
            # text, which looked like an accidental duplicate otherwise.
            st.markdown("##### Model's Written Analysis (raw text)")
            if analysis_text:
                st.caption(
                    'Shown once, unedited. Explanatory only — never programmatically '
                    'trusted or acted on. Recommendations are requested separately as '
                    'structured data (see Summary below), not extracted from this text.'
                )
                st.markdown(analysis_text)
            else:
                st.caption('(model gave no free-text analysis this time)')

            # Plain-language only, 2026-07-29 (Mike's explicit call): no tool
            # names, no JSON, no good/bad/unverified/conflict badges. Redesigned
            # same day (JSON-envelope): recommendations now come from the response's
            # own structured `recommendations` field, not best-effort-parsed out of
            # the text above — see tools/agentic_loop.describe_potential_changes.
            st.markdown('##### Summary')
            for line in describe_potential_changes(getattr(response, 'recommendations', [])):
                st.markdown(f'- {line}')

        button_col1, button_col2 = st.columns(2)
        with button_col1:
            diagnose_clicked = st.button('Diagnose with AI')
        with button_col2:
            experimental_clicked = st.button('Experimental AI — May take a long time')

        if diagnose_clicked or experimental_clicked:
            from tools.agentic_loop import diagnose  # local import: avoid constructing
            # anthropic.Anthropic() (module-level in agentic_loop.py) unless a button
            # is actually clicked.
            visible_ids = [rid for rid in history if rid in _runs_by_id.index]
            if not visible_ids:
                st.info('No runs in the current view to diagnose.')
            else:
                visible_history = {rid: history[rid] for rid in visible_ids}
                trend_context = build_trend_summary(visible_history)
                latest_run_id = max(visible_ids)
                latest_row = _runs_by_id.loc[latest_run_id]
                run_data = latest_row.to_dict()
                run_data['id'] = latest_run_id

                model_name = EXPERIMENTAL_MODEL if experimental_clicked else PRIMARY_MODEL
                model_label = model_name
                spinner_text = ('Asking the experimental model — this can take '
                                 'several minutes...' if experimental_clicked
                                 else 'Asking the model...')

                with st.spinner(spinner_text):
                    start = time.perf_counter()
                    # offer_tools=False (2026-07-29, 4th-round simplification, Mike's
                    # explicit call): the dashboard doesn't offer the model any tools
                    # at all — plain free text only, no tool-calling concept anywhere
                    # in this page. The CLI (tools/agentic_loop.py's run_loop()) is a
                    # separate, untouched call path that still uses tools normally.
                    response = diagnose(run_data, db_path=DB_PATH, trend_context=trend_context,
                                         source='dashboard', offer_tools=False,
                                         model_name=model_name)  # auto-logs
                    elapsed = time.perf_counter() - start

                _render_diagnosis_result(response, model_label, elapsed)
