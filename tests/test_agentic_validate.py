# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Smoke test for tools/agentic_validate.py — confirms it runs end-to-end and prints
every case's name, with both backends mocked (no live Claude API key or live Ollama
server needed)."""
from tools import agentic_loop, agentic_validate


def test_agentic_validate_runs_end_to_end_with_mocked_backends(monkeypatch, capsys):
    def _fake_backend(prompt):
        return agentic_loop._DiagnosisResponse(content=[
            agentic_loop._ToolUseBlock(
                name='propose_nav_param_change',
                input={'param_path': 'x', 'proposed_value': '1', 'rationale': 'r'},
            )
        ])

    monkeypatch.setattr(agentic_loop, '_diagnose_claude', lambda prompt, **kw: _fake_backend(prompt))
    monkeypatch.setattr(agentic_loop, '_diagnose_ollama', lambda prompt, **kw: _fake_backend(prompt))

    agentic_validate.main()

    out = capsys.readouterr().out
    for case in agentic_validate.CASES:
        assert case['name'] in out
    assert out.count('propose_nav_param_change') == len(agentic_validate.CASES) * 2


def test_agentic_validate_prints_backend_error_instead_of_crashing(monkeypatch, capsys):
    def _raise_claude(prompt, **kw):
        raise RuntimeError('no API key')

    def _raise_ollama(prompt, **kw):
        raise RuntimeError('ollama serve')

    monkeypatch.setattr(agentic_loop, '_diagnose_claude', _raise_claude)
    monkeypatch.setattr(agentic_loop, '_diagnose_ollama', _raise_ollama)

    agentic_validate.main()  # must not raise

    out = capsys.readouterr().out
    assert 'ERROR: no API key' in out
    assert 'ERROR: ollama serve' in out
