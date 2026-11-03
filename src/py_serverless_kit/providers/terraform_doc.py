"""Builder for Terraform JSON configuration (``main.tf.json``).

Terraform reads ``*.tf.json`` natively. Generating JSON (instead of HCL text)
removes a whole class of quoting / escaping bugs.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..config.loader import deep_merge

_TF_REF = re.compile(r"\$\$\{\s*tf:([^}]+)\}")


def tf_id(name: str) -> str:
    """Make a valid Terraform block label from an arbitrary logical name."""
    ident = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not re.match(r"[A-Za-z_]", ident):
        ident = "_" + ident
    return ident


def ref(*parts: str) -> str:
    """``ref("aws_lambda_function", "hello", "arn")`` -> ``${aws_lambda_function.hello.arn}``."""
    return "${" + ".".join(parts) + "}"


def escape(value: str) -> str:
    """Escape literal ``${`` / ``%{`` so Terraform does not treat them as templates.

    The explicit ``${tf:<expression>}`` form is the one way to reference Terraform
    from user values, e.g. ``${tf:aws_dynamodb_table.orders.arn}`` in an IAM
    statement or environment variable.
    """
    escaped = value.replace("${", "$${").replace("%{", "%%{")
    return _TF_REF.sub(lambda m: "${" + m.group(1).strip() + "}", escaped)


class TerraformDoc:
    def __init__(self) -> None:
        self.terraform: Dict[str, Any] = {"required_providers": {}}
        self.providers: Dict[str, Any] = {}
        self.resources: Dict[str, Dict[str, Any]] = {}
        self.data_sources: Dict[str, Dict[str, Any]] = {}
        self.outputs: Dict[str, Any] = {}
        self.locals: Dict[str, Any] = {}
        self.variables: Dict[str, Any] = {}
        self._extra: Dict[str, Any] = {}
        self.warnings: List[str] = []

    # ----------------------------------------------------------------- blocks
    def required_provider(self, name: str, source: str, version: Optional[str] = None) -> None:
        spec: Dict[str, Any] = {"source": source}
        if version:
            spec["version"] = version
        self.terraform["required_providers"][name] = spec

    def required_version(self, constraint: str) -> None:
        self.terraform["required_version"] = constraint

    def backend(self, kind: str, config: Dict[str, Any]) -> None:
        self.terraform["backend"] = {kind: config}

    def provider(self, name: str, body: Dict[str, Any]) -> None:
        self.providers.setdefault(name, []).append(body)

    def resource(self, rtype: str, name: str, body: Dict[str, Any]) -> str:
        bucket = self.resources.setdefault(rtype, {})
        label = tf_id(name)
        if label in bucket:
            raise ValueError(f"duplicate terraform resource {rtype}.{label}")
        bucket[label] = body
        return f"{rtype}.{label}"

    def has_resource(self, rtype: str, name: str) -> bool:
        return tf_id(name) in self.resources.get(rtype, {})

    def data(self, dtype: str, name: str, body: Dict[str, Any]) -> str:
        bucket = self.data_sources.setdefault(dtype, {})
        label = tf_id(name)
        bucket.setdefault(label, body)
        return f"data.{dtype}.{label}"

    def output(self, name: str, value: Any, *, sensitive: bool = False, description: str = "") -> None:
        body: Dict[str, Any] = {"value": value}
        if sensitive:
            body["sensitive"] = True
        if description:
            body["description"] = description
        self.outputs[tf_id(name)] = body

    def local(self, name: str, value: Any) -> None:
        self.locals[name] = value

    def merge(self, extra: Dict[str, Any]) -> None:
        """Deep-merge user supplied raw Terraform JSON (escape hatch)."""
        self._extra = deep_merge(self._extra, extra)

    # ----------------------------------------------------------------- output
    def to_dict(self) -> Dict[str, Any]:
        doc: Dict[str, Any] = {"terraform": self.terraform}
        if self.providers:
            doc["provider"] = self.providers
        if self.variables:
            doc["variable"] = self.variables
        if self.locals:
            doc["locals"] = self.locals
        if self.data_sources:
            doc["data"] = self.data_sources
        if self.resources:
            doc["resource"] = self.resources
        if self.outputs:
            doc["output"] = self.outputs
        if self._extra:
            doc = deep_merge(doc, self._extra)
        return doc

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    def count(self) -> int:
        return sum(len(v) for v in self.resources.values())
