"""Compile a portable workflow definition to Google Cloud Workflows (JSON syntax).

Each task state becomes an authenticated ``http.post`` to the Cloud Function's
URL with the ``{"__pskit": "workflow", "data": ...}`` envelope; the GCP adapter
answers with the handler's JSON result or a 500 ``{"errorType", "cause"}``.

Limitations compared to Step Functions (validated, reported as warnings):

* only the *first* retry rule of a task is used (Cloud Workflows allows one policy);
* retry / catch are honoured on ``task`` states only.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

UrlResolver = Callable[[str], str]
_MAX_HTTP_TIMEOUT = 1800


def _sid(*parts: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", "_".join(p for p in parts if p))


def _keys(path: Optional[str]) -> List[Any]:
    if not path or path == "$":
        return []
    from ..runtime.workflow import _tokens  # same JSON-path dialect as the engine

    return _tokens(path)


def read_expr(path: Optional[str], var: str = "data") -> str:
    keys = _keys(path)
    if not keys:
        return var
    if all(isinstance(k, str) for k in keys):
        return f"map.get({var}, {json.dumps(keys)})"
    expr = var
    for k in keys:
        expr += f"[{json.dumps(k)}]"
    return expr


def assign_target(path: Optional[str], var: str = "data") -> Optional[str]:
    if path is None:
        return None
    keys = _keys(path)
    target = var
    for k in keys:
        target += f"[{json.dumps(k)}]" if isinstance(k, int) else f".{k}"
    return target


def _lit(value: Any) -> str:
    return json.dumps(value)


def rule_expr(rule: Dict[str, Any]) -> str:
    if "and" in rule:
        return "(" + " and ".join(rule_expr(r) for r in rule["and"]) + ")"
    if "or" in rule:
        return "(" + " or ".join(rule_expr(r) for r in rule["or"]) + ")"
    if "not" in rule:
        return f"(not {rule_expr(rule['not'])})"
    v = read_expr(rule.get("variable", "$"))
    simple = {"equals": "==", "not_equals": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    for op, sym in simple.items():
        if op in rule:
            return f"({v} {sym} {_lit(rule[op])})"
    if "in" in rule:
        return f"({v} in {_lit(rule['in'])})"
    if "contains" in rule:
        return f"(len(text.find_all({v}, {_lit(str(rule['contains']))})) > 0)"
    if "matches" in rule:
        regex = "^" + re.escape(rule["matches"]).replace("\\*", ".*").replace("\\?", ".") + "$"
        return f"text.match_regex({v}, {_lit(regex)})"
    if "is_null" in rule:
        return f"({v} == null)" if rule["is_null"] else f"({v} != null)"
    if "is_present" in rule:
        return f"({v} != null)" if rule["is_present"] else f"({v} == null)"
    raise ValueError(f"unsupported choice rule: {rule}")


def _errors_condition(errors: List[str]) -> str:
    if any(e in ("*", "States.ALL") for e in errors or ["*"]):
        return "${true}"
    return '${map.get(e, ["body", "errorType"]) in ' + _lit(list(errors)) + "}"


class _Compiler:
    def __init__(self, url_of: UrlResolver, workflow: str) -> None:
        self.url_of = url_of
        self.workflow = workflow
        self.subworkflows: Dict[str, Any] = {}
        self.warnings: List[str] = []

    # ------------------------------------------------------------------
    def machine(self, machine: Dict[str, Any], prefix: str) -> List[Dict[str, Any]]:
        states: Dict[str, Dict[str, Any]] = machine["states"]
        entry = {name: self._entry_step(prefix, name, st) for name, st in states.items()}
        steps: List[Dict[str, Any]] = [
            {
                _sid(prefix, "init"): {
                    "assign": [{"data": "${input}"}, {"_caught": ""}],
                    "next": entry[machine["start_at"]],
                }
            }
        ]
        for name, st in states.items():
            steps.extend(self.state(prefix, name, st, entry))
        return steps

    def _entry_step(self, prefix: str, name: str, st: Dict[str, Any]) -> str:
        if st["type"] == "task" and st.get("catch"):
            return _sid(prefix, name, "pre")
        if st["type"] in ("parallel", "map"):
            return _sid(prefix, name, "init")
        return _sid(prefix, name)

    def _after(self, st: Dict[str, Any], entry: Dict[str, str]) -> Dict[str, Any]:
        if st.get("next"):
            return {"next": entry[st["next"]]}
        return {"return": "${data}"}

    def _store(
        self, prefix: str, name: str, st: Dict[str, Any], value_expr: str, entry: Dict[str, str]
    ) -> Dict[str, Any]:
        target = assign_target(st.get("result_path", "$"))
        body: Dict[str, Any] = {}
        if target is not None:
            body["assign"] = [{target: value_expr}]
        else:
            body["assign"] = [{"_discard": value_expr}]
        body.update(self._after(st, entry))
        return {_sid(prefix, name, "out"): body}

    def _sub(self, machine: Dict[str, Any], name: str) -> str:
        sub_name = _sid(self.workflow, name)
        self.subworkflows[sub_name] = {"params": ["input"], "steps": self.machine(machine, sub_name)}
        return sub_name

    # ------------------------------------------------------------------
    def state(self, prefix: str, name: str, st: Dict[str, Any], entry: Dict[str, str]) -> List[Dict[str, Any]]:
        kind = st["type"]
        sid = _sid(prefix, name)
        input_expr = "${" + read_expr(st.get("input_path")) + "}"
        if kind == "task":
            return self.task(prefix, name, st, entry, input_expr)
        if kind == "pass":
            value = _lit(st["result"]) if "result" in st else read_expr(st.get("input_path"))
            return [
                {sid: {"assign": [{"_pass": "${" + value + "}"}], "next": _sid(prefix, name, "out")}},
                self._store(prefix, name, st, "${_pass}", entry),
            ]
        if kind == "wait":
            seconds: Any = int(st.get("seconds", 0))
            if st.get("seconds_path"):
                seconds = "${" + read_expr(st["seconds_path"]) + "}"
            return [{sid: {"call": "sys.sleep", "args": {"seconds": seconds}, **self._after(st, entry)}}]
        if kind == "choice":
            conds: List[Dict[str, Any]] = [
                {"condition": "${" + rule_expr(r) + "}", "next": entry[r["next"]]} for r in st["choices"]
            ]
            body: Dict[str, Any] = {"switch": conds}
            if st.get("default"):
                body["next"] = entry[st["default"]]
            else:
                conds.append({"condition": True, "raise": {"error": "States.NoChoiceMatched", "cause": name}})
            return [{sid: body}]
        if kind == "succeed":
            return [{sid: {"return": "${data}"}}]
        if kind == "fail":
            return [{sid: {"raise": {"error": st.get("error", "States.Fail"), "cause": st.get("cause", "")}}}]
        if kind == "parallel":
            if st.get("retry") or st.get("catch"):
                self.warnings.append(f"{self.workflow}.{name}: retry/catch on parallel states is ignored on GCP")
            var = _sid("par", prefix, name)
            branches = []
            for i, branch in enumerate(st["branches"]):
                sub = self._sub(branch, f"{prefix}_{name}_b{i}")
                branches.append(
                    {
                        f"b{i}": {
                            "steps": [
                                {
                                    _sid(sid, f"b{i}", "call"): {
                                        "call": sub,
                                        "args": {"input": input_expr},
                                        "result": f"r{i}",
                                    }
                                },
                                {_sid(sid, f"b{i}", "save"): {"assign": [{f"{var}.b{i}": f"${{r{i}}}"}]}},
                            ]
                        }
                    }
                )
            collect = "${[" + ", ".join(f"{var}.b{i}" for i in range(len(branches))) + "]}"
            return [
                {_sid(prefix, name, "init"): {"assign": [{var: {}}]}},
                {sid: {"parallel": {"shared": [var], "branches": branches}}},
                self._store(prefix, name, st, collect, entry),
            ]
        if kind == "map":
            if st.get("retry") or st.get("catch"):
                self.warnings.append(f"{self.workflow}.{name}: retry/catch on map states is ignored on GCP")
            sub = self._sub(st["iterator"], f"{prefix}_{name}_it")
            items, res, out = _sid("items", prefix, name), _sid("res", prefix, name), _sid("out", prefix, name)
            items_src = read_expr(st.get("items_path"), read_expr(st.get("input_path")))
            parallel: Dict[str, Any] = {
                "shared": [res],
                "for": {
                    "value": "item",
                    "index": "i",
                    "in": "${" + items + "}",
                    "steps": [
                        {_sid(sid, "call"): {"call": sub, "args": {"input": "${item}"}, "result": "r"}},
                        {_sid(sid, "save"): {"assign": [{f"{res}[string(i)]": "${r}"}]}},
                    ],
                },
            }
            if st.get("max_concurrency"):
                parallel["concurrency_limit"] = int(st["max_concurrency"])
            return [
                {_sid(prefix, name, "init"): {"assign": [{items: "${" + items_src + "}"}, {res: {}}, {out: []}]}},
                {sid: {"parallel": parallel}},
                {
                    _sid(prefix, name, "collect"): {
                        "for": {
                            "value": "j",
                            "range": "${[0, len(" + items + ") - 1]}",
                            "steps": [
                                {_sid(sid, "append"): {"assign": [{out: f"${{list.concat({out}, {res}[string(j)])}}"}]}}
                            ],
                        }
                    }
                },
                self._store(prefix, name, st, "${" + out + "}", entry),
            ]
        raise ValueError(f"unknown state type {kind}")  # pragma: no cover

    def task(
        self, prefix: str, name: str, st: Dict[str, Any], entry: Dict[str, str], input_expr: str
    ) -> List[Dict[str, Any]]:
        sid = _sid(prefix, name)
        result_var = _sid("res", prefix, name)
        timeout = min(int(st.get("timeout_seconds") or _MAX_HTTP_TIMEOUT), _MAX_HTTP_TIMEOUT)
        call = {
            "call": "http.post",
            "args": {
                "url": self.url_of(st["function"]),
                "auth": {"type": "OIDC"},
                "timeout": timeout,
                "body": {"__pskit": "workflow", "data": input_expr},
            },
            "result": result_var,
        }
        steps: List[Dict[str, Any]] = []
        retry = st.get("retry") or []
        catch = st.get("catch") or []
        if len(retry) > 1:
            self.warnings.append(f"{self.workflow}.{name}: only the first retry rule is used on GCP")
        if not retry and not catch:
            steps.append({sid: call})
        else:
            body: Dict[str, Any] = {"try": call}
            if retry:
                rule = retry[0]
                pred = _sid(self.workflow, prefix, name, "retry_pred")
                self.subworkflows[pred] = {
                    "params": ["e"],
                    "steps": [
                        {
                            "check": {
                                "switch": [{"condition": _errors_condition(rule.get("errors", ["*"])), "return": True}]
                            }
                        },
                        {"no": {"return": False}},
                    ],
                }
                body["retry"] = {
                    "predicate": "${" + pred + "}",
                    "max_retries": int(rule.get("max_attempts", 3)),
                    "backoff": {
                        "initial_delay": max(1, float(rule.get("interval_seconds", 1))),
                        "max_delay": float(rule.get("max_delay_seconds") or 300),
                        "multiplier": float(rule.get("backoff_rate", 2.0)),
                    },
                }
            if catch:
                info = {
                    "error": '${default(map.get(e, ["body", "errorType"]), "Error")}',
                    "cause": '${default(map.get(e, ["body", "cause"]), "")}',
                }
                conds: List[Dict[str, Any]] = []
                for i, c in enumerate(catch):
                    assigns: List[Dict[str, Any]] = [{"_caught": c["next"]}]
                    target = assign_target(c.get("result_path", "$.error"))
                    if target is not None:
                        assigns.append({target: info})
                    conds.append(
                        {
                            "condition": _errors_condition(c.get("errors", ["*"])),
                            "steps": [{_sid(sid, f"catch{i}"): {"assign": assigns}}],
                        }
                    )
                conds.append({"condition": True, "raise": "${e}"})
                body["except"] = {"as": "e", "steps": [{_sid(sid, "except"): {"switch": conds}}]}
                steps.append({_sid(prefix, name, "pre"): {"assign": [{"_caught": ""}]}})
            steps.append({sid: body})
            if catch:
                route = [
                    {"condition": "${_caught == " + _lit(c["next"]) + "}", "next": entry[c["next"]]} for c in catch
                ]
                steps.append({_sid(prefix, name, "route"): {"switch": route}})
        steps.append(self._store(prefix, name, st, "${" + result_var + ".body}", entry))
        return steps


def compile_gcp(definition: Dict[str, Any], url_of: UrlResolver, workflow: str) -> Tuple[Dict[str, Any], List[str]]:
    """Return ``(workflow_source_dict, warnings)``."""
    comp = _Compiler(url_of, _sid(workflow))
    main = {"params": ["input"], "steps": comp.machine(definition, "s")}
    source: Dict[str, Any] = {"main": main}
    source.update(comp.subworkflows)
    return source, comp.warnings
