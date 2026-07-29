# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/agentic_loop.py's diagnose() prompt-building — no real
Anthropic API calls (client.messages.create is monkeypatched in every test)."""
import json
import sqlite3

import pytest

from tools import agentic_loop
from tools.telemetry_logger import init_db, log_run


class _FakeResponse:
    content = []


def test_load_nav2_params_text_reads_the_real_file():
    text = agentic_loop.load_nav2_params_text()
    assert "inflation_radius: 0.25" in text


def test_diagnose_injects_real_nav2_params_into_prompt(monkeypatch, tmp_path):
    """Bug fix: diagnose() must inject the REAL nav2_params.yaml content into the
    prompt sent to Claude, so current_value comes from the actual file, not an LLM
    guess (caught wrong once: claimed 0.55 for inflation_radius, real value 0.25)."""
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    captured = {}

    def _fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS",
                "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude')

    prompt_text = captured["messages"][0]["content"]
    assert "inflation_radius: 0.25" in prompt_text


def test_diagnose_includes_trend_context_when_given(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    captured = {}

    def _fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS",
                "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude',
                           trend_context="  nav_success_rate: 3/20 runs flagged")

    prompt_text = captured["messages"][0]["content"]
    assert "nav_success_rate: 3/20 runs flagged" in prompt_text


def test_diagnose_omits_trend_section_when_not_given(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    captured = {}

    def _fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS",
                "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude')

    prompt_text = captured["messages"][0]["content"]
    assert "Big-picture trend context" not in prompt_text


def test_diagnose_prompt_requires_every_recommendation_as_a_tool_call(monkeypatch, tmp_path):
    """2026-07-29 design: recommendations must come in as structured tool calls, not
    buried in free-text prose (the exact failure mode that motivated
    evaluate_diagnosis_items) — the prompt must say so explicitly."""
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    captured = {}

    def _fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS",
                "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude')

    prompt_text = captured["messages"][0]["content"]
    assert "own tool call" in prompt_text
    assert "as many tools as you have recommendations" in prompt_text.lower()


def test_diagnose_auto_logs_a_diagnosis_row(monkeypatch, tmp_path):
    """2026-07-29 design: every diagnose() call auto-logs, no button, no separate
    save action — same lifecycle as telemetry_logger.log_run()."""
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    fake_response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(text='some analysis'),
        agentic_loop._ToolUseBlock(name='propose_mission_plan',
                                    input={'mission_description': 'd', 'goals': [], 'rationale': 'r'}),
    ])
    monkeypatch.setattr(agentic_loop.client.messages, "create", lambda **kw: fake_response)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude')

    row = sqlite3.connect(db).execute(
        "SELECT backend, model_name, source, run_id, analysis_text FROM ai_diagnoses "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row == ('claude', 'claude-sonnet-5', 'cli', run_id, 'some analysis')

    item_row = sqlite3.connect(db).execute(
        "SELECT tool_name, auto_verdict FROM ai_diagnosis_items "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert item_row == ('propose_mission_plan', 'unverified')


def test_diagnose_source_defaults_to_cli(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    monkeypatch.setattr(agentic_loop.client.messages, "create", lambda **kw: _FakeResponse())

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude')

    row = sqlite3.connect(db).execute(
        "SELECT source FROM ai_diagnoses ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == 'cli'


def test_diagnose_source_param_is_logged(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    monkeypatch.setattr(agentic_loop.client.messages, "create", lambda **kw: _FakeResponse())

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude', source='dashboard')

    row = sqlite3.connect(db).execute(
        "SELECT source FROM ai_diagnoses ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == 'dashboard'


def test_diagnose_logs_prompt_text(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    monkeypatch.setattr(agentic_loop.client.messages, "create", lambda **kw: _FakeResponse())

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude')

    row = sqlite3.connect(db).execute(
        "SELECT prompt_text FROM ai_diagnoses ORDER BY id DESC LIMIT 1").fetchone()
    assert 'inflation_radius: 0.25' in row[0]


def test_diagnose_logs_ollama_model_name(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    monkeypatch.setattr(agentic_loop, "_diagnose_ollama",
                         lambda prompt, **kw: agentic_loop._DiagnosisResponse(content=[]))

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='ollama')

    row = sqlite3.connect(db).execute(
        "SELECT backend, model_name FROM ai_diagnoses ORDER BY id DESC LIMIT 1").fetchone()
    assert row == ('ollama', agentic_loop.OLLAMA_MODEL)


def test_diagnose_logs_prose_only_recommendations_as_extracted_items(monkeypatch, tmp_path):
    """Locks in the wiring, not just the unit — reproduces the exact live incident:
    prose promises 2 param changes, 0 real items submitted for either. Third-round
    design: these are no longer just a conflict_notes count, they're real logged
    items with source='extracted'."""
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    fake_response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(
            text='propose_nav_param_change(a:b:1)\npropose_nav_param_change(c:d:2)'),
        agentic_loop._ToolUseBlock(name='propose_mission_plan',
                                    input={'mission_description': 'd', 'goals': [], 'rationale': 'r'}),
    ])
    monkeypatch.setattr(agentic_loop.client.messages, "create", lambda **kw: fake_response)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='claude')

    rows = sqlite3.connect(db).execute(
        "SELECT tool_name, source FROM ai_diagnosis_items ORDER BY item_index").fetchall()
    assert rows == [
        ('propose_mission_plan', 'submitted'),
        ('propose_nav_param_change', 'extracted'),
        ('propose_nav_param_change', 'extracted'),
    ]


def test_to_ollama_tools_converts_anthropic_shape_to_function_calling_shape():
    ollama_tools = agentic_loop._to_ollama_tools(agentic_loop.TOOLS)

    assert len(ollama_tools) == len(agentic_loop.TOOLS)
    first = ollama_tools[0]
    assert first["type"] == "function"
    assert first["function"]["name"] == "propose_nav_param_change"
    assert first["function"]["description"] == agentic_loop.TOOLS[0]["description"]
    assert first["function"]["parameters"] == agentic_loop.TOOLS[0]["input_schema"]


def test_to_ollama_tools_does_not_mutate_the_original_tools_list():
    import copy
    original = copy.deepcopy(agentic_loop.TOOLS)

    agentic_loop._to_ollama_tools(agentic_loop.TOOLS)

    assert agentic_loop.TOOLS == original


class _FakeOllamaFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeOllamaToolCall:
    def __init__(self, name, arguments):
        self.function = _FakeOllamaFunction(name, arguments)


class _FakeOllamaMessage:
    def __init__(self, content='', tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeOllamaChatResponse:
    def __init__(self, message):
        self.message = message


def test_diagnose_ollama_passes_tools_by_default(monkeypatch):
    captured = {}
    fake_response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._ToolUseBlock(name='propose_mission_plan',
                                    input={'mission_description': 'd', 'goals': [], 'rationale': 'r'}),
    ])

    def _fake_chat(**kwargs):
        captured.update(kwargs)
        return type('R', (), {'message': type('M', (), {
            'content': None, 'tool_calls': [
                type('C', (), {'function': type('F', (), {
                    'name': 'propose_mission_plan',
                    'arguments': {'mission_description': 'd', 'goals': [], 'rationale': 'r'},
                })()})()],
        })()})()

    monkeypatch.setattr(agentic_loop.ollama, 'chat', _fake_chat)

    agentic_loop._diagnose_ollama('irrelevant prompt')

    assert 'tools' in captured


def test_diagnose_ollama_omits_tools_when_offer_tools_false(monkeypatch):
    """2026-07-29, 4th-round simplification: the dashboard no longer wants the model
    offered any tools at all — plain free text only, no native tool-calling attempt,
    no JSON-fallback retry (nothing to retry from since no tool call was ever
    possible)."""
    captured = {}

    def _fake_chat(**kwargs):
        captured.update(kwargs)
        return type('R', (), {'message': type('M', (), {'content': 'just analysis text'})()})()

    monkeypatch.setattr(agentic_loop.ollama, 'chat', _fake_chat)
    monkeypatch.setattr(agentic_loop, '_diagnose_ollama_json_fallback',
                         lambda *a, **kw: (_ for _ in ()).throw(
                             AssertionError('fallback must not be called when offer_tools=False')))

    result = agentic_loop._diagnose_ollama('irrelevant prompt', offer_tools=False)

    assert 'tools' not in captured
    assert result.content[0].type == 'text'
    assert result.content[0].text == 'just analysis text'


def test_diagnose_ollama_returns_tool_use_block(monkeypatch):
    fake_call = _FakeOllamaToolCall(
        'propose_nav_param_change',
        {'param_path': 'local_costmap.inflation_layer.inflation_radius',
         'current_value': '0.25', 'proposed_value': '0.35',
         'rationale': 'collisions trending up'},
    )
    fake_response = _FakeOllamaChatResponse(_FakeOllamaMessage(tool_calls=[fake_call]))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    result = agentic_loop._diagnose_ollama('irrelevant prompt text')

    assert len(result.content) == 1
    block = result.content[0]
    assert block.type == 'tool_use'
    assert block.name == 'propose_nav_param_change'
    assert block.input['proposed_value'] == '0.35'


def test_diagnose_ollama_parses_json_string_arguments(monkeypatch):
    """Some Ollama models/versions may return tool arguments as a JSON string
    rather than an already-parsed dict — handle both without guessing which."""
    fake_call = _FakeOllamaToolCall(
        'propose_nav_param_change',
        '{"param_path": "x", "proposed_value": "1", "rationale": "r"}',
    )
    fake_response = _FakeOllamaChatResponse(_FakeOllamaMessage(tool_calls=[fake_call]))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    result = agentic_loop._diagnose_ollama('irrelevant prompt text')

    assert result.content[0].input['param_path'] == 'x'


def test_diagnose_ollama_includes_text_block_when_model_writes_analysis(monkeypatch):
    fake_call = _FakeOllamaToolCall('propose_mission_plan',
                                     {'mission_description': 'd', 'goals': [], 'rationale': 'r'})
    fake_response = _FakeOllamaChatResponse(
        _FakeOllamaMessage(content='Looking at the drift report...', tool_calls=[fake_call]))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    result = agentic_loop._diagnose_ollama('irrelevant prompt text')

    types = [b.type for b in result.content]
    assert types == ['text', 'tool_use']
    assert result.content[0].text == 'Looking at the drift report...'


def test_diagnose_ollama_raises_when_no_tool_call_returned(monkeypatch):
    """Both the native attempt AND the JSON-prompted fallback fail to produce a
    usable proposal here (fallback's json.loads on free-text analysis raises) —
    covers the case where the fallback doesn't rescue a truly non-cooperative
    response, not just the length-triggered failure mode below."""
    fake_response = _FakeOllamaChatResponse(
        _FakeOllamaMessage(content='just some analysis text, no proposal'))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    with pytest.raises(RuntimeError, match='did not propose a tool call'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_ollama_falls_back_to_json_prompting_when_no_tool_call_returned(monkeypatch):
    """Root cause fix, 2026-07-29: qwen2.5:14b-instruct's native tool-calling
    reliably invokes a tool for short prompts but silently degrades to free-text-only
    analysis once the real diagnose() prompt's full nav2_params.yaml injection
    (~16K chars) is included — confirmed by direct reproduction against the live
    model, not assumed. When native tool-calling returns no tool_calls, retry once
    with Ollama's format='json' structured-output contract instead of raising
    immediately (the parked 'Approach C' fallback from the 2026-07-28 design spec)."""
    call_count = {'n': 0}

    def _fake_chat(**kwargs):
        call_count['n'] += 1
        if call_count['n'] == 1:
            assert 'tools' in kwargs
            return _FakeOllamaChatResponse(
                _FakeOllamaMessage(content='lots of free-text analysis, no tool call'))
        assert kwargs.get('format') == 'json'
        assert 'tools' not in kwargs
        json_body = ('{"tool": "propose_nav_param_change", '
                     '"input": {"param_path": "x", "proposed_value": "1", "rationale": "r"}}')
        return _FakeOllamaChatResponse(_FakeOllamaMessage(content=json_body))

    monkeypatch.setattr(agentic_loop.ollama, 'chat', _fake_chat)

    result = agentic_loop._diagnose_ollama('irrelevant prompt text')

    assert call_count['n'] == 2
    tool_blocks = [b for b in result.content if b.type == 'tool_use']
    assert len(tool_blocks) == 1
    assert tool_blocks[0].name == 'propose_nav_param_change'
    assert tool_blocks[0].input['proposed_value'] == '1'


def test_diagnose_ollama_json_fallback_raises_on_unknown_tool_name(monkeypatch):
    call_count = {'n': 0}

    def _fake_chat(**kwargs):
        call_count['n'] += 1
        if call_count['n'] == 1:
            return _FakeOllamaChatResponse(_FakeOllamaMessage(content='no tool call here'))
        return _FakeOllamaChatResponse(
            _FakeOllamaMessage(content='{"tool": "not_a_real_tool", "input": {}}'))

    monkeypatch.setattr(agentic_loop.ollama, 'chat', _fake_chat)

    with pytest.raises(RuntimeError, match='unknown tool'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_ollama_json_fallback_raises_on_missing_required_argument(monkeypatch):
    call_count = {'n': 0}

    def _fake_chat(**kwargs):
        call_count['n'] += 1
        if call_count['n'] == 1:
            return _FakeOllamaChatResponse(_FakeOllamaMessage(content='no tool call here'))
        return _FakeOllamaChatResponse(_FakeOllamaMessage(
            content='{"tool": "propose_nav_param_change", "input": {"param_path": "x"}}'))

    monkeypatch.setattr(agentic_loop.ollama, 'chat', _fake_chat)

    with pytest.raises(RuntimeError, match='omitted required argument'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_ollama_raises_actionable_error_when_unreachable(monkeypatch):
    def _fake_chat(**kwargs):
        raise ConnectionRefusedError('[Errno 111] Connection refused')

    monkeypatch.setattr(agentic_loop.ollama, 'chat', _fake_chat)

    with pytest.raises(RuntimeError, match='ollama serve'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_ollama_raises_actionable_error_when_model_not_pulled(monkeypatch):
    def _fake_chat(**kwargs):
        raise Exception(f'model "{agentic_loop.OLLAMA_MODEL}" not found, try pulling it first')

    monkeypatch.setattr(agentic_loop.ollama, 'chat', _fake_chat)

    with pytest.raises(RuntimeError, match='ollama pull'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_ollama_raises_actionable_error_on_malformed_json_arguments(monkeypatch):
    fake_call = _FakeOllamaToolCall('propose_nav_param_change', '{not valid json')
    fake_response = _FakeOllamaChatResponse(_FakeOllamaMessage(tool_calls=[fake_call]))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    with pytest.raises(RuntimeError, match='malformed tool-call arguments'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_ollama_raises_actionable_error_on_unknown_tool_name(monkeypatch):
    fake_call = _FakeOllamaToolCall('not_a_real_tool', {'x': 1})
    fake_response = _FakeOllamaChatResponse(_FakeOllamaMessage(tool_calls=[fake_call]))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    with pytest.raises(RuntimeError, match='unknown tool'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_ollama_raises_actionable_error_on_non_dict_arguments(monkeypatch):
    fake_call = _FakeOllamaToolCall('propose_nav_param_change', ['not', 'a', 'dict'])
    fake_response = _FakeOllamaChatResponse(_FakeOllamaMessage(tool_calls=[fake_call]))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    with pytest.raises(RuntimeError, match='non-object tool-call arguments'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_ollama_raises_actionable_error_on_missing_required_argument(monkeypatch):
    fake_call = _FakeOllamaToolCall('propose_nav_param_change', {'param_path': 'x'})
    fake_response = _FakeOllamaChatResponse(_FakeOllamaMessage(tool_calls=[fake_call]))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    with pytest.raises(RuntimeError, match='omitted required argument'):
        agentic_loop._diagnose_ollama('irrelevant prompt text')


def test_diagnose_dispatches_to_ollama_backend_when_requested(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    captured = {}

    def _fake_diagnose_ollama(prompt, **kw):
        captured["prompt"] = prompt
        return "sentinel-ollama-response"

    monkeypatch.setattr(agentic_loop, "_diagnose_ollama", _fake_diagnose_ollama)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    result = agentic_loop.diagnose(run_data, db_path=db, backend="ollama")

    assert result == "sentinel-ollama-response"
    assert "inflation_radius: 0.25" in captured["prompt"]


def test_diagnose_defaults_to_ollama_backend_when_env_var_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENTIC_BACKEND", raising=False)
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    monkeypatch.setattr(agentic_loop, "_diagnose_ollama",
                         lambda prompt, **kw: "sentinel-ollama-default")

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    result = agentic_loop.diagnose(run_data, db_path=db)  # no backend= given

    assert result == "sentinel-ollama-default"


def test_diagnose_reads_backend_from_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_BACKEND", "ollama")
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    monkeypatch.setattr(agentic_loop, "_diagnose_ollama", lambda prompt, **kw: "sentinel")

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    result = agentic_loop.diagnose(run_data, db_path=db)

    assert result == "sentinel"


def test_diagnose_explicit_backend_param_overrides_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_BACKEND", "ollama")
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    monkeypatch.setattr(agentic_loop.client.messages, "create", lambda **kw: _FakeResponse())

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    result = agentic_loop.diagnose(run_data, db_path=db, backend="claude")

    assert isinstance(result, _FakeResponse)


def test_diagnose_claude_passes_tools_by_default(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    captured = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)
    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend="claude")

    assert 'tools' in captured
    assert captured['tools'] == agentic_loop.TOOLS


def test_diagnose_omits_tools_when_offer_tools_false(monkeypatch, tmp_path):
    """2026-07-29, 4th-round simplification: the dashboard opts out of offering the
    model any tools at all — plain free text only. The CLI's own call is unaffected
    (offer_tools defaults to True, unchanged)."""
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    captured = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)
    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend="claude", offer_tools=False)

    assert 'tools' not in captured


def test_diagnose_offer_tools_defaults_to_true(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    captured = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)
    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend="claude")  # offer_tools omitted

    assert 'tools' in captured


def test_evaluate_diagnosis_items_flags_value_mismatch_as_bad():
    """Regression fixture for the Session 17 Piece 5 incident class: Claude once
    claimed inflation_radius=0.55 when the real value was 0.25. Exercises the same
    shape against a real, currently-tuned param (rotate_to_heading_angular_vel, real
    value 0.5 — see the Session 16 Task 9e comment in nav2_params.yaml)."""
    fake_call = agentic_loop._ToolUseBlock(
        name='propose_nav_param_change',
        input={'param_path': 'controller_server.rotate_to_heading_angular_vel',
               'current_value': '1.2', 'proposed_value': '1.8', 'rationale': 'r'},
    )
    response = agentic_loop._DiagnosisResponse(content=[fake_call])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert len(items) == 1
    assert items[0]['auto_verdict'] == 'bad'
    assert 'rotate_to_heading_angular_vel' in items[0]['auto_notes']
    assert '1.2' in items[0]['auto_notes']
    assert '0.5' in items[0]['auto_notes']


def test_evaluate_diagnosis_items_marks_value_match_as_good():
    fake_call = agentic_loop._ToolUseBlock(
        name='propose_nav_param_change',
        input={'param_path': 'controller_server.rotate_to_heading_angular_vel',
               'current_value': '0.5', 'proposed_value': '0.6', 'rationale': 'r'},
    )
    response = agentic_loop._DiagnosisResponse(content=[fake_call])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'good'
    assert items[0]['auto_notes'] is None


def test_evaluate_diagnosis_items_treats_numeric_equivalent_values_as_good():
    fake_call = agentic_loop._ToolUseBlock(
        name='propose_nav_param_change',
        input={'param_path': 'controller_server.rotate_to_heading_angular_vel',
               'current_value': '0.50', 'proposed_value': '0.6', 'rationale': 'r'},
    )
    response = agentic_loop._DiagnosisResponse(content=[fake_call])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'good'


def test_evaluate_diagnosis_items_flags_param_not_found_as_bad():
    """Regression fixture for the 2026-07-29 incident: the local model invented
    `scan_period` in a nonexistent `robot_description.yaml` — no such param exists
    anywhere in the real nav2_params.yaml."""
    fake_call = agentic_loop._ToolUseBlock(
        name='propose_nav_param_change',
        input={'param_path': 'lidar.scan_period', 'current_value': '0.1',
               'proposed_value': '0.05', 'rationale': 'r'},
    )
    response = agentic_loop._DiagnosisResponse(content=[fake_call])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'bad'
    assert 'scan_period' in items[0]['auto_notes']
    assert 'not found' in items[0]['auto_notes']


def test_evaluate_diagnosis_items_marks_no_current_value_claim_as_good():
    fake_call = agentic_loop._ToolUseBlock(
        name='propose_nav_param_change',
        input={'param_path': 'x.inflation_radius', 'proposed_value': '0.3', 'rationale': 'r'},
    )
    response = agentic_loop._DiagnosisResponse(content=[fake_call])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'good'


def test_evaluate_diagnosis_items_flags_nonexistent_param_bad_even_without_current_value():
    """2026-07-29, third-round fix: a missing current_value used to short-circuit
    straight to 'good' WITHOUT checking whether the param itself is real — meaning a
    fabricated param with no current_value claim was invisible to the guardrail. Most
    real-world prose recommendations never state a current_value at all, so this was
    silently disabling the check almost every time. Now checks existence regardless;
    only the value-match check is skipped when there's no current_value to compare."""
    fake_call = agentic_loop._ToolUseBlock(
        name='propose_nav_param_change',
        input={'param_path': 'x.scan_period', 'proposed_value': '0.05', 'rationale': 'r'},
    )
    response = agentic_loop._DiagnosisResponse(content=[fake_call])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'bad'
    assert 'scan_period' in items[0]['auto_notes']


def test_evaluate_diagnosis_items_marks_other_tools_as_unverified():
    fake_call = agentic_loop._ToolUseBlock(
        name='propose_mission_plan',
        input={'mission_description': 'd', 'goals': [], 'rationale': 'r'},
    )
    response = agentic_loop._DiagnosisResponse(content=[fake_call])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'unverified'
    assert items[0]['auto_notes'] is None


def test_evaluate_diagnosis_items_ignores_text_blocks():
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(text='some analysis'),
        agentic_loop._ToolUseBlock(name='propose_mission_plan',
                                    input={'mission_description': 'd', 'goals': [], 'rationale': 'r'}),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert len(items) == 1
    assert items[0]['tool_name'] == 'propose_mission_plan'


def test_evaluate_diagnosis_items_returns_items_in_order():
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._ToolUseBlock(name='propose_mission_plan',
                                    input={'mission_description': 'a', 'goals': [], 'rationale': 'r'}),
        agentic_loop._ToolUseBlock(name='generate_world_variant',
                                    input={'variant_name': 'b', 'obstacle_layout': [], 'rationale': 'r'}),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert [i['tool_name'] for i in items] == ['propose_mission_plan', 'generate_world_variant']


def test_evaluate_diagnosis_items_works_with_duck_typed_anthropic_style_blocks():
    """Must work for BOTH backends via duck typing (type/name/input attributes), not
    just Ollama's normalized _ToolUseBlock — this exact bug class (inflation_radius=
    0.55) was originally a CLAUDE hallucination, Session 17 Piece 5."""
    class _FakeAnthropicToolUseBlock:
        type = 'tool_use'
        name = 'propose_nav_param_change'
        input = {'param_path': 'x.rotate_to_heading_angular_vel', 'current_value': '99',
                 'proposed_value': '1.0', 'rationale': 'r'}

    class _FakeAnthropicResponse:
        content = [_FakeAnthropicToolUseBlock()]

    items = agentic_loop.evaluate_diagnosis_items(_FakeAnthropicResponse())

    assert items[0]['auto_verdict'] == 'bad'
    assert '99' in items[0]['auto_notes']


def test_evaluate_diagnosis_items_detects_conflict_between_two_items():
    """The 2026-07-29 ask: when the AI's own recommendations disagree with each other,
    say so. Two propose_nav_param_change items targeting the same leaf param
    (rotate_to_heading_angular_vel) with different proposed_values — matched by leaf
    name since the model may not write identical full param_path strings."""
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._ToolUseBlock(
            name='propose_nav_param_change',
            input={'param_path': 'a.rotate_to_heading_angular_vel',
                   'proposed_value': '1.2', 'rationale': 'r1'}),
        agentic_loop._ToolUseBlock(
            name='propose_nav_param_change',
            input={'param_path': 'b.rotate_to_heading_angular_vel',
                   'proposed_value': '0.3', 'rationale': 'r2'}),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'conflict'
    assert items[1]['auto_verdict'] == 'conflict'
    assert '1' in items[0]['auto_notes']  # mentions the conflicting sibling item


def test_evaluate_diagnosis_items_no_conflict_when_items_agree():
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._ToolUseBlock(
            name='propose_nav_param_change',
            input={'param_path': 'a.rotate_to_heading_angular_vel',
                   'proposed_value': '1.2', 'rationale': 'r1'}),
        agentic_loop._ToolUseBlock(
            name='propose_nav_param_change',
            input={'param_path': 'b.rotate_to_heading_angular_vel',
                   'proposed_value': '1.2', 'rationale': 'r2'}),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'good'
    assert items[1]['auto_verdict'] == 'good'


def test_evaluate_diagnosis_items_bad_fact_check_takes_priority_over_conflict():
    """Two items disagree with each other AND both fail the fact check (a fabricated
    param) — 'bad' is the more objective, more important finding, so it wins over
    'conflict' in the verdict label."""
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._ToolUseBlock(
            name='propose_nav_param_change',
            input={'param_path': 'a.scan_period', 'current_value': '0.1',
                   'proposed_value': '0.05', 'rationale': 'r1'}),
        agentic_loop._ToolUseBlock(
            name='propose_nav_param_change',
            input={'param_path': 'b.scan_period', 'current_value': '0.1',
                   'proposed_value': '0.02', 'rationale': 'r2'}),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['auto_verdict'] == 'bad'
    assert items[1]['auto_verdict'] == 'bad'


_REAL_KWARGS_STYLE_ANALYSIS_TEXT = """Recommendations
Improve Odometry Frequency

propose_nav_param_change(
    component="local_costmap",
    parameter="update_frequency",
    new_value=10.0,
)

Enhance Camera Performance

propose_nav_param_change(
    component="camera_interface",
    parameter="image_transport",
    new_value="compressed"
)

Create More Challenging Missions

propose_mission_plan(
    mission=[
        "visit the bedroom_goal",
        "then go to the desk",
        "return to home_base"
    ]
)"""

_REAL_COLON_STYLE_ANALYSIS_TEXT = (
    'propose_nav_param_change(local_costmap:robot_radius:0.237)\n'
    'propose_nav_param_change(global_costmap:inflation_layer:inflation_radius:0.25)\n'
    'propose_nav_param_change(local_costmap:inflation_layer:inflation_radius:0.20)\n'
    'propose_mission_plan(home_base hallway_west bedroom_goal home_base)'
)


def test_extract_prose_recommendations_returns_empty_for_no_text():
    assert agentic_loop.extract_prose_recommendations(None) == []
    assert agentic_loop.extract_prose_recommendations('') == []


def test_extract_prose_recommendations_returns_empty_when_no_tool_calls_written():
    assert agentic_loop.extract_prose_recommendations('just some plain analysis text') == []


def test_extract_prose_recommendations_finds_all_calls_in_real_kwargs_style_text():
    items = agentic_loop.extract_prose_recommendations(_REAL_KWARGS_STYLE_ANALYSIS_TEXT)

    assert [i['tool_name'] for i in items] == [
        'propose_nav_param_change', 'propose_nav_param_change', 'propose_mission_plan',
    ]


def test_extract_prose_recommendations_pulls_nearby_title():
    items = agentic_loop.extract_prose_recommendations(_REAL_KWARGS_STYLE_ANALYSIS_TEXT)

    assert items[0]['title'] == 'Improve Odometry Frequency'
    assert items[1]['title'] == 'Enhance Camera Performance'
    assert items[2]['title'] == 'Create More Challenging Missions'


def test_extract_prose_recommendations_title_skips_markdown_code_fence():
    """Live bug, 2026-07-29: the model sometimes wraps its pseudo-call in a
    ```python fence — the naive 'nearest preceding line' heuristic grabbed the
    fence marker itself ('```python') as the title. Must look past fence lines to
    find a real title, or fall back to None rather than show junk."""
    text = (
        'Optimize Odometry Update Rate\n'
        '```python\n'
        'propose_nav_param_change(\n'
        '    parameter="update_frequency",\n'
        '    new_value=10.0,\n'
        ')\n'
        '```\n'
    )
    items = agentic_loop.extract_prose_recommendations(text)

    assert items[0]['title'] == 'Optimize Odometry Update Rate'


def test_extract_prose_recommendations_title_none_when_only_junk_precedes():
    text = '```python\npropose_nav_param_change(parameter="x", new_value=1)\n```'
    items = agentic_loop.extract_prose_recommendations(text)

    assert items[0]['title'] is None


def test_extract_prose_recommendations_title_skips_generic_section_heading():
    """Live bug, 2026-07-29: the model's own generic '### Recommendations' section
    heading (not an item-specific title) was picked up as the FIRST item's title —
    'GOOD — Recommendations' on the real page, meaningless to a reader."""
    text = (
        '### Recommendations\n\n'
        'propose_nav_param_change(parameter="odometry_frequency", new_value=50.0)\n'
    )
    items = agentic_loop.extract_prose_recommendations(text)

    assert items[0]['title'] is None


def test_extract_prose_recommendations_title_skips_stray_closing_paren():
    """Live bug, 2026-07-29: a lone ')' left over from a PRIOR multi-line call was
    picked up as the 'title' for the NEXT call."""
    text = (
        'propose_nav_param_change(\n'
        '    parameter="a",\n'
        '    new_value=1,\n'
        ')\n'
        'Second Recommendation\n'
        'propose_mission_plan(mission="b")\n'
    )
    items = agentic_loop.extract_prose_recommendations(text)

    assert items[1]['title'] == 'Second Recommendation'


def test_extract_prose_recommendations_combines_component_and_parameter_into_param_path():
    items = agentic_loop.extract_prose_recommendations(_REAL_KWARGS_STYLE_ANALYSIS_TEXT)

    assert items[0]['input']['param_path'] == 'local_costmap.update_frequency'
    assert items[0]['input']['proposed_value'] == '10.0'
    assert items[1]['input']['param_path'] == 'camera_interface.image_transport'
    assert items[1]['input']['proposed_value'] == 'compressed'


def test_extract_prose_recommendations_never_returns_empty_input_for_a_found_call():
    """Even the loosely-structured mission plan call must produce SOMETHING non-empty
    — existence stays visible even when details can't be cleanly parsed."""
    items = agentic_loop.extract_prose_recommendations(_REAL_KWARGS_STYLE_ANALYSIS_TEXT)

    assert items[2]['input']  # non-empty dict


def test_extract_prose_recommendations_parses_colon_style_three_segments():
    items = agentic_loop.extract_prose_recommendations(_REAL_COLON_STYLE_ANALYSIS_TEXT)

    assert items[0]['input']['param_path'] == 'local_costmap.robot_radius'
    assert items[0]['input']['proposed_value'] == '0.237'


def test_extract_prose_recommendations_parses_colon_style_four_segments():
    items = agentic_loop.extract_prose_recommendations(_REAL_COLON_STYLE_ANALYSIS_TEXT)

    assert items[1]['input']['param_path'] == 'global_costmap.inflation_layer.inflation_radius'
    assert items[1]['input']['proposed_value'] == '0.25'
    assert items[2]['input']['param_path'] == 'local_costmap.inflation_layer.inflation_radius'
    assert items[2]['input']['proposed_value'] == '0.20'


def test_extract_prose_recommendations_falls_back_to_raw_text_when_unparseable():
    items = agentic_loop.extract_prose_recommendations(_REAL_COLON_STYLE_ANALYSIS_TEXT)

    assert items[3]['tool_name'] == 'propose_mission_plan'
    assert items[3]['input']  # non-empty — didn't silently drop it


_REAL_JSON_OBJECT_STYLE_ANALYSIS_TEXT = (
    'Optimize parameters related to camera integration or adjust the camera\'s '
    'configuration settings.\n'
    '{ "tool": "propose_nav_param_change", "parameter": "camera/image_transport", '
    '"value": "compressed" }'
)


def test_extract_prose_recommendations_parses_real_json_object_style_call():
    """Third real format observed live, 2026-07-29: the model sometimes writes a
    single-line JSON object with a "tool" key instead of a tool_name(...) call —
    valid JSON, so parsed directly rather than via the paren-call regex."""
    items = agentic_loop.extract_prose_recommendations(_REAL_JSON_OBJECT_STYLE_ANALYSIS_TEXT)

    assert len(items) == 1
    assert items[0]['tool_name'] == 'propose_nav_param_change'
    assert items[0]['input']['param_path'] == 'camera/image_transport'
    assert items[0]['input']['proposed_value'] == 'compressed'


def test_extract_prose_recommendations_json_object_style_is_fact_checkable():
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(text=_REAL_JSON_OBJECT_STYLE_ANALYSIS_TEXT),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert len(items) == 1
    assert items[0]['source'] == 'extracted'
    # 'camera/image_transport' isn't a real nav2_params.yaml param — must be 'bad'.
    assert items[0]['auto_verdict'] == 'bad'


def test_extract_prose_recommendations_ignores_unrelated_json_objects():
    text = '{"foo": "bar", "baz": 1}'
    assert agentic_loop.extract_prose_recommendations(text) == []


def test_extract_prose_recommendations_combines_paren_and_json_styles_in_one_text():
    combined = _REAL_COLON_STYLE_ANALYSIS_TEXT + '\n' + _REAL_JSON_OBJECT_STYLE_ANALYSIS_TEXT
    items = agentic_loop.extract_prose_recommendations(combined)

    assert len(items) == 5


_REAL_NESTED_JSON_STYLE_ANALYSIS_TEXT = """Improve Odometry Data Reliability

{
  "tool": "propose_nav_param_change",
  "parameters": {
    "parameter_name": "odometry_frequency",
    "new_value": 50.0,
    "rationale": "Increasing the odometry frequency to improve data reliability and reduce position errors."
  }
}

Enhance Camera Stream Reliability

{
  "tool": "propose_nav_param_change",
  "parameters": {
    "parameter_name": "camera_frequency",
    "new_value": 30.0,
    "rationale": "Increasing the camera frequency to ensure more reliable and consistent data capture."
  }
}

Generate More Challenging Missions

{
  "tool": "propose_mission_plan",
  "parameters": {
    "mission_name": "complex_hallway_navigation",
    "locations": ["hallway_west", "bedroom_goal", "desk"],
    "rationale": "Creating a mission that includes multiple waypoints to increase the complexity and challenge of navigation tasks."
  }
}

Create A Harder World Variant

{
  "tool": "generate_world_variant",
  "parameters": {
    "variant_name": "high_obstacle_density",
    "rationale": "Generating a world variant with increased obstacle density to test the robot's ability to navigate complex environments."
  }
}"""


def test_extract_prose_recommendations_finds_all_calls_in_real_nested_json_text():
    """4th real format observed live, 2026-07-29: a JSON object with args wrapped in
    a nested "parameters" sub-object, not flat — the original json_object regex
    explicitly excluded nested braces ([^{}]*) and silently found ZERO of these."""
    items = agentic_loop.extract_prose_recommendations(_REAL_NESTED_JSON_STYLE_ANALYSIS_TEXT)

    assert [i['tool_name'] for i in items] == [
        'propose_nav_param_change', 'propose_nav_param_change',
        'propose_mission_plan', 'generate_world_variant',
    ]


def test_extract_prose_recommendations_flattens_nested_parameters_object():
    items = agentic_loop.extract_prose_recommendations(_REAL_NESTED_JSON_STYLE_ANALYSIS_TEXT)

    assert items[0]['input']['param_path'] == 'odometry_frequency'
    assert items[0]['input']['proposed_value'] == '50.0'
    assert items[0]['input']['rationale'].startswith('Increasing the odometry')


def test_extract_prose_recommendations_nested_json_pulls_title():
    items = agentic_loop.extract_prose_recommendations(_REAL_NESTED_JSON_STYLE_ANALYSIS_TEXT)

    assert items[0]['title'] == 'Improve Odometry Data Reliability'
    assert items[3]['title'] == 'Create A Harder World Variant'


def test_extract_prose_recommendations_nested_json_items_are_fact_checkable():
    """odometry_frequency isn't a real nav2_params.yaml param — must come out 'bad'."""
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(text=_REAL_NESTED_JSON_STYLE_ANALYSIS_TEXT),
    ])
    items = agentic_loop.evaluate_diagnosis_items(response)

    nav_param_items = [i for i in items if i['tool_name'] == 'propose_nav_param_change']
    assert len(nav_param_items) == 2
    assert all(i['auto_verdict'] == 'bad' for i in nav_param_items)


