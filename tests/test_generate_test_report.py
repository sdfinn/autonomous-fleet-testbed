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
