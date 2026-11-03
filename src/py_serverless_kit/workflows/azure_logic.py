"""Compile a portable workflow definition to an Azure Logic Apps (Consumption) definition.

Logic Apps run a DAG of actions, while pskit workflows are state machines that may
loop. The compiled workflow is therefore a small interpreter:

* string variables ``data`` (the JSON-serialised state input/output) and ``state``
  (the current state name) are initialised from the HTTP request trigger;
* an ``Until`` loop runs a ``Switch`` on ``state`` with one case per state; each
  case does its work and sets ``state`` to the next one, ``__end__`` or ``__fail__``;
* after the loop a ``Response`` returns the output (200) or the error (500) and a
  failed run ends with ``Terminate``.

Task states ``POST`` the ``{"__pskit": "workflow", "data": ...}`` envelope to the
function app's ``/_pskit/invoke/<function>`` route (function-key auth); the Azure
adapter answers with the handler's JSON result or a 500 ``{"errorType", "cause"}``.
Parallel branches and map iterators are nested machines with their own variables.

Limitations (reported as warnings or errors by :func:`compile_logic_app`):

* only the first retry rule of a task is used, its ``errors`` filter and
  ``backoff_rate`` are not expressible (Logic Apps retries 408/429/5xx responses
  with its own exponential policy);
* retry / catch are honoured on ``task`` states only;
* map iterations run one at a time (``max_concurrency`` is ignored);
* ``matches`` supports globs of the form ``abc``, ``abc*``, ``*abc``, ``*abc*`` and ``*``;
* ``is_present`` cannot tell a missing key from ``null`` (both count as absent);
* ``result_path`` may not contain array indexes;
* Logic Apps allow 8 nested levels of loops/switches: deep parallel/map nesting is an error.

Variables cannot be read while they are being set, so every write of ``data``
goes through a per-machine ``tmp`` variable.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

UrlResolver = Callable[[str], str]

END = "__end__"
FAIL = "__fail__"
MAX_DEPTH = 8  # Logic Apps limit on nested Until/Switch/Foreach/If/Scope actions
MAX_ITERATIONS = 5000  # Until loop maximum
HTTP_TIMEOUT = 120  # outbound synchronous HTTP limit on multi-tenant Logic Apps
_ALL_ERRORS = ("*", "States.ALL")
_NAME_MAX = 80


class LogicAppsError(ValueError):
    """A definition that cannot be expressed as a Logic App."""


# --------------------------------------------------------------------- expression helpers


def _keys(path: Optional[str]) -> List[Any]:
    if not path or path == "$":
        return []
    from ..runtime.workflow import _tokens  # same JSON-path dialect as the engine

    return _tokens(path)


def quote(text: str) -> str:
    """A Logic Apps expression string literal."""
    return "'" + str(text).replace("'", "''") + "'"


def lit(value: Any) -> str:
    """Any JSON value as an expression."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return quote(value)
    return f"json({quote(json.dumps(value, separators=(',', ':')))})"


def plain(text: str) -> str:
    """A literal string property value (a leading ``@`` would start an expression)."""
    return "@" + text if text.startswith("@") else text


def read_expr(path: Optional[str], base: str) -> str:
    expr = base
    for key in _keys(path):
        expr += f"?[{key}]" if isinstance(key, int) else f"?[{quote(key)}]"
    return expr


def write_expr(path: Optional[str], base: str, value: str) -> str:
    """``base`` with ``value`` written at ``path`` (``$`` replaces, ``None`` keeps ``base``)."""
    if path is None:
        return base
    keys = _keys(path)
    if any(isinstance(k, int) for k in keys):
        raise LogicAppsError(f"result_path {path!r} uses an array index, which Logic Apps can't write")
    if not keys:
        return value

    def build(obj: str, rest: List[Any]) -> str:
        head = quote(rest[0])
        if len(rest) == 1:
            return f"setProperty({obj}, {head}, {value})"
        inner = f"coalesce({obj}?[{head}], json('{{}}'))"
        return f"setProperty({obj}, {head}, {build(inner, rest[1:])})"

    return build(base, keys)


def _any(exprs: List[str]) -> str:
    return exprs[0] if len(exprs) == 1 else f"or({', '.join(exprs)})"