def test_evaluate_diagnosis_items_fact_checks_extracted_items_too():
    """The whole point of extraction: prose-only recommendations get the SAME
    fact-check as real submitted tool calls, end to end via evaluate_diagnosis_items
    — scan_period doesn't exist anywhere in the real nav2_params.yaml."""
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(text='propose_nav_param_change(lidar:scan_period:0.1)'),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert len(items) == 1
    assert items[0]['source'] == 'extracted'
    assert items[0]['auto_verdict'] == 'bad'
    assert 'scan_period' in items[0]['auto_notes']


def test_evaluate_diagnosis_items_tags_submitted_items_correctly():
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._ToolUseBlock(name='propose_mission_plan',
                                    input={'mission_description': 'd', 'goals': [], 'rationale': 'r'}),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert items[0]['source'] == 'submitted'
    assert items[0]['title'] is None


def test_evaluate_diagnosis_items_reproduces_the_real_incident_end_to_end():
    """Regression fixture: the exact live incident that motivated extraction — one
    real submitted mission plan, plus prose describing three other recommendations
    that never became real tool calls. All four must now appear in one list."""
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(text=_REAL_KWARGS_STYLE_ANALYSIS_TEXT),
        agentic_loop._ToolUseBlock(name='propose_mission_plan',
                                    input={'mission_description': 'd', 'goals': [], 'rationale': 'r'}),
    ])

    items = agentic_loop.evaluate_diagnosis_items(response)

    assert len(items) == 4
    sources = [i['source'] for i in items]
    assert sources.count('submitted') == 1
    assert sources.count('extracted') == 3


