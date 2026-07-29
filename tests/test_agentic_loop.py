# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/agentic_loop.py's diagnose() prompt-building — no real
Anthropic API calls (client.messages.create is monkeypatched in every test)."""
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
    agentic_loop.diagnose(run_data, db_path=db)

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
    agentic_loop.diagnose(run_data, db_path=db,
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
    agentic_loop.diagnose(run_data, db_path=db)

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
