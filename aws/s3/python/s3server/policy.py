"""The bucket policy engine.

A statement applies to a request when its principal, action, resource and condition all match. ``evaluate_policy``
returns ``"deny"`` when any applicable statement denies, ``"allow"`` when one allows, else ``""``; ``access.allowed``
turns that into the final decision (ARCHITECTURE.md, "Bucket policies").
"""

from __future__ import annotations

import ipaddress
import json
import operator
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import ACCOUNT
from .util import as_list, parse_time

# A signed request may always read, replace or delete the policy, so the owner can repair a policy that locks it out.
POLICY_ACTIONS = ("s3:GetBucketPolicy", "s3:PutBucketPolicy", "s3:DeleteBucketPolicy")
# Condition keys that tie an Allow to a network, account or organization: such an Allow is not public.
RESTRICTING_KEYS = (
    "aws:sourceip",
    "aws:sourcevpc",
    "aws:sourcevpce",
    "aws:sourceaccount",
    "aws:sourcearn",
    "aws:principalaccount",
    "aws:principalorgid",
)
_TAG_KEY = "s3:existingobjecttag/"


class Context:
    """The requester and the condition key values of one request."""

    def __init__(self, principal: Optional[str], values: Dict[str, str]) -> None:
        self.principal = principal  # the access key id; None for an anonymous request
        self.values = {k.lower(): v for k, v in values.items()}

    def lookup(self, key: str, tags: Dict[str, str]) -> Optional[List[str]]:
        """The request's values of a condition key (case-insensitive), or None when the request has none."""
        low = key.lower()
        if low.startswith(_TAG_KEY):
            name = key[len(_TAG_KEY) :]
            return [tags[name]] if name in tags else None
        return [self.values[low]] if low in self.values else None


