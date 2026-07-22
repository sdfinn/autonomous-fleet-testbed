# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Generate a per-run PDF report (+ GitHub Job Summary) scoped to one runner_type's
own scenarios — not a rolling window of the last N runs. Historical trend views live
in the Piece 5 dashboard, not here."""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta

# Plain-script safety — see tools/validate_telemetry.py for the why (same trap).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tools.baseline_monitor import check_run  # noqa: E402
from tools.telemetry_logger import DB_PATH, PHOTO_DIR  # noqa: E402

REPORT_PATH = os.getenv(
    "REPORT_PATH",
    os.path.join(_PROJECT_ROOT, "reports", "test_report.pdf")
)
PHOTO_WINDOW_SECONDS = 180

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


def find_run_photos(row_timestamp: str, photo_dir: str = PHOTO_DIR,
                     window_seconds: int = PHOTO_WINDOW_SECONDS) -> list:
    """Photos taken in the window immediately before this row's own timestamp. There's
    no DB column linking a row to its photo(s) — proximity in time is the correlation
    signal instead, since missions run sequentially on one machine and each mission's
    own photo(s) land well inside the window before that mission's telemetry row is
    logged. Returns paths oldest-first."""
    if not os.path.isdir(photo_dir):
        return []
    row_dt = datetime.strptime(row_timestamp, "%Y-%m-%dT%H:%M:%S")
    matches = []
    for name in os.listdir(photo_dir):
        if not name.endswith(".png"):
            continue
        parts = name[:-4].rsplit("_", 2)  # label, YYYYmmdd, HHMMSS
        if len(parts) != 3:
            continue
        _, date_part, time_part = parts
        try:
            photo_dt = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
        except ValueError:
            continue
        delta = (row_dt - photo_dt).total_seconds()
        if 0 <= delta <= window_seconds:
            matches.append((photo_dt, os.path.join(photo_dir, name)))
    matches.sort()
    return [path for _, path in matches]


def build_job_summary(runner_type: str, rows: list, reports_by_row_id: dict,
                       any_flagged: bool, evidence_artifact: str = None) -> str:
    """Markdown for $GITHUB_STEP_SUMMARY — renders directly on the run's summary page,
    so PASS/FAIL and the drift verdict are visible with zero clicks."""
    lines = [f"## {'⚠ DRIFT DETECTED' if any_flagged else 'Report'} — {runner_type}", ""]
    for row in rows:
        lines.append(f"- **{row['scenario']}**: {row['result']}")
        for r in reports_by_row_id.get(row["id"], []):
            if r.flagged:
                word = "below" if r.direction == "down" else "above"
                lines.append(
                    f"  - ⚠ `{r.metric}` is {r.sigma:.1f}σ {word} baseline "
                    f"({r.current:.2f} vs {r.mean:.2f} typical)"
                )
    if evidence_artifact:
        lines.append("")
        lines.append(
            f"Evidence (photos, Nav2 logs, failure bags) for this run: "
            f"see the `{evidence_artifact}` artifact on this run's Actions page."
        )
    lines.append("")
    return "\n".join(lines)


def generate_report(runner_type: str, scenarios: list, db_path: str = DB_PATH,
                     output_path: str = REPORT_PATH, config_path: str = None,
                     photo_dir: str = PHOTO_DIR, evidence_artifact: str = None) -> str:
    rows = load_run_rows(runner_type, scenarios, db_path=db_path)

    reports_by_row_id = {
        row["id"]: check_run(row["id"], db_path=db_path, config_path=config_path)
        for row in rows
    }
    any_flagged = any(
        r.flagged for reports in reports_by_row_id.values() for r in reports
    )

    if any_flagged:
        root, ext = os.path.splitext(output_path)
        output_path = f"{root}-DRIFT{ext}"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    if any_flagged:
        story.append(Paragraph(
            "⚠ DRIFT DETECTED",
            ParagraphStyle("DriftBanner", parent=styles["Title"], textColor=colors.red),
        ))
    else:
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
        flagged = [r for r in reports if r.flagged]
        if flagged:
            for r in flagged:
                word = "below" if r.direction == "down" else "above"
                story.append(Paragraph(
                    f"⚠ {r.metric} is {r.sigma:.1f}σ {word} baseline "
                    f"({r.current:.2f} vs {r.mean:.2f} typical)",
                    ParagraphStyle("DriftDetail", parent=styles["Normal"],
                                   textColor=colors.red),
                ))
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
        for photo_path in find_run_photos(row["timestamp"], photo_dir=photo_dir):
            story.append(Spacer(1, 8))
            story.append(RLImage(photo_path, width=300, height=225))
        story.append(Spacer(1, 16))

    doc.build(story)
    print(f"Report saved to {output_path}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(build_job_summary(runner_type, rows, reports_by_row_id, any_flagged,
                                       evidence_artifact=evidence_artifact))

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
    parser.add_argument("--evidence-artifact", default=None,
                         help="name of the GH Actions evidence artifact for this run "
                              "(e.g. hil-mission-evidence-142) — omitted for sim reports, "
                              "which have no separate evidence artifact")
    args = parser.parse_args()
    generate_report(args.runner_type, args.scenarios, db_path=args.db,
                     output_path=args.report_path, config_path=args.config,
                     evidence_artifact=args.evidence_artifact)


if __name__ == "__main__":
    main()
