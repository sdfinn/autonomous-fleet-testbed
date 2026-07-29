# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/agentic_loop.py's diagnose() prompt-building — no real
Anthropic API calls (client.messages.create is monkeypatched in every test)."""
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
                         lambda prompt: agentic_loop._DiagnosisResponse(content=[]))

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db, backend='ollama')

    row = sqlite3.connect(db).execute(
        "SELECT backend, model_name FROM ai_diagnoses ORDER BY id DESC LIMIT 1").fetchone()
    assert row == ('ollama', agentic_loop.OLLAMA_MODEL)


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

    def _fake_diagnose_ollama(prompt):
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
                         lambda prompt: "sentinel-ollama-default")

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}
    result = agentic_loop.diagnose(run_data, db_path=db)  # no backend= given

    assert result == "sentinel-ollama-default"


def test_diagnose_reads_backend_from_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_BACKEND", "ollama")
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    monkeypatch.setattr(agentic_loop, "_diagnose_ollama", lambda prompt: "sentinel")

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


def test_diagnose_rejects_unknown_backend(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}

    with pytest.raises(ValueError, match="unknown AGENTIC_BACKEND"):
        agentic_loop.diagnose(run_data, db_path=db, backend="bogus")
