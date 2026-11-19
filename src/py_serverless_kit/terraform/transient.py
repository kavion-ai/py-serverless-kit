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

An ``already exists`` error for a resource that did not fail earlier in the same deploy is usually left over from an
earlier deploy that failed half-way, or from a region change whose delete Azure had not finished yet. It becomes an
*adopt* candidate: the deployer imports it and keeps it only when its tags show that this service and stage created
it (:func:`owned_by`); otherwise it removes it from the state again and reports the original error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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
    # Exist in the cloud but unknown to this deploy: imported only when their pskit tags match (see ``owned_by``).
    adopt: List[Tuple[str, str]] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    settling: bool = False  # an error that needs the cloud to settle: wait before applying again


def _address(address: Optional[str], message: str) -> Optional[str]:
    if address:
        return address
    m = _ABSENT_ADDRESS.search(message)
    return m.group(1) if m else None


def recovery(errors: Iterable[Tuple[Optional[str], str]], seen: Set[str]) -> Optional[Recovery]:
    """The recovery for ``errors`` (``partial.parse_errors`` of a failed apply), or ``None`` when one is not transient.

    ``seen`` collects the addresses that failed transiently during this deploy; it is updated in place. An
    ``already exists`` error for one of them is imported at once: pskit created that resource a moment ago. Any other
    ``already exists`` error goes to ``adopt``, which the deployer imports only after checking the resource's tags,
    so pskit never takes over a resource it did not create.
    """
    found = list(errors)
    if not found:
        return None
    plan = Recovery()
    for address, message in found:
        addr = _address(address, message)
        exists = _EXISTS.search(message)
        if exists:
            if not addr or addr.startswith("data."):
                return None
            if addr in seen:
                plan.imports.append((addr, exists.group("id")))
                plan.reasons.append(f"{addr}: created a moment ago but not recorded; importing it")
            else:
                plan.adopt.append((addr, exists.group("id")))
                plan.reasons.append(f"{addr}: exists in the cloud but not in the state (left by an earlier deploy?); "
                                    "importing it if its pskit tags show this service and stage created it")
            continue
        if not addr or addr.startswith("data.") or not (_NOT_FOUND.search(message) or _ABSENT.search(message)):
            return None  # a data source reads something that must already exist: its 404 is real
        seen.add(addr)
        plan.settling = True
        if not _ABSENT.search(message):
            plan.untaint.append(addr)
        plan.reasons.append(f"{addr}: the cloud did not return it yet right after creating it")
    return plan


def resource_tags(state: Dict[str, Any], address: str) -> Optional[Dict[str, Any]]:
    """The ``tags`` of ``address`` (``[module.x.]type.name``) in a ``terraform state pull`` document, if any."""
    for res in state.get("resources") or []:
        if res.get("mode") != "managed":
            continue
        module = res.get("module")
        full = f"{module + '.' if module else ''}{res.get('type')}.{res.get('name')}"
        if full != address:
            continue
        for inst in res.get("instances") or []:
            tags = (inst.get("attributes") or {}).get("tags")
            if isinstance(tags, dict):
                return tags
        return None
    return None


def owned_by(tags: Optional[Dict[str, Any]], service: str, stage: str) -> bool:
    """True when ``tags`` are the ones pskit puts on every resource it creates for ``service``/``stage``."""
    if not tags:
        return False
    return (
        tags.get("managed-by") == "py-serverless-kit"
        and tags.get("pskit-service") == service
        and tags.get("pskit-stage") == stage
    )
