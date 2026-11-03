import json

import pytest

from py_serverless_kit.config.schema import WorkflowConfig
from py_serverless_kit.workflows import definition_dict
from py_serverless_kit.workflows.azure_logic import (
    LogicAppsError,
    compile_logic_app,
    lit,
    read_expr,
    rule_expr,
    write_expr,
)
from tests.workflows.test_compilers import WF


def _compile(wf, **kwargs):
    kwargs.setdefault("key", "KEY")
    actions, warnings = compile_logic_app(
        definition_dict(wf), lambda f: f"https://app/_pskit/invoke/{f}", "demo", **kwargs
    )
    return dict(actions), [name for name, _ in actions], warnings


def _walk(action):
    """Every nested action of a container action."""
    for child in (action.get("actions") or {}).values():
        yield child
        yield from _walk(child)
    for case in (action.get("cases") or {}).values():
        for child in case["actions"].values():
            yield child
            yield from _walk(child)
    for key in ("default", "else"):
        for child in ((action.get(key) or {}).get("actions") or {}).values():
            yield child
            yield from _walk(child)


def test_structure_and_order():
    actions, order, warnings = _compile(WF, timeout=600)
    assert order[0] == "init_err"
    assert {"init_data", "init_state", "init_tmp"} <= set(order)
    assert order[-3:] == ["run", "finish", "respond_timeout"]
    init = actions["init_data"]["inputs"]["variables"][0]
    assert init == {"name": "data", "type": "string", "value": "@string(coalesce(triggerBody(), json('{}')))"}
    assert actions["init_state"]["inputs"]["variables"][0]["value"] == "Validate"
    # runAfter chains the top-level actions in order.
    for prev, name in zip(order, order[1:-1]):
        assert actions[name]["runAfter"] == {prev: ["Succeeded"]}
    assert actions["respond_timeout"]["runAfter"] == {"run": ["Failed", "TimedOut"]}
    run = actions["run"]
    assert run["type"] == "Until"
    assert run["limit"] == {"count": 5000, "timeout": "PT600S"}
    cases = run["actions"]["switch"]["cases"]
    assert {c["case"] for c in cases.values()} == set(WF.states)
    assert any("only honoured" in w or "one at a time" in w for w in warnings)


def test_task_http_retry_and_catch():
    actions, _, warnings = _compile(WF)
    case = actions["run"]["actions"]["switch"]["cases"]["case_Validate"]["actions"]
    call = case["Validate_call"]
    assert call["type"] == "Http"
    assert call["inputs"]["uri"] == "https://app/_pskit/invoke/validate"
    assert call["inputs"]["headers"]["x-functions-key"] == "KEY"
    assert call["inputs"]["body"] == {"__pskit": "workflow", "data": "@json(variables('data'))"}
    policy = call["inputs"]["retryPolicy"]
    assert policy["type"] == "exponential" and policy["count"] == 4 and policy["interval"] == "PT5S"
    assert any("errors filter" in w for w in warnings)
    assert any("backoff_rate" in w for w in warnings)
    assert case["Validate_err"]["runAfter"] == {"Validate_call": ["Failed", "TimedOut"]}
    route = case["Validate_route"]["inputs"]["value"]
    assert (
        route
        == "@if(contains(json('[\"ValueError\"]'), coalesce(body('Validate_call')?['errorType'], 'Error')), 'Rejected', '__fail__')"
    )
    # Both trails join so a handled failure doesn't fail the loop.
    assert case["Validate_done"]["runAfter"] == {
        "Validate_next": ["Succeeded", "Skipped"],
        "Validate_route": ["Succeeded", "Skipped"],
    }
    # Writing data never reads the variable being set.
    for action in _walk(actions["run"]):
        if action.get("type") == "SetVariable":
            name = action["inputs"]["name"]
            assert f"variables('{name}')" not in json.dumps(action["inputs"]["value"])


def test_no_retry_disables_default_policy():
    actions, _, _ = _compile(WF)
    charge = actions["run"]["actions"]["switch"]["cases"]["case_Charge"]["actions"]["Charge_call"]
    assert charge["inputs"]["retryPolicy"] == {"type": "none"}
    # result_path: null keeps the data
    tmp = actions["run"]["actions"]["switch"]["cases"]["case_Charge"]["actions"]["Charge_tmp"]
    assert tmp["inputs"]["value"] == "@string(json(variables('data')))"


