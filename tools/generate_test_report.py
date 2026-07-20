# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Auto-generate a PDF test report from the last 100 runs."""
import io
import os
import sqlite3
import sys
from datetime import datetime

# Plain-script safety — see tools/validate_telemetry.py for the why (same trap).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.getenv(
    "FLEET_DB",
    os.path.join(_PROJECT_ROOT, "reports", "fleet_runs.db")
)
REPORT_PATH = os.getenv(
    "REPORT_PATH",
    os.path.join(_PROJECT_ROOT, "reports", "test_report.pdf")
)

_RESULT_COLORS = {
    "PASS":    "#00cc44",
    "FAIL":    "#ff4444",
    "STOPPED": "#ff8800",
    "TIMEOUT": "#888888",
}


def load_data(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    runs = pd.read_sql("SELECT * FROM runs ORDER BY id DESC LIMIT 100", conn)
    conn.close()
    return runs


def make_pass_fail_chart(runs) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(6, 3))
    stats = runs.groupby("scenario")["result"].value_counts().unstack(fill_value=0)
    bar_colors = [_RESULT_COLORS.get(col, "#aaaaaa") for col in stats.columns]
    stats.plot(kind="bar", ax=ax, color=bar_colors)
    ax.set_title("Pass / Fail by Scenario")
    ax.set_xlabel("")
    ax.set_ylabel("Count")
    ax.legend(loc="upper right")
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def make_position_scatter(runs) -> io.BytesIO:
    from tools.goal_zones import end_zones  # local import: keeps report usable standalone
    fig, ax = plt.subplots(figsize=(5, 5))
    for result, group in runs.groupby("result"):
        ax.scatter(
            group["final_x"], group["final_y"],
            c=_RESULT_COLORS.get(result, "#aaaaaa"),
            label=result, alpha=0.7, s=40,
        )
    # End zones derived from mission data (S17 review CR-12) — one box per distinct
    # final goal (home_base for the missions, bedroom_goal for the BR-01 nav test).
    for zone in end_zones():
        rect = plt.Rectangle(
            (zone["x"] - zone["tol"], zone["y"] - zone["tol"]),
            2 * zone["tol"], 2 * zone["tol"],
            linewidth=2, edgecolor="blue", facecolor="none", linestyle="--",
        )
        ax.add_patch(rect)
        ax.annotate(zone["label"], (zone["x"], zone["y"] + zone["tol"] + 0.05),
                    ha="center", fontsize=6, color="blue")
    ax.set_title("Final Robot Positions")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.legend()
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_report(db_path=DB_PATH, output_path=REPORT_PATH):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    runs = load_data(db_path)
    total = len(runs)
    passed = (runs["result"] == "PASS").sum()
    pass_rate = f"{100 * passed / max(total, 1):.1f}%"

    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Autonomous Navigation Test Report", styles["Title"]))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"Runs analyzed: {total}  |  Pass rate: {pass_rate}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 12))

    metric_fields = [
        ("Nav Success Rate", "nav_success_rate"),
        ("Mean Position Error", "mean_position_error"),
        ("Mean Time to Goal", "mean_time_to_goal"),
        ("Collision Rate", "collision_rate"),
        ("Odom Hz Mean", "odom_hz_mean"),
        ("LiDAR Hz Mean", "lidar_hz_mean"),
        ("Camera Hz Mean", "camera_hz_mean"),
    ]
    summary_data = [
        ["Metric", "Value"],
        ["Total Runs", str(total)],
        ["Passed", str(int(passed))],
        ["Failed", str(total - int(passed))],
        ["Pass Rate", pass_rate],
    ]

    for label, col in metric_fields:
        if col in runs.columns:
            avg = runs[col].mean()
            summary_data.append([
                label,
                f"{avg:.2f}" if not pd.isna(avg) else "N/A",
            ])

    if "steps" in runs.columns:
        avg_steps = runs[runs["result"] == "PASS"]["steps"].mean()
        summary_data.append([
            "Avg Steps (PASS)",
            f"{avg_steps:.0f}" if not pd.isna(avg_steps) else "N/A",
        ])
    t = Table(summary_data, colWidths=[200, 200])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  colors.grey),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.whitesmoke),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.black),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    story.append(RLImage(make_pass_fail_chart(runs), width=450, height=225))
    story.append(Spacer(1, 12))
    story.append(RLImage(make_position_scatter(runs), width=375, height=375))

    doc.build(story)
    print(f"Report saved to {output_path}")
    return output_path


if __name__ == "__main__":
    generate_report()
