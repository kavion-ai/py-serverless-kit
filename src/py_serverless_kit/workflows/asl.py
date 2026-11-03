"""Compile a portable workflow definition to Amazon States Language."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

ArnResolver = Callable[[str], str]


def _errors(errors: List[str]) -> List[str]:
    return ["States.ALL" if e in ("*", "States.ALL") else e for e in (errors or ["*"])]


def _typed(op: str, value: Any) -> str:
    if isinstance(value, bool):
        return "Boolean" + op
    if isinstance(value, (int, float)):
        return "Numeric" + op
    return "String" + op


_CMP = {"gt": "GreaterThan", "gte": "GreaterThanEquals", "lt": "LessThan", "lte": "LessThanEquals"}


def compile_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    if "and" in rule:
        return {"And": [compile_rule(r) for r in rule["and"]]}
    if "or" in rule:
        return {"Or": [compile_rule(r) for r in rule["or"]]}
    if "not" in rule:
        return {"Not": compile_rule(rule["not"])}
    var = rule.get("variable", "$")
    if "equals" in rule:
        value = rule["equals"]
        if value is None:
            return {"Variable": var, "IsNull": True}
        return {"Variable": var, _typed("Equals", value): value}
    if "not_equals" in rule:
        return {"Not": compile_rule({"variable": var, "equals": rule["not_equals"]})}
    for op, name in _CMP.items():
        if op in rule:
            value = rule[op]
            if isinstance(value, bool):
                raise ValueError(f"operator {op} cannot compare booleans")
            return {"Variable": var, _typed(name, value): value}
    if "in" in rule:
        return {"Or": [compile_rule({"variable": var, "equals": v}) for v in rule["in"]]}
    if "contains" in rule:
        needle = str(rule["contains"]).replace("*", "\\*")
        return {"Variable": var, "StringMatches": f"*{needle}*"}
    if "matches" in rule:
        return {"Variable": var, "StringMatches": rule["matches"]}
    if "is_null" in rule:
        return {"Variable": var, "IsNull": bool(rule["is_null"])}
    if "is_present" in rule:
        return {"Variable": var, "IsPresent": bool(rule["is_present"])}
    raise ValueError(f"unsupported choice rule: {rule}")


def _flow(state: Dict[str, Any], out: Dict[str, Any]) -> None:
    if state.get("next"):
        out["Next"] = state["next"]
    else:
        out["End"] = True


def _io(state: Dict[str, Any], out: Dict[str, Any]) -> None:
    if state.get("input_path"):
        out["InputPath"] = state["input_path"]
    if "result_path" in state and state["result_path"] != "$":
        out["ResultPath"] = state["result_path"]


def compile_machine(machine: Dict[str, Any], arn_of: ArnResolver) -> Dict[str, Any]:
    states: Dict[str, Any] = {}
    for name, st in machine["states"].items():
        kind = st["type"]
        out: Dict[str, Any] = {}
        if st.get("comment"):
            out["Comment"] = st["comment"]
        if kind == "task":
            out["Type"] = "Task"
            out["Resource"] = arn_of(st["function"])
            out["Parameters"] = {"__pskit": "workflow", "data.$": "$"}
            _io(st, out)
            if st.get("timeout_seconds"):
                out["TimeoutSeconds"] = int(st["timeout_seconds"])
            _flow(st, out)
        elif kind == "pass":
            out["Type"] = "Pass"
            if "result" in st:
                out["Result"] = st["result"]
            _io(st, out)
            _flow(st, out)
        elif kind == "wait":
            out["Type"] = "Wait"
            if st.get("seconds_path"):
                out["SecondsPath"] = st["seconds_path"]
            else:
                out["Seconds"] = int(st.get("seconds", 0))
            if st.get("input_path"):
                out["InputPath"] = st["input_path"]
            _flow(st, out)
        elif kind == "choice":
            out["Type"] = "Choice"
            out["Choices"] = [dict(compile_rule(r), Next=r["next"]) for r in st["choices"]]
            if st.get("default"):
                out["Default"] = st["default"]
        elif kind == "parallel":
            out["Type"] = "Parallel"
            out["Branches"] = [compile_machine(b, arn_of) for b in st["branches"]]
            _io(st, out)
            _flow(st, out)
        elif kind == "map":
            out["Type"] = "Map"
            if st.get("items_path"):
                out["ItemsPath"] = st["items_path"]
            out["ItemProcessor"] = {
                "ProcessorConfig": {"Mode": "INLINE"},
                **compile_machine(st["iterator"], arn_of),
            }
            if st.get("max_concurrency"):
                out["MaxConcurrency"] = int(st["max_concurrency"])
            _io(st, out)
            _flow(st, out)
        elif kind == "succeed":
            out["Type"] = "Succeed"
        elif kind == "fail":
            out["Type"] = "Fail"
            if st.get("error"):
                out["Error"] = st["error"]
            if st.get("cause"):
                out["Cause"] = st["cause"]
        else:  # pragma: no cover - schema prevents this
            raise ValueError(f"unknown state type {kind}")

        if kind in ("task", "parallel", "map"):
            if st.get("retry"):
                out["Retry"] = []
                for r in st["retry"]:
                    rr: Dict[str, Any] = {
                        "ErrorEquals": _errors(r.get("errors", ["*"])),
                        "IntervalSeconds": max(1, int(round(r.get("interval_seconds", 1)))),
                        "MaxAttempts": int(r.get("max_attempts", 3)),
                        "BackoffRate": float(r.get("backoff_rate", 2.0)),
                    }
                    if r.get("max_delay_seconds"):
                        rr["MaxDelaySeconds"] = int(r["max_delay_seconds"])
                    out["Retry"].append(rr)
            if st.get("catch"):
                out["Catch"] = [
                    {
                        "ErrorEquals": _errors(c.get("errors", ["*"])),
                        "Next": c["next"],
                        "ResultPath": c.get("result_path", "$.error"),
                    }
                    for c in st["catch"]
                ]
        states[name] = out
    return {"StartAt": machine["start_at"], "States": states}


def compile_asl(definition: Dict[str, Any], arn_of: ArnResolver, comment: str = "", timeout: int = 0) -> Dict[str, Any]:
    asl: Dict[str, Any] = {}
    if comment:
        asl["Comment"] = comment
    asl.update(compile_machine(definition, arn_of))
    if timeout:
        asl["TimeoutSeconds"] = int(timeout)
    return asl
