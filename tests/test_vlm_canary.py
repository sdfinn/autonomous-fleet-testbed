# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/vlm_canary.py (2026-07-30 design spec) — the fully decoupled,
log-only on-device VLM classification of Mission 2's red-ball reaction photo."""
import sqlite3
import sys
from types import SimpleNamespace

import pytest

import tools.vlm_canary as vlm_canary_module
from tools.vlm_canary import (DEFAULT_MODEL, classify_photo, find_vlm_canary_results,
                               init_db, log_vlm_canary_result, main)


def test_classify_photo_returns_model_answer(monkeypatch):
    def fake_chat(model, messages):
        assert model == DEFAULT_MODEL
        assert messages[0]['images'] == ['/tmp/fake.png']
        return SimpleNamespace(message=SimpleNamespace(content='a red ball'))
    monkeypatch.setattr(vlm_canary_module.ollama, 'chat', fake_chat)
    assert classify_photo('/tmp/fake.png') == 'a red ball'


def test_classify_photo_raises_friendly_error_when_model_not_pulled(monkeypatch):
    def fake_chat(model, messages):
        raise Exception("model 'moondream:1.8b' not found, try pulling it first")
    monkeypatch.setattr(vlm_canary_module.ollama, 'chat', fake_chat)
    with pytest.raises(RuntimeError, match="ollama pull"):
        classify_photo('/tmp/fake.png')


def test_classify_photo_raises_friendly_error_when_ollama_unreachable(monkeypatch):
    def fake_chat(model, messages):
        raise ConnectionError("Connection refused")
    monkeypatch.setattr(vlm_canary_module.ollama, 'chat', fake_chat)
    with pytest.raises(RuntimeError, match="ollama serve"):
        classify_photo('/tmp/fake.png')


def test_log_vlm_canary_result_writes_answer_row(tmp_path):
    db = str(tmp_path / "t.db")
    row_id = log_vlm_canary_result('red', '/tmp/fake.png', DEFAULT_MODEL,
                                    answer='a red ball', db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT run_context, photo_path, model_name, answer, error "
        "FROM vlm_canary_log WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row == ('red', '/tmp/fake.png', DEFAULT_MODEL, 'a red ball', None)


def test_log_vlm_canary_result_writes_error_row(tmp_path):
    db = str(tmp_path / "t.db")
    row_id = log_vlm_canary_result('red', '/tmp/fake.png', DEFAULT_MODEL,
                                    error='Ollama unreachable', db_path=db)
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT answer, error FROM vlm_canary_log WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row == (None, 'Ollama unreachable')


def test_find_vlm_canary_results_matches_exact_photo_path(tmp_path):
    db = str(tmp_path / "t.db")
    log_vlm_canary_result('red', '/tmp/a.png', DEFAULT_MODEL, answer='a red ball', db_path=db)
    log_vlm_canary_result('red', '/tmp/b.png', DEFAULT_MODEL, answer='a giraffe', db_path=db)
    results = find_vlm_canary_results(['/tmp/a.png', '/tmp/nonexistent.png'], db_path=db)
    assert len(results) == 1
    assert results[0]['photo_path'] == '/tmp/a.png'
    assert results[0]['answer'] == 'a red ball'


def test_find_vlm_canary_results_empty_list_returns_empty(tmp_path):
    db = str(tmp_path / "t.db")
    assert find_vlm_canary_results([], db_path=db) == []


def test_find_vlm_canary_results_table_missing_returns_empty_not_error(tmp_path):
    # init_db() never called against this path — the table genuinely doesn't exist
    # yet (e.g. the canary has never run on this machine). Must not raise.
    db = str(tmp_path / "never_initialized.db")
    assert find_vlm_canary_results(['/tmp/a.png'], db_path=db) == []


def test_main_logs_answer_on_success(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    monkeypatch.setattr(vlm_canary_module, 'DB_PATH', db)

    def fake_chat(model, messages):
        return SimpleNamespace(message=SimpleNamespace(content='a red ball'))
    monkeypatch.setattr(vlm_canary_module.ollama, 'chat', fake_chat)
    monkeypatch.setattr(sys, 'argv', ['vlm_canary', '/tmp/fake.png', 'red'])

    main()

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT answer, error FROM vlm_canary_log").fetchone()
    conn.close()
    assert row == ('a red ball', None)


def test_main_logs_error_on_failure_without_raising(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    monkeypatch.setattr(vlm_canary_module, 'DB_PATH', db)

    def fake_chat(model, messages):
        raise ConnectionError("Connection refused")
    monkeypatch.setattr(vlm_canary_module.ollama, 'chat', fake_chat)
    monkeypatch.setattr(sys, 'argv', ['vlm_canary', '/tmp/fake.png', 'red'])

    main()  # must not raise

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT answer, error FROM vlm_canary_log").fetchone()
    conn.close()
    assert row[0] is None
    assert 'ollama serve' in row[1]