def test_summarize_diagnosis_reports_no_recommendations():
    assert agentic_loop.summarize_diagnosis([]) == \
        ['No recommendations were found in this response — nothing to review.']


def test_summarize_diagnosis_tally_line_counts_by_source():
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(text=_REAL_KWARGS_STYLE_ANALYSIS_TEXT),
        agentic_loop._ToolUseBlock(name='propose_mission_plan',
                                    input={'mission_description': 'd', 'goals': [], 'rationale': 'r'}),
    ])
    items = agentic_loop.evaluate_diagnosis_items(response)

    lines = agentic_loop.summarize_diagnosis(items)

    assert '4 recommendation(s) found' in lines[0]
    assert '1 formally submitted' in lines[0]
    assert '3 found only in the written text' in lines[0]


def test_summarize_diagnosis_lists_extracted_titles():
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._TextBlock(text=_REAL_KWARGS_STYLE_ANALYSIS_TEXT),
    ])
    items = agentic_loop.evaluate_diagnosis_items(response)

    lines = agentic_loop.summarize_diagnosis(items)

    assert any('Improve Odometry Frequency' in line for line in lines)


def test_summarize_diagnosis_includes_conflict_notes():
    response = agentic_loop._DiagnosisResponse(content=[
        agentic_loop._ToolUseBlock(
            name='propose_nav_param_change',
            input={'param_path': 'a.rotate_to_heading_angular_vel',
                   'proposed_value': '1.2', 'rationale': 'r1'}),
        agentic_loop._ToolUseBlock(
            name='propose_nav_param_change',
            input={'param_path': 'b.rotate_to_heading_angular_vel',
                   'proposed_value': '0.3', 'rationale': 'r2'}),
    ])
    items = agentic_loop.evaluate_diagnosis_items(response)

    lines = agentic_loop.summarize_diagnosis(items)

    assert any('disagrees with' in line for line in lines)


