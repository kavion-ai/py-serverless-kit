"""Terraform apply errors caused by cloud eventual consistency, and how to recover from them.

Azure Resource Manager can answer ``404`` for a resource it has just reported as created (for example a storage
account whose ``listKeys`` call runs 0.2 s after the create succeeded, or Application Insights read back right after
its create). ``azurerm`` does not retry those reads, so the apply fails although the resource exists:

* the create itself returned an error -> the resource is in the state, *tainted* (the next apply would destroy and
  recreate it, and race again);
* ``Provider produced inconsistent result after apply ... Root object was present, but now absent`` -> the resource
  is not in the state at all (the next apply fails with ``a resource with the ID ... already exists``).

:func:`recovery` turns the errors of a failed apply into the steps that make a retry succeed: wait, untaint what was
created, import what exists but was not recorded. It returns ``None`` as soon as one error is not of that kind, so a
real failure (quota, permissions, bad arguments) is reported at once and never retried.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set, Tuple

# A read right after a write that the cloud has not propagated yet.
_NOT_FOUND = re.compile(
    r"unexpected status 404|\bResourceNotFound\b|\bParentResourceNotFound\b|\bResourceGroupNotFound\b"
)
# azurerm: the create succeeded but the read-back found nothing.
_ABSENT = re.compile(r"Root object was present, but now absent")
_ABSENT_ADDRESS = re.compile(r"When applying changes to ([^\s,]+),")
# azurerm: the resource exists in the cloud but not in the state.
_EXISTS = re.compile(
    r'a resource with the ID "(?P<id>[^"]+)" already exists - to be managed via Terraform this resource needs to be '
    r"imported into the State"
)


@dataclass
class Recovery:
    """What to do before applying again."""

    untaint: List[str] = field(default_factory=list)
    imports: List[Tuple[str, str]] = field(default_factory=list)  # (address, cloud resource id)
    reasons: List[str] = field(default_factory=list)


def _address(address: Optional[str], message: str) -> Optional[str]:
    if address:
        return address
    m = _ABSENT_ADDRESS.search(message)
    return m.group(1) if m else None


def recovery(errors: Iterable[Tuple[Optional[str], str]], seen: Set[str]) -> Optional[Recovery]:
    """The recovery for ``errors`` (``partial.parse_errors`` of a failed apply), or ``None`` when one is not transient.

    ``seen`` collects the addresses that failed transiently during this deploy; it is updated in place. An
    ``already exists`` error is only recoverable for one of them: pskit then knows it created the resource itself a
    moment ago and imports it, and never adopts a resource it did not create.
    """
    found = list(errors)
    if not found:
        return None
    plan = Recovery()
    for address, message in found:
        addr = _address(address, message)
        exists = _EXISTS.search(message)
        if exists:
            if not addr or addr not in seen:
                return None
            plan.imports.append((addr, exists.group("id")))
            plan.reasons.append(f"{addr}: created a moment ago but not recorded; importing it")
            continue
        if not addr or addr.startswith("data.") or not (_NOT_FOUND.search(message) or _ABSENT.search(message)):
            return None  # a data source reads something that must already exist: its 404 is real
        seen.add(addr)
        if not _ABSENT.search(message):
            plan.untaint.append(addr)
        plan.reasons.append(f"{addr}: the cloud did not return it yet right after creating it")
    return plan