def _glob(value: str, pattern: str) -> str:
    body = pattern.strip("*")
    if any(c in body for c in "*?[]"):
        raise LogicAppsError(f"matches pattern {pattern!r} can't be expressed in Logic Apps (use abc*, *abc or *abc*)")
    starts, ends = pattern.startswith("*"), pattern.endswith("*")
    if pattern and not body:
        return f"not(equals({value}, null))"
    if starts and ends:
        return f"contains(string({value}), {quote(body)})"
    if ends:
        return f"startsWith(string({value}), {quote(body)})"
    if starts:
        return f"endsWith(string({value}), {quote(body)})"
    return f"equals({value}, {quote(pattern)})"


def rule_expr(rule: Dict[str, Any], data: str) -> str:
    """A choice rule as a boolean expression over ``data`` (an object expression)."""
    if "and" in rule:
        parts = [rule_expr(r, data) for r in rule["and"]]
        return parts[0] if len(parts) == 1 else f"and({', '.join(parts)})"
    if "or" in rule:
        return _any([rule_expr(r, data) for r in rule["or"]])
    if "not" in rule:
        return f"not({rule_expr(rule['not'], data)})"
    v = read_expr(rule.get("variable", "$"), data)
    if "equals" in rule:
        return f"equals({v}, {lit(rule['equals'])})"
    if "not_equals" in rule:
        return f"not(equals({v}, {lit(rule['not_equals'])}))"
    for op, fn in (("gt", "greater"), ("gte", "greaterOrEquals"), ("lt", "less"), ("lte", "lessOrEquals")):
        if op in rule:
            bound = rule[op]
            # null never compares; substitute a value that makes the comparison false.
            if isinstance(bound, str):
                sentinel = quote("") if op in ("gt", "gte") else quote("\uffff")
            else:
                sentinel = "-1.7e308" if op in ("gt", "gte") else "1.7e308"
            check = f"{fn}(coalesce({v}, {sentinel}), {lit(bound)})"
            return f"and(not(equals({v}, null)), {check})"
    if "in" in rule:
        return f"contains({lit(list(rule['in']))}, {v})"
    if "contains" in rule:
        return f"contains(coalesce({v}, ''), {lit(rule['contains'])})"
    if "matches" in rule:
        return _glob(v, str(rule["matches"]))
    if "is_null" in rule:
        return f"equals({v}, null)" if rule["is_null"] else f"not(equals({v}, null))"
    if "is_present" in rule:
        return f"not(equals({v}, null))" if rule["is_present"] else f"equals({v}, null)"
    raise LogicAppsError(f"unsupported choice rule: {rule}")


def _uses(rule: Dict[str, Any], op: str) -> bool:
    if op in rule:
        return True
    nested = list(rule.get("and") or []) + list(rule.get("or") or [])
    if "not" in rule:
        nested.append(rule["not"])
    return any(_uses(r, op) for r in nested)


def _duration(seconds: float) -> str:
    return f"PT{max(1, int(round(seconds)))}S"


# --------------------------------------------------------------------- actions


def _setvar(name: str, value: Any) -> Dict[str, Any]:
    return {"type": "SetVariable", "inputs": {"name": name, "value": value}}