def test_describe_potential_changes_no_matches():
    lines = agentic_loop.describe_potential_changes('just some general discussion')

    assert lines == ['No specific changes were identified in the analysis above.']


def test_describe_potential_changes_no_text():
    lines = agentic_loop.describe_potential_changes(None)

    assert lines == ['No specific changes were identified in the analysis above.']


def test_describe_potential_changes_nav_param_plain_language():
    lines = agentic_loop.describe_potential_changes(_REAL_KWARGS_STYLE_ANALYSIS_TEXT)

    assert len(lines) == 3
    # No tool names, no JSON, no verdicts anywhere in the output.
    for line in lines:
        assert 'propose_' not in line
        assert 'generate_' not in line
        assert '{' not in line
        assert 'GOOD' not in line and 'BAD' not in line and 'UNVERIFIED' not in line


def test_describe_potential_changes_includes_title_and_rationale():
    lines = agentic_loop.describe_potential_changes(_REAL_KWARGS_STYLE_ANALYSIS_TEXT)

    assert any('Improve Odometry Frequency' in line for line in lines)
    assert any('local_costmap.update_frequency' in line and '10.0' in line for line in lines)


def test_describe_potential_changes_mission_and_world_variant_phrasing():
    lines = agentic_loop.describe_potential_changes(_REAL_KWARGS_STYLE_ANALYSIS_TEXT)

    joined = ' '.join(lines)
    assert 'mission' in joined.lower()


