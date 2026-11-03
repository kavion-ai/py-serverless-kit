import json

import pytest

from py_serverless_kit.config.schema import WorkflowConfig
from py_serverless_kit.workflows import definition_dict
from py_serverless_kit.workflows.asl import compile_asl, compile_rule
from py_serverless_kit.workflows.gcp import compile_gcp, read_expr, rule_expr

WF = WorkflowConfig.model_validate(
    {
        "description": "demo",
        "start_at": "Validate",
        "states": {
            "Validate": {
                "type": "task",
                "function": "validate",
                "retry": [{"errors": ["Timeout"], "max_attempts": 4, "interval_seconds": 2, "backoff_rate": 1.5}],
                "catch": [{"errors": ["ValueError"], "next": "Rejected"}],
                "next": "Route",
            },
            "Route": {
                "type": "choice",
                "choices": [
                    {"variable": "$.amount", "gt": 100, "next": "Review"},
                    {
                        "and": [{"variable": "$.country", "equals": "IN"}, {"variable": "$.vip", "equals": True}],
                        "next": "Fanout",
                    },
                ],
                "default": "Charge",
            },
            "Review": {"type": "wait", "seconds": 60, "next": "Charge"},
            "Fanout": {
                "type": "parallel",
                "branches": [
                    {"start_at": "A", "states": {"A": {"type": "task", "function": "charge", "end": True}}},
                    {"start_at": "B", "states": {"B": {"type": "pass", "result": {"ok": True}, "end": True}}},
                ],
                "result_path": "$.fanout",
                "next": "Items",
            },
            "Items": {
                "type": "map",
                "items_path": "$.items",
                "max_concurrency": 5,
                "iterator": {"start_at": "I", "states": {"I": {"type": "task", "function": "charge", "end": True}}},
                "result_path": "$.items_out",
                "next": "Charge",
            },
            "Charge": {"type": "task", "function": "charge", "result_path": None, "end": True},
            "Rejected": {"type": "fail", "error": "Rejected", "cause": "invalid"},
        },
    }
)


def test_asl_structure():
    asl = compile_asl(definition_dict(WF), lambda f: f"arn:{f}", "demo", 300)
    st = asl["States"]
    assert asl["Comment"] == "demo" and asl["TimeoutSeconds"] == 300 and asl["StartAt"] == "Validate"
    v = st["Validate"]
    assert v["Resource"] == "arn:validate"
    assert v["Parameters"] == {"__pskit": "workflow", "data.$": "$"}
    assert v["Retry"] == [{"ErrorEquals": ["Timeout"], "IntervalSeconds": 2, "MaxAttempts": 4, "BackoffRate": 1.5}]
    assert v["Catch"] == [{"ErrorEquals": ["ValueError"], "Next": "Rejected", "ResultPath": "$.error"}]
    assert st["Route"]["Choices"][0] == {"Variable": "$.amount", "NumericGreaterThan": 100, "Next": "Review"}
    assert st["Route"]["Choices"][1]["And"][1] == {"Variable": "$.vip", "BooleanEquals": True}
    assert st["Route"]["Default"] == "Charge"
    assert st["Review"] == {"Type": "Wait", "Seconds": 60, "Next": "Charge"}
    assert len(st["Fanout"]["Branches"]) == 2 and st["Fanout"]["ResultPath"] == "$.fanout"
    assert st["Items"]["ItemProcessor"]["StartAt"] == "I" and st["Items"]["MaxConcurrency"] == 5
    assert st["Charge"]["ResultPath"] is None and st["Charge"]["End"] is True
    assert st["Rejected"] == {"Type": "Fail", "Error": "Rejected", "Cause": "invalid"}
    json.dumps(asl)  # serialisable


@pytest.mark.parametrize(
    "rule,expected",
    [
        ({"variable": "$.s", "equals": "x"}, {"Variable": "$.s", "StringEquals": "x"}),
        ({"variable": "$.s", "equals": None}, {"Variable": "$.s", "IsNull": True}),
        ({"variable": "$.n", "not_equals": 1}, {"Not": {"Variable": "$.n", "NumericEquals": 1}}),
        ({"variable": "$.s", "lte": "m"}, {"Variable": "$.s", "StringLessThanEquals": "m"}),
        ({"variable": "$.s", "contains": "ab"}, {"Variable": "$.s", "StringMatches": "*ab*"}),
        (
            {"variable": "$.n", "in": [1, 2]},
            {"Or": [{"Variable": "$.n", "NumericEquals": 1}, {"Variable": "$.n", "NumericEquals": 2}]},
        ),
        ({"variable": "$.p", "is_present": True}, {"Variable": "$.p", "IsPresent": True}),
    ],
)
def test_asl_rules(rule, expected):
    assert compile_rule(rule) == expected


def test_gcp_structure():
    source, warnings = compile_gcp(definition_dict(WF), lambda f: f"https://{f}", "orders")
    main = source["main"]
    assert main["params"] == ["input"]
    names = [next(iter(step)) for step in main["steps"]]
    assert names[0] == "s_init"
    assert "s_Validate_pre" in names and "s_Validate_route" in names and "s_Validate_out" in names
    validate = next(step["s_Validate"] for step in main["steps"] if "s_Validate" in step)
    assert validate["try"]["call"] == "http.post"
    assert validate["try"]["args"]["url"] == "https://validate"
    assert validate["try"]["args"]["auth"] == {"type": "OIDC"}
    assert validate["retry"]["max_retries"] == 4
    assert validate["retry"]["backoff"] == {"initial_delay": 2.0, "max_delay": 300.0, "multiplier": 1.5}
    pred = source[validate["retry"]["predicate"][2:-1]]
    assert "Timeout" in json.dumps(pred)
    # parallel / map branches become subworkflows
    assert any(k.startswith("orders_s_Fanout_b") for k in source)
    assert any(k.startswith("orders_s_Items_it") for k in source)
    # Charge discards its result
    out = next(step["s_Charge_out"] for step in main["steps"] if "s_Charge_out" in step)
    assert "_discard" in out["assign"][0] and out["return"] == "${data}"
    assert warnings == []
    json.dumps(source)


def test_gcp_expressions():
    assert read_expr("$") == "data"
    assert read_expr("$.a.b") == 'map.get(data, ["a", "b"])'
    assert read_expr("$.a[0]") == 'data["a"][0]'
    assert rule_expr({"variable": "$.n", "gte": 3}) == '(map.get(data, ["n"]) >= 3)'
    assert rule_expr({"not": {"variable": "$.s", "in": ["a"]}}) == '(not (map.get(data, ["s"]) in ["a"]))'
    assert "text.match_regex" in rule_expr({"variable": "$.s", "matches": "a*"})


def test_gcp_warns_on_multiple_retries():
    wf = WorkflowConfig.model_validate(
        {
            "start_at": "T",
            "states": {
                "T": {"type": "task", "function": "f", "retry": [{"errors": ["A"]}, {"errors": ["B"]}], "end": True}
            },
        }
    )
    _, warnings = compile_gcp(definition_dict(wf), lambda f: f, "w")
    assert warnings and "first retry" in warnings[0]
