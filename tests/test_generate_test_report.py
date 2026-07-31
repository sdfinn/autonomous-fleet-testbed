# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Focused tests for tools/generate_test_report.py's VLM canary surfacing (PDF +
console print) — added after the canary result was found MISSING from both the PDF
and the (confirmed-buggy) GitHub Job Summary, despite a real row already existing in
vlm_canary_log. The rest of this module has no test coverage yet (pre-existing gap,
out of scope here — this only covers the new canary-surfacing behavior)."""
import fitz  # PyMuPDF
from PIL import Image

import tools.generate_test_report as gtr_module
from tools.generate_test_report import generate_report
from tools.telemetry_logger import log_run
from tools.vlm_canary import log_vlm_canary_result


def _pdf_text(path):
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def test_generate_report_includes_vlm_canary_answer_in_pdf_and_console(
        monkeypatch, tmp_path, capsys):
    db = str(tmp_path / "t.db")
    log_run('mission2_red', steps=3, final_x=0.0, final_y=0.0, result='PASS',
            step_log=[], db_path=db, runner_type='local', sim_engine='gazebo')
    photo_path = str(tmp_path / "fake_reaction_red.png")
    Image.new('RGB', (4, 4)).save(photo_path)
    log_vlm_canary_result('red', photo_path, 'moondream:1.8b',
                           answer='a red ball in mid-air', db_path=db)

    # find_run_photos() would normally scan a real photo_dir for files within a time
    # window of the run's own timestamp — stubbed here to hand back the exact path the
    # canary row was logged against, so the join has a real key (RLImage below still
    # needs a real, openable image file, hence the tiny PNG written above).
    monkeypatch.setattr(gtr_module, 'find_run_photos', lambda *a, **k: [photo_path])

    out_path = generate_report(
        'local', ['mission2_red'], db_path=db,
        output_path=str(tmp_path / "report.pdf"),
    )

    text = _pdf_text(out_path)
    assert 'a red ball in mid-air' in text

    console_out = capsys.readouterr().out
    assert 'VLM canary' in console_out
    assert 'a red ball in mid-air' in console_out


def test_generate_report_does_not_cross_contaminate_photos_between_same_timestamp_rows(
        tmp_path):
    """Regression test for the real bug found 2026-07-31: mission2's 3 legs get judged
    in one tight loop with no meaningful delay, so they always share an identical
    %Y-%m-%dT%H:%M:%S timestamp — find_run_photos()'s ±180s time-window match then
    returned EVERY leg's photos (and VLM canary text) under EVERY scenario's PDF
    section. The `photos` telemetry column (this row's own exact list) fixes this.
    Deliberately does NOT stub find_run_photos — proves the real column-based path is
    what's used, not the time-window fallback. Two log_run() calls back-to-back land
    in the same wall-clock second in practice (1-second timestamp resolution),
    reproducing the real trigger without needing to force it artificially."""
    import json

    db = str(tmp_path / "t.db")
    yellow_photo = str(tmp_path / "mission2_reaction_yellow_1.png")
    red_photo = str(tmp_path / "mission2_reaction_red_1.png")
    Image.new('RGB', (4, 4)).save(yellow_photo)
    Image.new('RGB', (4, 4)).save(red_photo)

    log_run('mission2_yellow', steps=1, final_x=0.0, final_y=0.0, result='PASS',
            step_log=[], db_path=db, runner_type='local', sim_engine='gazebo',
            photos=json.dumps([yellow_photo]))
    log_run('mission2_red', steps=1, final_x=0.0, final_y=0.0, result='PASS',
            step_log=[], db_path=db, runner_type='local', sim_engine='gazebo',
            photos=json.dumps([red_photo]))
    log_vlm_canary_result('red', red_photo, 'moondream:1.8b',
                           answer='a red ball in mid-air', db_path=db)

    out_path = generate_report(
        'local', ['mission2_yellow', 'mission2_red'], db_path=db,
        output_path=str(tmp_path / "report.pdf"),
    )

    text = _pdf_text(out_path)
    red_section_start = text.index('mission2_red')
    yellow_section = text[:red_section_start]
    red_section = text[red_section_start:]
    assert 'a red ball in mid-air' not in yellow_section
    assert red_section.count('a red ball in mid-air') == 1


def test_row_photos_prefers_stored_column_over_time_window(monkeypatch):
    from tools.generate_test_report import _row_photos
    monkeypatch.setattr(gtr_module, 'find_run_photos',
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError('must not fall back when photos column is set')))
    row = {'photos': '["/tmp/a.png", "/tmp/b.png"]', 'timestamp': '2026-07-31T08:00:00'}
    assert _row_photos(row) == ['/tmp/a.png', '/tmp/b.png']


def test_row_photos_falls_back_to_time_window_when_column_empty(monkeypatch):
    from tools.generate_test_report import _row_photos
    monkeypatch.setattr(gtr_module, 'find_run_photos', lambda ts, photo_dir: ['/tmp/fallback.png'])
    row = {'photos': None, 'timestamp': '2026-07-31T08:00:00'}
    assert _row_photos(row) == ['/tmp/fallback.png']


def test_generate_report_omits_canary_section_when_no_result_logged(
        monkeypatch, tmp_path, capsys):
    db = str(tmp_path / "t.db")
    log_run('mission2_no_ball', steps=3, final_x=0.0, final_y=0.0, result='PASS',
            step_log=[], db_path=db, runner_type='local', sim_engine='gazebo')
    monkeypatch.setattr(gtr_module, 'find_run_photos', lambda *a, **k: [])

    out_path = generate_report(
        'local', ['mission2_no_ball'], db_path=db,
        output_path=str(tmp_path / "report.pdf"),
    )

    text = _pdf_text(out_path)
    assert 'VLM canary' not in text
    assert 'VLM canary' not in capsys.readouterr().out