def test_describe_potential_changes_falls_back_to_raw_text():
    lines = agentic_loop.describe_potential_changes(_REAL_COLON_STYLE_ANALYSIS_TEXT)

    # The unparseable propose_mission_plan(home_base hallway_west ...) call still
    # produces a line — existence stays visible even without clean field extraction.
    assert len(lines) == 4


def test_normalize_extracted_fields_preserves_unrecognized_keys():
    """Root cause of the 'pretty lame' summary bug, 2026-07-29: unrecognized field
    names used to be silently DISCARDED (only aliased canonical fields were kept),
    so when SOME field matched an alias but others didn't, the unmatched ones were
    lost before display ever saw them — producing a bare, content-free sentence
    even though the model had written real information."""
    result = agentic_loop._normalize_extracted_fields(
        'propose_nav_param_change', {'value': '6.0', 'target': 'local_costmap.width'}, '')

    assert result['proposed_value'] == '6.0'  # aliased, as before
    assert result['target'] == 'local_costmap.width'  # NEW: no longer discarded


def test_normalize_extracted_fields_removes_raw_keys_once_consumed_by_an_alias():
    """2026-07-29, follow-up fix: preserving raw_pairs (previous fix) introduced a
    NEW bug — a key that successfully aliased (e.g. 'value' -> proposed_value) was
    ALSO left sitting in the dict under its original name, so display showed the
    same information twice: 'local_costmap.width -> 5. (parameter=local_costmap.
    width, value=5)'. Once a raw key has been folded into a canonical field, it
    must not also remain as a separate, redundant 'leftover' field."""
    result = agentic_loop._normalize_extracted_fields(
        'propose_nav_param_change',
        {'parameter': 'local_costmap.width', 'value': '5'}, '')

    assert result == {'param_path': 'local_costmap.width', 'proposed_value': '5'}
    assert 'parameter' not in result
    assert 'value' not in result