def parse_policy(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """The policy document, or None when there is none (or it is not a JSON object)."""
    if not raw:
        return None
    try:
        policy = json.loads(raw)
    except ValueError:
        return None
    return policy if isinstance(policy, dict) else None


def evaluate_policy(
    policy: Optional[Dict[str, Any]], action: str, resource: str, ctx: Context, tags: Dict[str, str]
) -> str:
    """ "deny", "allow" or "" for ``action`` on ``resource``; ``tags`` are the existing object's tags."""
    decision = ""
    for st in as_list((policy or {}).get("Statement")):
        if not isinstance(st, dict) or not _applies(st, action, resource, ctx, tags):
            continue
        if st.get("Effect") == "Deny":
            return "deny"
        if st.get("Effect") == "Allow":
            decision = "allow"
    return decision


def is_public_policy(policy: Optional[Dict[str, Any]]) -> bool:
    """True when an Allow statement lets anyone in without a restricting condition (policyStatus.IsPublic)."""
    for st in as_list((policy or {}).get("Statement")):
        if isinstance(st, dict) and st.get("Effect") == "Allow" and _for_everyone(st) and not _restricted(st):
            return True
    return False


# ----------------------------------------------------------------------------- statements


def _applies(st: Dict[str, Any], action: str, resource: str, ctx: Context, tags: Dict[str, str]) -> bool:
    return (
        _matches_principal(st, ctx.principal)
        and _matches(st, "Action", "NotAction", action, ignore_case=True)
        and _matches(st, "Resource", "NotResource", resource, ignore_case=False)
        and _conditions_hold(st.get("Condition"), ctx, tags)
    )


def _requester_ids(principal: Optional[str]) -> Tuple[str, ...]:
    """The principal values that name the requester: an anonymous request is only matched by "*"."""
    if principal is None:
        return ("*",)
    return ("*", ACCOUNT, f"arn:aws:iam::{ACCOUNT}:root", principal, f"arn:aws:iam::{ACCOUNT}:user/{principal}")


def _names_requester(value: Any, principal: Optional[str]) -> bool:
    if value == "*":
        return True
    if isinstance(value, dict):
        ids = _requester_ids(principal)
        return any(isinstance(v, str) and v in ids for v in as_list(value.get("AWS")))
    return False


def _matches_principal(st: Dict[str, Any], principal: Optional[str]) -> bool:
    if "Principal" in st:
        return _names_requester(st["Principal"], principal)
    if "NotPrincipal" in st:
        return not _names_requester(st["NotPrincipal"], principal)
    return False


def _matches(st: Dict[str, Any], field: str, not_field: str, value: str, *, ignore_case: bool) -> bool:
    if field in st:
        return any(_like(p, value, ignore_case) for p in as_list(st[field]) if isinstance(p, str))
    if not_field in st:
        return not any(_like(p, value, ignore_case) for p in as_list(st[not_field]) if isinstance(p, str))
    return False


def _like(pattern: str, value: str, ignore_case: bool) -> bool:
    """``*`` matches any run of characters, ``?`` any one character."""
    regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
    return re.fullmatch(regex, value, re.IGNORECASE | re.DOTALL if ignore_case else re.DOTALL) is not None


def _for_everyone(st: Dict[str, Any]) -> bool:
    if "NotPrincipal" in st:
        return True
    principal = st.get("Principal")
    return principal == "*" or (isinstance(principal, dict) and "*" in as_list(principal.get("AWS")))


def _restricted(st: Dict[str, Any]) -> bool:
    condition = st.get("Condition")
    if not isinstance(condition, dict):
        return False
    return any(
        isinstance(block, dict) and any(str(key).lower() in RESTRICTING_KEYS for key in block)
        for block in condition.values()
    )


# ----------------------------------------------------------------------------- conditions


def _numbers(compare: Callable[[float, float], bool]) -> Callable[[str, str], bool]:
    def test(value: str, wanted: str) -> bool:
        try:
            return compare(float(value), float(wanted))
        except ValueError:
            return False

    return test


def _when(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return parse_time(value)


def _dates(compare: Callable[[float, float], bool]) -> Callable[[str, str], bool]:
    def test(value: str, wanted: str) -> bool:
        left, right = _when(value), _when(wanted)
        return left is not None and right is not None and compare(left, right)

    return test


def _in_network(value: str, cidr: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None and network.version == 4:
        return address.ipv4_mapped in network
    return address.version == network.version and address in network


def _same_text(value: str, wanted: str) -> bool:
    return value == wanted


def _same_text_ignoring_case(value: str, wanted: str) -> bool:
    return value.lower() == wanted.lower()


def _string_like(value: str, wanted: str) -> bool:
    return _like(wanted, value, False)


# operator -> (test of one request value against one policy value, negated)
OPERATORS: Dict[str, Tuple[Callable[[str, str], bool], bool]] = {
    "StringEquals": (_same_text, False),
    "StringNotEquals": (_same_text, True),
    "StringEqualsIgnoreCase": (_same_text_ignoring_case, False),
    "StringNotEqualsIgnoreCase": (_same_text_ignoring_case, True),
    "StringLike": (_string_like, False),
    "StringNotLike": (_string_like, True),
    "NumericEquals": (_numbers(operator.eq), False),
    "NumericNotEquals": (_numbers(operator.eq), True),
    "NumericLessThan": (_numbers(operator.lt), False),
    "NumericLessThanEquals": (_numbers(operator.le), False),
    "NumericGreaterThan": (_numbers(operator.gt), False),
    "NumericGreaterThanEquals": (_numbers(operator.ge), False),
    "DateEquals": (_dates(operator.eq), False),
    "DateNotEquals": (_dates(operator.eq), True),
    "DateLessThan": (_dates(operator.lt), False),
    "DateLessThanEquals": (_dates(operator.le), False),
    "DateGreaterThan": (_dates(operator.gt), False),
    "DateGreaterThanEquals": (_dates(operator.ge), False),
    "Bool": (_same_text_ignoring_case, False),
    "IpAddress": (_in_network, False),
    "NotIpAddress": (_in_network, True),
}


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _conditions_hold(condition: Any, ctx: Context, tags: Dict[str, str]) -> bool:
    """Every operator of the condition block must hold (AND)."""
    if condition is None:
        return True
    if not isinstance(condition, dict):
        return False
    return all(_operator_holds(str(op), block, ctx, tags) for op, block in condition.items())


def _operator_holds(op: str, block: Any, ctx: Context, tags: Dict[str, str]) -> bool:
    qualifier = ""
    for prefix in ("ForAnyValue:", "ForAllValues:"):
        if op.startswith(prefix):
            qualifier, op = prefix[:-1], op[len(prefix) :]
    if_exists = op.endswith("IfExists")
    if if_exists:
        op = op[: -len("IfExists")]
    if not isinstance(block, dict):
        return False
    for key, wanted in block.items():
        values = ctx.lookup(str(key), tags)
        wanted_values = [_text(w) for w in as_list(wanted)]
        if op == "Null":
            # "true": the key must be missing; "false": it must be present.
            holds = any((w.lower() == "true") == (values is None) for w in wanted_values)
        elif op not in OPERATORS:
            return False
        elif values is None:
            holds = if_exists or OPERATORS[op][1]
        else:
            holds = _values_hold(values, wanted_values, OPERATORS[op], qualifier)
        if not holds:
            return False
    return True


def _values_hold(
    values: List[str], wanted: List[str], test: Tuple[Callable[[str, str], bool], bool], qualifier: str
) -> bool:
    """A request value holds when it matches any policy value (a negated operator: none of them)."""
    compare, negated = test

    def holds(value: str) -> bool:
        return any(compare(value, w) for w in wanted) != negated

    if qualifier == "ForAllValues":
        return all(holds(v) for v in values)
    return any(holds(v) for v in values)
