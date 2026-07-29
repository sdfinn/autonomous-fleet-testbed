# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Auto-log for tools.agentic_loop.diagnose() calls (2026-07-29 design).

System-driven writes only — every diagnosis gets logged the moment it runs, from either
the CLI or the dashboard, same lifecycle as tools.telemetry_logger.log_run(). No human
verdict columns here: this is NOT the (deferred, not built) user-feedback/scoring layer —
see docs/superpowers/specs/2026-07-29-ai-diagnosis-items-and-feedback-design.md for the
scope history. Two-table shape (ai_diagnoses / ai_diagnosis_items) mirrors the existing
runs/steps pattern in telemetry_logger.py.
"""
import json
import sqlite3
import time

from tools.telemetry_logger import DB_PATH


def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_diagnoses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT,
            run_id          INTEGER,
            backend         TEXT,
            model_name      TEXT,
            source          TEXT,
            prompt_text     TEXT,
            analysis_text   TEXT,
            conflict_notes  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_diagnosis_items (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnosis_id  INTEGER,
            item_index    INTEGER,
            tool_name     TEXT,
            item_input    TEXT,
            auto_verdict  TEXT,
            auto_notes    TEXT,
            FOREIGN KEY (diagnosis_id) REFERENCES ai_diagnoses(id)
        )
    """)
    _ensure_diagnosis_item_columns(conn)
    conn.commit()
    conn.close()


# 2026-07-29 third-round addition: 'source' ('submitted'|'extracted') and 'title'
# (best-effort label for extracted items, NULL for submitted ones) — additive
# migration, same pattern as telemetry_logger.py's RUNS_COLUMNS/_ensure_run_columns,
# since the table already existed (and had real rows) before this addition.
DIAGNOSIS_ITEM_COLUMNS = {
    "source": "TEXT",
    "title": "TEXT",
}


def _ensure_diagnosis_item_columns(conn):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(ai_diagnosis_items)").fetchall()}
    for name, col_type in DIAGNOSIS_ITEM_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE ai_diagnosis_items ADD COLUMN {name} {col_type}")


def log_diagnosis(*, backend, model_name, source, prompt_text, analysis_text,
                   items, conflict_notes=None, run_id=None, db_path: str = DB_PATH):
    """Insert one ai_diagnoses row plus one ai_diagnosis_items row per item.

    `items`: list of {'tool_name', 'input', 'auto_verdict', 'auto_notes', 'source',
    'title'} dicts, in display order (see
    tools.agentic_loop.evaluate_diagnosis_items — 'source' here is per-ITEM,
    'submitted' or 'extracted'; unrelated to this function's own `source` kwarg,
    which is per-DIAGNOSIS, 'cli' or 'dashboard'). `conflict_notes`: list of
    human-readable strings, or None. Returns the new ai_diagnoses.id.
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ai_diagnoses "
        "(created_at, run_id, backend, model_name, source, prompt_text, "
        "analysis_text, conflict_notes) VALUES (?,?,?,?,?,?,?,?)",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), run_id, backend, model_name, source,
         prompt_text, analysis_text,
         json.dumps(conflict_notes) if conflict_notes else None),
    )
    diagnosis_id = cur.lastrowid
    cur.executemany(
        "INSERT INTO ai_diagnosis_items "
        "(diagnosis_id, item_index, tool_name, item_input, auto_verdict, auto_notes, "
        "source, title) VALUES (?,?,?,?,?,?,?,?)",
        [(diagnosis_id, i, item["tool_name"], json.dumps(item["input"]),
          item["auto_verdict"], item.get("auto_notes"), item.get("source"),
          item.get("title"))
         for i, item in enumerate(items)],
    )
    conn.commit()
    conn.close()
    return diagnosis_id