def test_describe_potential_changes_no_duplicate_value_in_parentheses():
    """Reproduces the exact live incident: real param_path/proposed_value already
    shown in the main sentence must not ALSO appear in a redundant '(parameter=...,
    value=...)' parenthetical."""
    text = '{"tool": "propose_nav_param_change", "parameter": "local_costmap.width", "value": 5}'

    lines = agentic_loop.describe_potential_changes(text)

    assert lines == ['A parameter change was mentioned: local_costmap.width → 5.']


def test_describe_potential_changes_shows_proposed_value_alone_when_param_path_missing():
    text = ('{"tool": "propose_nav_param_change", "value": 6.0, '
            '"target": "local_costmap.width"}')
    lines = agentic_loop.describe_potential_changes(text)

    assert len(lines) == 1
    assert lines[0] != 'A parameter change was mentioned.'  # not the bare/empty case
    assert '6.0' in lines[0]


def test_describe_potential_changes_shows_unrecognized_fields_instead_of_going_silent():
    text = ('{"tool": "propose_mission_plan", "destination_sequence": '
            '["bedroom_goal", "desk"]}')
    lines = agentic_loop.describe_potential_changes(text)

    assert len(lines) == 1
    assert lines[0] != 'A mission plan was mentioned.'
    assert 'destination_sequence' in lines[0]


def test_diagnose_rejects_unknown_backend(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}

    with pytest.raises(ValueError, match="unknown AGENTIC_BACKEND"):
        agentic_loop.diagnose(run_data, db_path=db, backend="bogus")
