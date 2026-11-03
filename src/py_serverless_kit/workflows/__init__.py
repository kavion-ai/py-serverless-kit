"""Workflow (state machine) compilers.

One portable definition in ``pskit.yml`` -> AWS Step Functions (ASL), Google
Cloud Workflows, or the embedded engine in :mod:`py_serverless_kit.runtime.workflow`.
"""

from __future__ import annotations

from typing import Any, Dict

from ..config.schema import WorkflowDefinition

_CONFIG_ONLY = {"description", "enabled", "engine", "timeout", "options"}


def definition_dict(wf: WorkflowDefinition) -> Dict[str, Any]:
    """Plain-dict form consumed by the engine and the compilers."""
    raw = wf.model_dump(mode="json", exclude=_CONFIG_ONLY & set(type(wf).model_fields))
    return _clean(raw)


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "result_path":  # None is meaningful ("discard result")
                out[k] = v
            elif v is None or v == [] or (k == "end" and v is False):
                continue
            else:
                out[k] = _clean(v)
        return out
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value
