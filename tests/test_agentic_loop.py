# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/agentic_loop.py's diagnose() prompt-building — no real
Anthropic API calls (client.messages.create is monkeypatched in every test)."""
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
    fake_response = _FakeOllamaChatResponse(
        _FakeOllamaMessage(content='just some analysis text, no proposal'))
    monkeypatch.setattr(agentic_loop.ollama, 'chat', lambda **kw: fake_response)

    with pytest.raises(RuntimeError, match='did not propose a tool call'):
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


def test_diagnose_rejects_unknown_backend(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS", "sim_engine": "gazebo"}

    with pytest.raises(ValueError, match="unknown AGENTIC_BACKEND"):
        agentic_loop.diagnose(run_data, db_path=db, backend="bogus")
