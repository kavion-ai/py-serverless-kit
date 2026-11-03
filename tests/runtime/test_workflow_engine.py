import pytest

from py_serverless_kit.runtime.workflow import WorkflowEngine, WorkflowFailed, evaluate_rule, get_path, set_path


class Flaky(Exception):
    pass


def make_runner(fail_times=None):
    calls = []
    fail_times = dict(fail_times or {})

    def run(fn, data):
        calls.append((fn, data))
        if fail_times.get(fn, 0) > 0:
            fail_times[fn] -= 1
            raise Flaky(f"{fn} failed")
        if fn == "double":
            return data * 2
        if fn == "inc":
            return {**data, "n": data.get("n", 0) + 1}
        if fn == "explode":
            raise ValueError("bad input")
        return data

    return run, calls


def test_paths():
    data = {"a": {"b": [1, {"c": 2}]}}
    assert get_path(data, "$.a.b[1].c") == 2
    assert get_path(data, "$") is data
    assert get_path(data, "$.x", None) is None
    assert set_path(data, "$.a.z", 5)["a"]["z"] == 5
    assert set_path(data, "$", 1) == 1
    assert set_path(data, None, 1) is data
    assert "z" not in data["a"]  # original untouched


@pytest.mark.parametrize(
    "rule,expected",
    [
        ({"variable": "$.n", "gt": 1}, True),
        ({"variable": "$.n", "lte": 1}, False),
        ({"variable": "$.s", "matches": "ab*"}, True),
        ({"variable": "$.s", "contains": "c"}, True),
        ({"variable": "$.n", "in": [1, 2, 3]}, True),
        ({"variable": "$.missing", "is_present": False}, True),
        ({"variable": "$.none", "is_null": True}, True),
        ({"and": [{"variable": "$.n", "equals": 2}, {"not": {"variable": "$.s", "equals": "x"}}]}, True),
        ({"or": [{"variable": "$.n", "equals": 9}, {"variable": "$.missing", "equals": 1}]}, False),
        ({"variable": "$.s", "gt": 3}, False),  # type mismatch -> False, not crash
    ],
)
def test_rules(rule, expected):
    assert evaluate_rule(rule, {"n": 2, "s": "abc", "none": None}) is expected


def test_sequence_choice_and_pass():
    definition = {
        "start_at": "Inc",
        "states": {
            "Inc": {"type": "task", "function": "inc", "next": "Check"},
            "Check": {"type": "choice", "choices": [{"variable": "$.n", "lt": 3, "next": "Inc"}], "default": "Tag"},
            "Tag": {"type": "pass", "result": "done", "result_path": "$.status", "next": "End"},
            "End": {"type": "succeed"},
        },
    }
    run, calls = make_runner()
    assert WorkflowEngine(definition, run).run({"n": 0}) == {"n": 3, "status": "done"}
    assert len(calls) == 3


def test_retry_then_success():
    definition = {
        "start_at": "T",
        "states": {
            "T": {"type": "task", "function": "inc", "retry": [{"errors": ["Flaky"], "max_attempts": 2}], "end": True}
        },
    }
    run, calls = make_runner({"inc": 2})
    sleeps = []
    out = WorkflowEngine(definition, run, sleep=sleeps.append).run({"n": 0})
    assert out == {"n": 1} and len(calls) == 3 and sleeps == [1.0, 2.0]


def test_retry_exhausted_then_catch():
    definition = {
        "start_at": "T",
        "states": {
            "T": {
                "type": "task",
                "function": "inc",
                "retry": [{"errors": ["*"], "max_attempts": 1, "interval_seconds": 0}],
                "catch": [{"errors": ["Flaky"], "next": "Handle", "result_path": "$.err"}],
                "next": "Never",
            },
            "Never": {"type": "fail", "error": "ShouldNotRun"},
            "Handle": {"type": "succeed"},
        },
    }
    run, calls = make_runner({"inc": 5})
    out = WorkflowEngine(definition, run, sleep=lambda s: None).run({"n": 0})
    assert out["err"]["error"] == "Flaky" and len(calls) == 2


def test_uncaught_failure_and_fail_state():
    run, _ = make_runner()
    with pytest.raises(WorkflowFailed) as exc:
        WorkflowEngine(
            {"start_at": "T", "states": {"T": {"type": "task", "function": "explode", "end": True}}}, run
        ).run({})
    assert exc.value.error == "ValueError"
    with pytest.raises(WorkflowFailed) as exc:
        WorkflowEngine({"start_at": "F", "states": {"F": {"type": "fail", "error": "Nope", "cause": "c"}}}, run).run({})
    assert (exc.value.error, exc.value.cause) == ("Nope", "c")


def test_no_choice_matched():
    run, _ = make_runner()
    d = {
        "start_at": "C",
        "states": {"C": {"type": "choice", "choices": [{"variable": "$.x", "equals": 1, "next": "C"}]}},
    }
    with pytest.raises(WorkflowFailed, match="NoChoiceMatched"):
        WorkflowEngine(d, run).run({"x": 2})


def test_parallel_and_map():
    branch = {"start_at": "D", "states": {"D": {"type": "task", "function": "double", "end": True}}}
    definition = {
        "start_at": "P",
        "states": {
            "P": {"type": "parallel", "branches": [branch, branch], "result_path": "$.par", "next": "M"},
            "M": {
                "type": "map",
                "items_path": "$.items",
                "iterator": branch,
                "result_path": "$.mapped",
                "max_concurrency": 2,
                "end": True,
            },
        },
    }
    run, _ = make_runner()

    def runner(fn, data):
        if fn == "double" and isinstance(data, dict):
            return 0
        return run(fn, data)

    out = WorkflowEngine(definition, runner).run({"items": [1, 2, 3]})
    assert out["mapped"] == [2, 4, 6] and out["par"] == [0, 0]


def test_wait_and_input_path():
    slept = []
    d = {
        "start_at": "W",
        "states": {
            "W": {"type": "wait", "seconds_path": "$.delay", "next": "T"},
            "T": {"type": "task", "function": "double", "input_path": "$.v", "result_path": "$.v2", "end": True},
        },
    }
    run, _ = make_runner()
    assert WorkflowEngine(d, run, sleep=slept.append).run({"delay": 3, "v": 4})["v2"] == 8
    assert slept == [3.0]


def test_max_steps_guard():
    d = {"start_at": "L", "states": {"L": {"type": "pass", "next": "L"}}}
    with pytest.raises(WorkflowFailed, match="exceeded"):
        WorkflowEngine(d, make_runner()[0], max_steps=10).run({})