def test_choice_wait_fail():
    actions, _, _ = _compile(WF)
    cases = actions["run"]["actions"]["switch"]["cases"]
    route = cases["case_Route"]["actions"]["Route_next"]["inputs"]["value"]
    assert route.startswith("@if(and(not(equals(json(variables('data'))?['amount'], null))")
    assert route.endswith(
        "'Review', if(and(equals(json(variables('data'))?['country'], 'IN'), "
        "equals(json(variables('data'))?['vip'], true)), 'Fanout', 'Charge'))"
    )
    wait = cases["case_Review"]["actions"]["Review_wait"]
    assert wait["inputs"]["interval"] == {"count": 60, "unit": "Second"}
    fail = cases["case_Rejected"]["actions"]
    assert json.loads(fail["Rejected_err"]["inputs"]["value"]) == {"error": "Rejected", "cause": "invalid"}
    assert fail["Rejected_fail"]["inputs"]["value"] == "__fail__"


def test_parallel_and_map_use_nested_machines():
    actions, order, _ = _compile(WF)
    assert "init_data_Fanout_b0" in order and "init_state_Fanout_b1" in order
    assert "init_out_Items_it" in order
    cases = actions["run"]["actions"]["switch"]["cases"]
    fan = cases["case_Fanout"]["actions"]
    assert fan["Fanout_b0_loop"]["type"] == "Until" and fan["Fanout_b1_loop"]["type"] == "Until"
    assert fan["Fanout_b0_in"]["runAfter"] == {} and fan["Fanout_b1_in"]["runAfter"] == {}
    assert fan["Fanout_tmp"]["runAfter"] == {"Fanout_b0_loop": ["Succeeded"], "Fanout_b1_loop": ["Succeeded"]}
    assert "setProperty(json(variables('data')), 'fanout', createArray(" in fan["Fanout_tmp"]["inputs"]["value"]
    each = cases["case_Items"]["actions"]["Items_each"]
    assert each["type"] == "Foreach"
    assert each["foreach"] == "@json(variables('data'))?['items']"
    assert each["runtimeConfiguration"] == {"concurrency": {"repetitions": 1}}


def test_sync_false_has_no_response():
    actions, order, _ = _compile(WF, sync=False)
    assert "respond_timeout" not in order
    assert "else" not in actions["finish"]
    assert list(actions["finish"]["actions"]) == ["terminate"]


def test_expressions():
    assert read_expr("$.a[0].b", "D") == "D?['a']?[0]?['b']"
    assert write_expr("$", "D", "V") == "V"
    assert write_expr(None, "D", "V") == "D"
    assert write_expr("$.a.b", "D", "V") == "setProperty(D, 'a', setProperty(coalesce(D?['a'], json('{}')), 'b', V))"
    with pytest.raises(LogicAppsError):
        write_expr("$.a[0]", "D", "V")
    assert lit("it's") == "'it''s'"
    assert lit({"a": [1]}) == "json('{\"a\":[1]}')"
    assert rule_expr({"variable": "$.s", "matches": "ab*"}, "D") == "startsWith(string(D?['s']), 'ab')"
    assert rule_expr({"variable": "$.s", "matches": "*ab"}, "D") == "endsWith(string(D?['s']), 'ab')"
    assert rule_expr({"variable": "$.s", "matches": "*ab*"}, "D") == "contains(string(D?['s']), 'ab')"
    assert rule_expr({"variable": "$.s", "in": [1, 2]}, "D") == "contains(json('[1,2]'), D?['s'])"
    assert rule_expr({"variable": "$.s", "is_null": True}, "D") == "equals(D?['s'], null)"
    assert rule_expr({"not": {"variable": "$.s", "equals": 1}}, "D") == "not(equals(D?['s'], 1))"
    with pytest.raises(LogicAppsError):
        rule_expr({"variable": "$.s", "matches": "a?b"}, "D")


def test_nesting_limit():
    leaf = {"start_at": "X", "states": {"X": {"type": "pass", "end": True}}}

    def nest(depth):
        if depth == 0:
            return leaf
        return {"start_at": "P", "states": {"P": {"type": "parallel", "branches": [nest(depth - 1)], "end": True}}}

    ok = WorkflowConfig.model_validate(nest(3))
    _compile(ok)
    too_deep = WorkflowConfig.model_validate(nest(4))
    with pytest.raises(LogicAppsError, match="too deeply"):
        _compile(too_deep)
