# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/diagnosis_log.py — auto-logging of diagnose() calls (2026-07-29).
System-driven writes only (no human verdict columns) — see
docs/superpowers/specs/2026-07-29-ai-diagnosis-items-and-feedback-design.md."""
import json
import sqlite3

from tools.diagnosis_log import init_db, log_diagnosis


def test_init_db_creates_ai_diagnoses_table(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    tables = {r[0] for r in sqlite3.connect(db).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ai_diagnoses" in tables


def test_init_db_creates_ai_diagnosis_items_table(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    tables = {r[0] for r in sqlite3.connect(db).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ai_diagnosis_items" in tables


def test_init_db_sets_wal_mode_on_fresh_file(tmp_path):
    db = str(tmp_path / "fresh.db")
    init_db(db)
    mode = sqlite3.connect(db).execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_init_db_is_idempotent(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    init_db(db)  # must not raise on a second call


def _sample_items():
    return [
        {"tool_name": "propose_nav_param_change",
         "input": {"param_path": "controller_server.rotate_to_heading_angular_vel",
                    "current_value": "0.5", "proposed_value": "0.6", "rationale": "r"},
         "auto_verdict": "good", "auto_notes": None},
        {"tool_name": "propose_mission_plan",
         "input": {"mission_description": "d", "goals": [], "rationale": "r"},
         "auto_verdict": "unverified", "auto_notes": None},
    ]


def test_log_diagnosis_returns_new_diagnosis_id(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="qwen2.5:14b-instruct", source="dashboard",
        prompt_text="p", analysis_text="a", items=_sample_items(), db_path=db,
    )
    assert isinstance(diagnosis_id, int)


def test_log_diagnosis_inserts_one_diagnoses_row(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="qwen2.5:14b-instruct", source="dashboard",
        prompt_text="the full prompt", analysis_text="the analysis text",
        items=_sample_items(), db_path=db,
    )
    row = sqlite3.connect(db).execute(
        "SELECT backend, model_name, source, prompt_text, analysis_text FROM "
        "ai_diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    assert row == ("ollama", "qwen2.5:14b-instruct", "dashboard",
                    "the full prompt", "the analysis text")


def test_log_diagnosis_inserts_one_item_row_per_item_in_order(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=_sample_items(), db_path=db,
    )
    rows = sqlite3.connect(db).execute(
        "SELECT item_index, tool_name, auto_verdict FROM ai_diagnosis_items "
        "WHERE diagnosis_id = ? ORDER BY item_index", (diagnosis_id,)).fetchall()
    assert rows == [
        (0, "propose_nav_param_change", "good"),
        (1, "propose_mission_plan", "unverified"),
    ]


def test_log_diagnosis_stores_item_input_as_json(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=_sample_items(), db_path=db,
    )
    row = sqlite3.connect(db).execute(
        "SELECT item_input FROM ai_diagnosis_items WHERE diagnosis_id = ? "
        "AND item_index = 0", (diagnosis_id,)).fetchone()
    assert json.loads(row[0])["proposed_value"] == "0.6"


def test_log_diagnosis_stores_auto_notes(tmp_path):
    db = str(tmp_path / "t.db")
    items = [{"tool_name": "propose_nav_param_change",
              "input": {"param_path": "x.scan_period", "current_value": "0.1",
                         "proposed_value": "0.05", "rationale": "r"},
              "auto_verdict": "bad",
              "auto_notes": "param not found anywhere in the real config"}]
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=items, db_path=db,
    )
    row = sqlite3.connect(db).execute(
        "SELECT auto_notes FROM ai_diagnosis_items WHERE diagnosis_id = ?",
        (diagnosis_id,)).fetchone()
    assert row[0] == "param not found anywhere in the real config"


def test_log_diagnosis_handles_empty_items_list(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=[], db_path=db,
    )
    count = sqlite3.connect(db).execute(
        "SELECT COUNT(*) FROM ai_diagnosis_items WHERE diagnosis_id = ?",
        (diagnosis_id,)).fetchone()[0]
    assert count == 0


def test_log_diagnosis_run_id_defaults_null(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=[], db_path=db,
    )
    row = sqlite3.connect(db).execute(
        "SELECT run_id FROM ai_diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    assert row[0] is None


def test_log_diagnosis_stores_run_id_when_given(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=[], run_id=483, db_path=db,
    )
    row = sqlite3.connect(db).execute(
        "SELECT run_id FROM ai_diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    assert row[0] == 483


def test_log_diagnosis_conflict_notes_defaults_null(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=[], db_path=db,
    )
    row = sqlite3.connect(db).execute(
        "SELECT conflict_notes FROM ai_diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    assert row[0] is None


def test_log_diagnosis_stores_conflict_notes_as_json(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=[], db_path=db,
        conflict_notes=["item 0 and item 2 disagree on rotate_to_heading_angular_vel"],
    )
    row = sqlite3.connect(db).execute(
        "SELECT conflict_notes FROM ai_diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    assert json.loads(row[0]) == ["item 0 and item 2 disagree on rotate_to_heading_angular_vel"]


def test_log_diagnosis_created_at_is_set(tmp_path):
    db = str(tmp_path / "t.db")
    diagnosis_id = log_diagnosis(
        backend="ollama", model_name="m", source="cli", prompt_text="p",
        analysis_text="a", items=[], db_path=db,
    )
    row = sqlite3.connect(db).execute(
        "SELECT created_at FROM ai_diagnoses WHERE id = ?", (diagnosis_id,)).fetchone()
    assert row[0] is not None and len(row[0]) > 0
