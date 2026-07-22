# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Generate a per-run PDF report (+ GitHub Job Summary) scoped to one runner_type's
own scenarios — not a rolling window of the last N runs. Historical trend views live
in the Piece 5 dashboard, not here."""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

# Plain-script safety — see tools/validate_telemetry.py for the why (same trap).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tools.baseline_monitor import check_run  # noqa: E402
from tools.telemetry_logger import DB_PATH  # noqa: E402

REPORT_PATH = os.getenv(
    "REPORT_PATH",
    os.path.join(_PROJECT_ROOT, "reports", "test_report.pdf")
)

_TABLE_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (-1, 0),  colors.grey),
    ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.whitesmoke),
    ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
    ("GRID",         (0, 0), (-1, -1), 0.5, colors.black),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
])


def load_run_rows(runner_type: str, scenarios: list, db_path: str = DB_PATH) -> list:
    """The latest row for each of `scenarios`, filtered to `runner_type` — 'this run's
    own result(s)', not a rolling window. A scenario with no matching row is omitted."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = []
    for scenario in scenarios:
        row = conn.execute(
            "SELECT * FROM runs WHERE runner_type = ? AND scenario = ? "
            "ORDER BY id DESC LIMIT 1",
            (runner_type, scenario),
        ).fetchone()
        if row is not None:
            rows.append(dict(row))
    conn.close()
    return rows


def generate_report(runner_type: str, scenarios: list, db_path: str = DB_PATH,
                     output_path: str = REPORT_PATH, config_path: str = None) -> str:
    rows = load_run_rows(runner_type, scenarios, db_path=db_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    reports_by_row_id = {
        row["id"]: check_run(row["id"], db_path=db_path, config_path=config_path)
        for row in rows
    }

    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Test Report — {runner_type}", styles["Title"]))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"Scenarios: {', '.join(scenarios)}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 12))

    for row in rows:
        story.append(Paragraph(
            f"{row['scenario']} — {row['result']}", styles["Heading2"]
        ))
        reports = reports_by_row_id[row["id"]]
        metric_table = [["Metric", "Current", "Baseline"]]
        for r in reports:
            metric_table.append([
                r.metric,
                f"{r.current:.2f}",
                f"{r.mean:.2f} ± {r.stddev:.2f}",
            ])
        if len(metric_table) > 1:
            t = Table(metric_table, colWidths=[180, 100, 140])
            t.setStyle(_TABLE_STYLE)
            story.append(t)
        else:
            story.append(Paragraph("No metrics available for comparison.",
                                    styles["Normal"]))
        story.append(Spacer(1, 16))

    doc.build(story)
    print(f"Report saved to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a per-run PDF report for one runner_type's own scenarios"
    )
    parser.add_argument("--runner-type", required=True)
    parser.add_argument("--scenario", action="append", required=True, dest="scenarios",
                         help="repeatable — one of this stage's known scenarios")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--report-path", default=REPORT_PATH)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    generate_report(args.runner_type, args.scenarios, db_path=args.db,
                     output_path=args.report_path, config_path=args.config)


if __name__ == "__main__":
    main()
