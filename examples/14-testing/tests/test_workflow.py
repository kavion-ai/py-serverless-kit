"""Workflow tests: once with the real handlers, once with stubbed tasks."""

import pytest

from py_serverless_kit.runtime.workflow import WorkflowEngine, WorkflowFailed
from py_serverless_kit.workflows import definition_dict


def test_scoring_end_to_end(runner):
    out = runner.run_workflow("scoring", {"customer": "ada", "vip": True})
    assert out["output"] == {"customer": "ada", "vip": True, "enriched": True, "score": 90}
    assert [h["state"] for h in out["history"] if h.get("event") == "enter"] == ["Enrich", "Score", "Route", "Approve"]


def test_scoring_declines(runner):
    with pytest.raises(WorkflowFailed) as exc:
        runner.run_workflow("scoring", {"customer": "bob"})
    assert exc.value.error == "LowScore"


def test_routing_with_stubbed_tasks(project):
    """Test only the state machine logic: replace every task with a stub."""
    calls = []

    def fake_task(function, data):
        calls.append(function)
        return {**data, "score": 85} if function == "score" else data

    engine = WorkflowEngine(definition_dict(project.config.workflows["scoring"]), fake_task)
    assert engine.run({"x": 1})["score"] == 85
    assert calls == ["enrich", "score"]
