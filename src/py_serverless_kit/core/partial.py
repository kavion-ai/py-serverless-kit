"""Partial deploys: one function that cannot be deployed does not stop the others.

``pskit deploy`` (unless ``--all-or-nothing``) works in two places:

* **Before Terraform.** A configuration error that concerns one function only (``functions.<name>...``) skips that
  function, as does a zip bundle over the provider's size limit while other functions ship as images. The
  others are packaged and applied. A skipped function that was deployed before keeps that deployment: the apply
  targets every other resource (``-target``), so Terraform does not destroy it. On providers where one host runs
  every function (Azure Function App, on premises, DigitalOcean) it leaves the host.
* **During Terraform.** Terraform finishes every resource that does not depend on a failed one, then exits 1. The
  error blocks name the failed resources (``with <address>,``). Each is matched to the functions that own it, or
  that need it through the dependency graph of ``main.tf.json``.

The functions that were not deployed, with the reason, are printed at the end, saved in ``deployment.json``
(``not_deployed``) and shown in the studio. ``pskit deploy`` then exits with status 1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ..providers.base import Issue
from ..providers.descriptions import describe_type
from ..providers.terraform_doc import tf_id

_REF = re.compile(r"\b((?:data\.)?[a-z][a-z0-9_]*\.[A-Za-z_][A-Za-z0-9_-]*)")
_ERROR_WITH = re.compile(r"^\s*with ([^\s,]+),?\s*$")
_INDEX = re.compile(r"\[[^\]]*\]$")
MAX_REASON = 2000  # long enough for a whole AWS error (request id, image digest, message)

CONFIG = "configuration"
SIZE = "package size"
TERRAFORM = "terraform apply"


@dataclass
class NotDeployed:
    function: str
    step: str  # CONFIG | SIZE | TERRAFORM
    reason: str
    previous: str = ""  # what happened to a version deployed before

    def as_dict(self) -> Dict[str, str]:
        out = {"step": self.step, "reason": self.reason}
        if self.previous:
            out["previous"] = self.previous
        return out


# ------------------------------------------------------------------ before terraform
def function_errors(issues: Iterable[Issue], functions: Iterable[str]) -> Dict[str, List[str]]:
    """Errors that concern one function only (``where`` is ``functions.<name>`` or below it)."""
    names = sorted(functions, key=len, reverse=True)  # "api-v2" before "api"
    found: Dict[str, List[str]] = {}
    for issue in issues:
        if issue.level != "error" or not issue.where.startswith("functions."):
            continue
        rest = issue.where[len("functions."):]
        for name in names:
            if rest == name or rest.startswith(name + "."):
                found.setdefault(name, []).append(issue.message)
                break
    return found


# ------------------------------------------------------------------ resources of each function
def resource_addresses(tf: Dict[str, Any]) -> List[str]:
    return [f"{rtype}.{label}" for rtype, bodies in (tf.get("resource") or {}).items()
            if isinstance(bodies, dict) for label in bodies]


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def dependencies(tf: Dict[str, Any]) -> Dict[str, Set[str]]:
    """address -> addresses it references (``${...}`` expressions and ``depends_on``)."""
    known = set(resource_addresses(tf))
    graph: Dict[str, Set[str]] = {}
    for rtype, bodies in (tf.get("resource") or {}).items():
        if not isinstance(bodies, dict):
            continue
        for label, body in bodies.items():
            refs: Set[str] = set()
            for text in _strings(body):
                for expr in re.findall(r"\$\{([^}]*)\}", text):
                    refs.update(m for m in _REF.findall(expr) if m in known)
                if text in known:  # depends_on entries
                    refs.add(text)
            graph[f"{rtype}.{label}"] = refs - {f"{rtype}.{label}"}
    return graph


def owner(label: str, functions: Iterable[str]) -> Optional[str]:
    """The function a resource label belongs to (``hello``, ``logs_hello``, ``hello_apigw``...); longest name wins."""
    best: Optional[str] = None
    for name in functions:
        ident = tf_id(name)
        if label == ident or label.startswith(ident + "_") or label.endswith("_" + ident) or f"_{ident}_" in label:
            if best is None or len(tf_id(best)) < len(ident):
                best = name
    return best


def function_resources(tf: Dict[str, Any], functions: Iterable[str]) -> Dict[str, Set[str]]:
    """function -> its resources: those named after it, plus shared hosts (compute resources named after none)."""
    names = list(functions)
    own: Dict[str, Set[str]] = {n: set() for n in names}
    hosts: Set[str] = set()
    for address in resource_addresses(tf):
        rtype, label = address.split(".", 1)
        fn = owner(label, names)
        if fn is not None:
            own[fn].add(address)
        elif describe_type(rtype)[0] == "compute":
            hosts.add(address)  # e.g. the Azure Function App / App Service plan: every function runs on it
    return {n: own[n] | hosts for n in names}


def closure(start: Set[str], graph: Dict[str, Set[str]]) -> Set[str]:
    seen: Set[str] = set()
    todo = list(start)
    while todo:
        node = todo.pop()
        if node in seen:
            continue
        seen.add(node)
        todo.extend(graph.get(node, ()))
    return seen


# ------------------------------------------------------------------ terraform errors
def parse_errors(output: str) -> List[Tuple[Optional[str], str]]:
    """``(address or None, message)`` for every ``Error:`` block of terraform's (``-no-color``) output."""
    blocks: List[List[str]] = []
    for raw in output.splitlines():
        line = raw.strip("│╷╵ \t\r")
        if line.startswith("Error: "):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    found: List[Tuple[Optional[str], str]] = []
    for block in blocks:
        address: Optional[str] = None
        detail: List[str] = []
        for line in block[1:]:
            m = _ERROR_WITH.match(line)
            if m and address is None:
                address = _INDEX.sub("", m.group(1))
            elif line and not line.startswith("on ") and not re.match(r"^\d+:", line) and not line.startswith("("):
                detail.append(line)
        message = block[0][len("Error: "):].strip()
        if detail:
            message += ": " + " ".join(detail)
        found.append((address, message[:MAX_REASON]))
    return found