def _chain(steps: List[Tuple[str, Dict[str, Any]]], first: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    """Order actions one after another (``runAfter`` the previous one succeeded)."""
    out: Dict[str, Any] = {}
    prev: Optional[str] = None
    for name, action in steps:
        action = dict(action)
        if "runAfter" not in action:
            action["runAfter"] = {prev: ["Succeeded"]} if prev else dict(first or {})
        out[name] = action
        prev = name
    return out


class _Machine:
    def __init__(self, prefix: str) -> None:
        tag = f"_{prefix}" if prefix else ""
        self.data = "data" + tag
        self.state = "state" + tag
        self.tmp = "tmp" + tag

    @property
    def obj(self) -> str:
        return f"json(variables({quote(self.data)}))"


class _Compiler:
    def __init__(self, url_of: UrlResolver, key: str, workflow: str, timeout: str) -> None:
        self.url_of = url_of
        self.key = key
        self.workflow = workflow
        self.timeout = timeout
        self.variables: List[Dict[str, Any]] = [{"name": "err", "type": "string", "value": ""}]
        self.names: Dict[str, str] = {}
        self.warnings: List[str] = []
        self.max_depth = 0

    # ------------------------------------------------------------------ naming
    def name(self, *parts: str) -> str:
        raw = "_".join(p for p in parts if p)
        clean = re.sub(r"[^A-Za-z0-9_]", "_", raw)
        if len(clean) > _NAME_MAX:
            digest = hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:8]
            clean = clean[: _NAME_MAX - 9] + "_" + digest
        if clean in self.names and self.names[clean] != raw:
            digest = hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:8]
            clean = clean[: _NAME_MAX - 9] + "_" + digest
        self.names[clean] = raw
        return clean

    def _depth(self, depth: int) -> None:
        self.max_depth = max(self.max_depth, depth)
        if depth > MAX_DEPTH:
            raise LogicAppsError(
                f"workflow {self.workflow!r} nests parallel/map states too deeply for Logic Apps "
                f"({depth} levels, max {MAX_DEPTH})"
            )

    def _declare(self, m: _Machine, start: str, data: str = "") -> None:
        self.variables.append({"name": m.data, "type": "string", "value": data})
        self.variables.append({"name": m.state, "type": "string", "value": plain(start)})
        self.variables.append({"name": m.tmp, "type": "string", "value": ""})

    # ------------------------------------------------------------------ machines
    def machine(self, definition: Dict[str, Any], prefix: str, depth: int) -> Dict[str, Any]:
        """An ``Until`` action running ``definition`` (``depth`` = nesting level of the loop)."""
        m = _Machine(prefix)
        self._depth(depth + 1)  # the Switch inside the loop
        cases: Dict[str, Any] = {}
        for state_name, st in definition["states"].items():
            actions = self.state(m, prefix, state_name, st, depth + 2)
            cases[self.name("case", prefix, state_name)] = {"case": plain(state_name), "actions": actions}
        done = (
            f"or(equals(variables({quote(m.state)}), {quote(END)}), equals(variables({quote(m.state)}), {quote(FAIL)}))"
        )
        unknown = _chain(
            [
                (
                    self.name(prefix, "unknown_err"),
                    _setvar("err", '{"error": "States.Runtime", "cause": "unknown state"}'),
                ),
                (self.name(prefix, "unknown_state"), _setvar(m.state, FAIL)),
            ]
        )
        return {
            "type": "Until",
            "expression": "@" + done,
            "limit": {"count": MAX_ITERATIONS, "timeout": self.timeout},
            "actions": {
                self.name(prefix, "switch"): {
                    "type": "Switch",
                    "expression": f"@variables({quote(m.state)})",
                    "cases": cases,
                    "default": {"actions": unknown},
                    "runAfter": {},
                }
            },
        }

    def _write(self, m: _Machine, prefix: str, sid: str, value_expr: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Set ``data`` to ``value_expr`` (an object expression) through ``tmp``."""
        return [
            (self.name(prefix, sid, "tmp"), _setvar(m.tmp, f"@string({value_expr})")),
            (self.name(prefix, sid, "data"), _setvar(m.data, f"@variables({quote(m.tmp)})")),
        ]

    @staticmethod
    def _goto(st: Dict[str, Any]) -> str:
        """Name of the next state (raw: quote() it in expressions, plain() it as a literal)."""
        return str(st["next"]) if st.get("next") else END

    def state(self, m: _Machine, prefix: str, name: str, st: Dict[str, Any], depth: int) -> Dict[str, Any]:
        kind = st["type"]
        sid = re.sub(r"[^A-Za-z0-9_]", "_", name)
        data = m.obj
        inp = read_expr(st.get("input_path"), data)
        if kind == "task":
            return self.task(m, prefix, sid, st, inp)
        if kind != "parallel" and kind != "map" and (st.get("retry") or st.get("catch")):
            self.warnings.append(f"{self.workflow}.{name}: retry/catch is only honoured on task states on Azure")
        steps: List[Tuple[str, Dict[str, Any]]] = []
        if kind == "pass":
            value = lit(st["result"]) if "result" in st else inp
            steps += self._write(m, prefix, sid, write_expr(st.get("result_path", "$"), data, value))
            steps.append((self.name(prefix, sid, "next"), _setvar(m.state, plain(self._goto(st)))))
        elif kind == "wait":
            count: Any = max(0, int(st.get("seconds") or 0))
            if st.get("seconds_path"):
                count = f"@int({read_expr(st['seconds_path'], data)})"
            steps.append(
                (
                    self.name(prefix, sid, "wait"),
                    {"type": "Wait", "inputs": {"interval": {"count": count, "unit": "Second"}}},
                )
            )
            steps.append((self.name(prefix, sid, "next"), _setvar(m.state, plain(self._goto(st)))))
        elif kind == "choice":
            target = quote(st["default"]) if st.get("default") else quote(FAIL)
            for rule in reversed(st["choices"]):
                if _uses(rule, "is_present"):
                    self.warnings.append(
                        f"{self.workflow}.{name}: is_present treats null like a missing key on Azure Logic Apps"
                    )
                target = f"if({rule_expr(rule, data)}, {quote(rule['next'])}, {target})"
            if not st.get("default"):
                err = {"error": "States.NoChoiceMatched", "cause": name}
                steps.append((self.name(prefix, sid, "err"), _setvar("err", plain(json.dumps(err)))))
            steps.append((self.name(prefix, sid, "next"), _setvar(m.state, "@" + target)))
        elif kind == "succeed":
            steps.append((self.name(prefix, sid, "end"), _setvar(m.state, END)))
        elif kind == "fail":
            err = {"error": st.get("error") or "States.Fail", "cause": st.get("cause") or ""}
            steps.append((self.name(prefix, sid, "err"), _setvar("err", plain(json.dumps(err)))))
            steps.append((self.name(prefix, sid, "fail"), _setvar(m.state, FAIL)))
        elif kind == "parallel":
            return self.parallel(m, prefix, sid, st, inp, depth)
        elif kind == "map":
            return self.map(m, prefix, sid, st, inp, depth)
        else:  # pragma: no cover - the schema rejects other types
            raise LogicAppsError(f"unknown state type {kind}")
        return _chain(steps)

    # ------------------------------------------------------------------ task
    def task(self, m: _Machine, prefix: str, sid: str, st: Dict[str, Any], inp: str) -> Dict[str, Any]:
        call = self.name(prefix, sid, "call")
        timeout = min(int(st.get("timeout_seconds") or HTTP_TIMEOUT), HTTP_TIMEOUT)
        inputs: Dict[str, Any] = {
            "method": "POST",
            "uri": self.url_of(st["function"]),
            "headers": {"Content-Type": "application/json", "x-functions-key": self.key},
            "body": {"__pskit": "workflow", "data": "@" + inp},
            "retryPolicy": {"type": "none"},
        }
        retry = st.get("retry") or []
        if len(retry) > 1:
            self.warnings.append(f"{self.workflow}.{sid}: only the first retry rule is used on Azure Logic Apps")
        if retry:
            rule = retry[0]
            if not any(e in _ALL_ERRORS for e in rule.get("errors") or ["*"]):
                self.warnings.append(
                    f"{self.workflow}.{sid}: retry errors filter is ignored on Azure (Logic Apps retries 408/429/5xx)"
                )
            if float(rule.get("backoff_rate", 2.0)) != 2.0:
                self.warnings.append(f"{self.workflow}.{sid}: backoff_rate is ignored on Azure (exponential policy)")
            attempts = int(rule.get("max_attempts", 3))
            if attempts > 0:
                interval = min(max(5, int(round(float(rule.get("interval_seconds", 1))))), 86400)
                maximum = min(max(interval, int(float(rule.get("max_delay_seconds") or 3600))), 86400)
                inputs["retryPolicy"] = {
                    "type": "exponential",
                    "count": min(attempts, 90),
                    "interval": _duration(interval),
                    "minimumInterval": _duration(interval),
                    "maximumInterval": _duration(maximum),
                }
        http = {"type": "Http", "inputs": inputs, "limit": {"timeout": _duration(timeout)}, "runAfter": {}}
        data = m.obj
        ok = self._write(m, prefix, sid, write_expr(st.get("result_path", "$"), data, f"body({quote(call)})"))
        ok_next = (self.name(prefix, sid, "next"), _setvar(m.state, plain(self._goto(st))))

        error_name = f"coalesce(body({quote(call)})?['errorType'], 'Error')"
        error_obj = (
            f"setProperty(setProperty(json('{{}}'), 'error', {error_name}), "
            f"'cause', coalesce(body({quote(call)})?['cause'], 'task failed'))"
        )
        caught = "json(variables('err'))"
        target = quote(FAIL)
        new_data = data
        for rule in reversed(st.get("catch") or []):
            errors = rule.get("errors") or ["*"]
            match = "true" if any(e in _ALL_ERRORS for e in errors) else f"contains({lit(list(errors))}, {error_name})"
            target = f"if({match}, {quote(rule['next'])}, {target})"
            new_data = f"if({match}, {write_expr(rule.get('result_path', '$.error'), data, caught)}, {new_data})"
        failed = [
            (
                self.name(prefix, sid, "err"),
                {**_setvar("err", f"@string({error_obj})"), "runAfter": {call: ["Failed", "TimedOut"]}},
            ),
            *self._write(m, prefix, sid + "_catch", new_data),
            (self.name(prefix, sid, "route"), _setvar(m.state, "@" + target)),
        ]
        actions: Dict[str, Any] = {call: http}
        actions.update(_chain([*ok, ok_next], first={call: ["Succeeded"]}))
        actions.update(_chain(failed, first={call: ["Failed", "TimedOut"]}))
        # Join both trails so a handled failure leaves the case (and the loop) Succeeded.
        actions[self.name(prefix, sid, "done")] = {
            "type": "Compose",
            "inputs": "done",
            "runAfter": {ok_next[0]: ["Succeeded", "Skipped"], failed[-1][0]: ["Succeeded", "Skipped"]},
        }
        return actions

    # ------------------------------------------------------------------ parallel / map
    def parallel(self, m: _Machine, prefix: str, sid: str, st: Dict[str, Any], inp: str, depth: int) -> Dict[str, Any]:
        if st.get("retry") or st.get("catch"):
            self.warnings.append(f"{self.workflow}.{sid}: retry/catch on parallel states is ignored on Azure")
        actions: Dict[str, Any] = {}
        lasts: Dict[str, List[str]] = {}
        subs: List[_Machine] = []
        for i, branch in enumerate(st["branches"]):
            sub_prefix = self.name(prefix, sid, f"b{i}")
            sub = _Machine(sub_prefix)
            subs.append(sub)
            self._declare(sub, branch["start_at"])
            loop = self.name(sub_prefix, "loop")
            steps = [
                (self.name(sub_prefix, "in"), _setvar(sub.data, f"@string({inp})")),
                (self.name(sub_prefix, "start"), _setvar(sub.state, plain(branch["start_at"]))),
                (loop, self.machine(branch, sub_prefix, depth)),
            ]
            actions.update(_chain(steps))
            lasts[loop] = ["Succeeded"]
        failed = _any([f"equals(variables({quote(s.state)}), {quote(FAIL)})" for s in subs])
        results = "createArray(" + ", ".join(s.obj for s in subs) + ")"
        data = m.obj
        value = f"if({failed}, {data}, {write_expr(st.get('result_path', '$'), data, results)})"
        steps = self._write(m, prefix, sid, value)
        steps.append(
            (self.name(prefix, sid, "next"), _setvar(m.state, f"@if({failed}, {quote(FAIL)}, {quote(self._goto(st))})"))
        )
        actions.update(_chain(steps, first=lasts))
        return actions

    def map(self, m: _Machine, prefix: str, sid: str, st: Dict[str, Any], inp: str, depth: int) -> Dict[str, Any]:
        if st.get("retry") or st.get("catch"):
            self.warnings.append(f"{self.workflow}.{sid}: retry/catch on map states is ignored on Azure")
        if st.get("max_concurrency") not in (None, 1):
            self.warnings.append(f"{self.workflow}.{sid}: map iterations run one at a time on Azure")
        sub_prefix = self.name(prefix, sid, "it")
        sub = _Machine(sub_prefix)
        iterator = st["iterator"]
        self._declare(sub, iterator["start_at"])
        out, states = self.name("out", sub_prefix), self.name("states", sub_prefix)
        self.variables.append({"name": out, "type": "array", "value": []})
        self.variables.append({"name": states, "type": "array", "value": []})
        each = self.name(prefix, sid, "each")
        self._depth(depth)  # the Foreach
        body = _chain(
            [
                (self.name(sub_prefix, "in"), _setvar(sub.data, f"@string(items({quote(each)}))")),
                (self.name(sub_prefix, "start"), _setvar(sub.state, plain(iterator["start_at"]))),
                (self.name(sub_prefix, "loop"), self.machine(iterator, sub_prefix, depth + 1)),
                (
                    self.name(sub_prefix, "collect"),
                    {"type": "AppendToArrayVariable", "inputs": {"name": out, "value": "@" + sub.obj}},
                ),
                (
                    self.name(sub_prefix, "status"),
                    {
                        "type": "AppendToArrayVariable",
                        "inputs": {"name": states, "value": f"@variables({quote(sub.state)})"},
                    },
                ),
            ]
        )
        failed = f"contains(variables({quote(states)}), {quote(FAIL)})"
        data = m.obj
        value = f"if({failed}, {data}, {write_expr(st.get('result_path', '$'), data, f'variables({quote(out)})')})"
        steps: List[Tuple[str, Dict[str, Any]]] = [
            (self.name(prefix, sid, "reset"), _setvar(out, "@createArray()")),
            (self.name(prefix, sid, "reset_states"), _setvar(states, "@createArray()")),
            (
                each,
                {
                    "type": "Foreach",
                    "foreach": "@" + read_expr(st.get("items_path"), inp),
                    "actions": body,
                    # Variables are set inside the loop: iterations must run one at a time.
                    "runtimeConfiguration": {"concurrency": {"repetitions": 1}},
                },
            ),
            *self._write(m, prefix, sid, value),
            (
                self.name(prefix, sid, "next"),
                _setvar(m.state, f"@if({failed}, {quote(FAIL)}, {quote(self._goto(st))})"),
            ),
        ]
        return _chain(steps)


def compile_logic_app(
    definition: Dict[str, Any],
    url_of: UrlResolver,
    workflow: str,
    *,
    key: str,
    timeout: Optional[int] = None,
    sync: bool = True,
) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[str]]:
    """Return ``([(action_name, action), ...], warnings)``: the top-level actions in run order.

    ``url_of(function)`` gives the invoke URL of a task function and ``key`` the
    ``x-functions-key`` value. The actions run after an HTTP request trigger.
    ``sync`` adds ``Response`` actions so the caller receives the output.
    """
    comp = _Compiler(url_of, key, workflow, _duration(timeout) if timeout else "PT1H")
    top = _Machine("")
    comp._declare(top, definition["start_at"], "@string(coalesce(triggerBody(), json('{}')))")
    loop = comp.machine(definition, "", 1)
    actions: List[Tuple[str, Dict[str, Any]]] = []
    for var in comp.variables:
        actions.append((comp.name("init", var["name"]), {"type": "InitializeVariable", "inputs": {"variables": [var]}}))
    actions.append(("run", loop))
    failed = f"@equals(variables('state'), {quote(FAIL)})"
    error = "@json(variables('err'))"
    fail_actions: List[Tuple[str, Dict[str, Any]]] = []
    ok_actions: Dict[str, Any] = {}
    if sync:
        fail_actions.append(
            (
                "respond_error",
                {"type": "Response", "kind": "Http", "inputs": {"statusCode": 500, "body": error}},
            )
        )
        ok_actions["respond"] = {
            "type": "Response",
            "kind": "Http",
            "inputs": {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": "@" + top.obj},
            "runAfter": {},
        }
    fail_actions.append(
        (
            "terminate",
            {
                "type": "Terminate",
                "inputs": {
                    "runStatus": "Failed",
                    "runError": {
                        "code": "@coalesce(json(variables('err'))?['error'], 'States.Fail')",
                        "message": "@string(coalesce(json(variables('err'))?['cause'], ''))",
                    },
                },
            },
        )
    )
    finish: Dict[str, Any] = {"type": "If", "expression": failed, "actions": _chain(fail_actions)}
    if ok_actions:
        finish["else"] = {"actions": ok_actions}
    actions.append(("finish", finish))
    chained = _chain(actions)
    ordered = list(chained.items())
    if sync:
        ordered.append(
            (
                "respond_timeout",
                {
                    "type": "Response",
                    "kind": "Http",
                    "inputs": {
                        "statusCode": 500,
                        "body": {"error": "States.Timeout", "cause": "the workflow loop failed or timed out"},
                    },
                    "runAfter": {"run": ["Failed", "TimedOut"]},
                },
            )
        )
    return ordered, comp.warnings


def check(definition: Dict[str, Any], workflow: str) -> List[str]:
    """Compile with placeholders; return warnings or raise :class:`LogicAppsError`."""
    _, warnings = compile_logic_app(definition, lambda f: f"https://example/{f}", workflow, key="key")
    return warnings


__all__ = ["LogicAppsError", "check", "compile_logic_app", "lit", "quote", "read_expr", "rule_expr", "write_expr"]
