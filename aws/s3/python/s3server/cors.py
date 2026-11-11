"""Bucket CORS rules: parsing, matching a request's origin / method / headers, and validating a new configuration."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .errors import S3Error, invalid, malformed
from .store import Bucket
from .util import parse_xml, text


def _wild(pattern: str, value: str) -> bool:
    regex = "^" + ".*".join(re.escape(p).replace(r"\?", ".") for p in pattern.split("*")) + "$"
    return re.match(regex, value, re.IGNORECASE if pattern.lower().startswith("s3:") else 0) is not None


def cors_rules(bucket: Bucket) -> List[Dict[str, List[str]]]:
    if "cors" in bucket.parsed:
        return bucket.parsed["cors"]
    rules: List[Dict[str, List[str]]] = []
    raw = (bucket.meta.get("configs") or {}).get("cors")
    if raw:
        try:
            root = parse_xml(raw.encode())
            for rule in root.iter("CORSRule"):
                rules.append(
                    {
                        "origins": [(e.text or "").strip() for e in rule.findall("AllowedOrigin")],
                        "methods": [(e.text or "").strip().upper() for e in rule.findall("AllowedMethod")],
                        "headers": [(e.text or "").strip().lower() for e in rule.findall("AllowedHeader")],
                        "expose": [(e.text or "").strip() for e in rule.findall("ExposeHeader")],
                        "max_age": [text(rule, "MaxAgeSeconds")] if text(rule, "MaxAgeSeconds") else [],
                    }
                )
        except S3Error:
            rules = []
    bucket.parsed["cors"] = rules
    return rules


def cors_match(bucket: Bucket, origin: str, method: str, req_headers: List[str]) -> Optional[Dict[str, str]]:
    for rule in cors_rules(bucket):
        if not any(_wild(o, origin) for o in rule["origins"]):
            continue
        if method not in rule["methods"]:
            continue
        if any(not any(_wild(a, h) for a in rule["headers"]) for h in req_headers if h):
            continue
        out = {
            "Access-Control-Allow-Origin": "*" if rule["origins"] == ["*"] else origin,
            "Access-Control-Allow-Methods": ", ".join(rule["methods"]),
            "Vary": "Origin, Access-Control-Request-Headers, Access-Control-Request-Method",
        }
        if origin != "*" and rule["origins"] != ["*"]:
            out["Access-Control-Allow-Credentials"] = "true"
        if rule["expose"]:
            out["Access-Control-Expose-Headers"] = ", ".join(rule["expose"])
        if rule["max_age"]:
            out["Access-Control-Max-Age"] = rule["max_age"][0]
        if req_headers:
            out["Access-Control-Allow-Headers"] = ", ".join(req_headers)
        return out
    return None


def validate_cors(body: bytes) -> None:
    root = parse_xml(body)
    if root.tag != "CORSConfiguration":
        raise malformed()
    rules = root.findall("CORSRule")
    if not rules or len(rules) > 100:
        raise malformed()
    for rule in rules:
        methods = [(e.text or "").strip() for e in rule.findall("AllowedMethod")]
        if not methods or not rule.findall("AllowedOrigin"):
            raise malformed()
        for m in methods:
            if m not in ("GET", "PUT", "POST", "DELETE", "HEAD"):
                raise invalid(
                    f"Found unsupported HTTP method in CORS config. Unsupported method is {m}",
                    "CORSRule/AllowedMethod",
                    m,
                )