def failed_functions(
    tf: Dict[str, Any], functions: Iterable[str], errors: List[Tuple[Optional[str], str]]
) -> Dict[str, str]:
    """function -> reason, for the functions a failed apply did not (fully) deploy."""
    names = list(functions)
    graph = dependencies(tf)
    owned = function_resources(tf, names)
    failed: Dict[str, str] = {}
    general = [msg for address, msg in errors if not address]
    by_address = {address: msg for address, msg in errors if address}
    for name in names:
        needed = closure(owned[name], graph)
        reasons = [f"{address}: {msg}" for address, msg in sorted(by_address.items()) if address in needed]
        if reasons:
            failed[name] = "; ".join(reasons)[:MAX_REASON]
    if general and not by_address:
        # Not tied to a resource (credentials, provider configuration...): nothing can be trusted to be deployed.
        for name in names:
            failed.setdefault(name, "; ".join(general)[:MAX_REASON])
    return failed


# ------------------------------------------------------------------ report
def report_lines(not_deployed: List[NotDeployed], total: int) -> List[str]:
    if not not_deployed:
        return []
    done = total - len(not_deployed)
    lines = [f"Deployed {done} of {total} function(s). Not deployed ({len(not_deployed)}):"]
    for item in sorted(not_deployed, key=lambda n: n.function):
        lines.append(f"  {item.function}  [{item.step}]")
        lines.append(f"      reason: {item.reason}")
        if item.previous:
            lines.append(f"      {item.previous}")
    lines.append("Fix the reasons above and run `pskit deploy` again; the deployed functions are not touched twice.")
    return lines
