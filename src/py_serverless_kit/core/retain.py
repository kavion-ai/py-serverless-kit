"""``pskit remove --keep-resources``: destroy functions and triggers, keep the data.

Managed buckets, queues and topics are taken out of the Terraform state before
``terraform destroy``, so they stay in the cloud (with their objects and
messages) and pskit stops managing them. Providers name those resources
``b-<bucket>``, ``q-<queue>`` and ``t-<topic>`` (Terraform labels ``b_*``,
``q_*``, ``t_*``); infrastructure buckets such as the code-upload bucket use
other labels and are destroyed as usual.

On Azure the storage account, Service Bus namespace and resource group that
hold kept queues, containers or topics are kept too: destroying them would
delete their contents.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

KEPT_DIR = "kept"

# Terraform resource types that hold data, per provider.
DATA_TYPES: Dict[str, Tuple[str, ...]] = {
    "aws": ("aws_s3_bucket", "aws_s3_bucket_public_access_block", "aws_sqs_queue", "aws_sns_topic"),
    "gcp": ("google_storage_bucket", "google_pubsub_topic"),
    "azure": ("azurerm_storage_queue", "azurerm_storage_container", "azurerm_servicebus_topic"),
    "alibaba": ("alicloud_oss_bucket", "alicloud_message_service_topic", "alicloud_message_service_queue"),
    "tencent": ("tencentcloud_cos_bucket",),
    "huawei": ("huaweicloud_obs_bucket", "huaweicloud_smn_topic"),
    "oracle": ("oci_objectstorage_bucket",),
}
# Containers that must survive with what they hold (only when something is kept).
_PARENTS: Dict[str, Tuple[str, ...]] = {
    "azure": ("azurerm_storage_account", "azurerm_servicebus_namespace", "azurerm_resource_group"),
}
_DATA_LABEL = re.compile(r"^[bqt]_")
_ADDRESS = re.compile(r"^(?:module\.[^.]+\.)*([a-z0-9_]+)\.([A-Za-z0-9_-]+)(?:\[.*\])?$")


def kept_addresses(provider: str, state: Iterable[str]) -> List[str]:
    """The addresses from ``terraform state list`` that ``--keep-resources`` keeps."""
    types = DATA_TYPES.get(provider, ())
    kept: List[str] = []
    parents: List[str] = []
    for address in state:
        address = address.strip()
        match = _ADDRESS.match(address)
        if not match or address.startswith("data."):
            continue
        kind, label = match.groups()
        if kind in types and _DATA_LABEL.match(label):
            kept.append(address)
        elif kind in _PARENTS.get(provider, ()):
            parents.append(address)
    return kept + parents if kept else []


def supports(provider: str) -> bool:
    return provider in DATA_TYPES


# --------------------------------------------------------------------- state helpers


def _address(res: Dict[str, Any], index: Any = None) -> str:
    prefix = f"{res['module']}." if res.get("module") else ""
    base = f"{prefix}{res.get('type')}.{res.get('name')}"
    if index is None:
        return base
    return f"{base}[{json.dumps(index)}]"


def _instances(state: Dict[str, Any]) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any], str]]:
    for res in state.get("resources") or []:
        if res.get("mode") != "managed":
            continue
        for inst in res.get("instances") or []:
            yield res, inst, _address(res, inst.get("index_key"))


def _describe(res: Dict[str, Any], inst: Dict[str, Any], address: str, status: str) -> Dict[str, Any]:
    attrs = inst.get("attributes") or {}
    kind = str(res.get("type"))
    name = attrs.get("bucket") or attrs.get("name") or attrs.get("id") or res.get("name")
    noun = "bucket" if "bucket" in kind or "container" in kind or kind == "ibm_cos" else (
        "queue" if "queue" in kind else "topic" if "topic" in kind else "container"
    )
    return {
        "address": address,
        "type": kind,
        "kind": noun,
        "name": str(name),
        "id": str(attrs.get("arn") or attrs.get("id") or ""),
        "status": status,
    }


def data_resources(provider: str, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deployed buckets, queues and topics in ``state`` (``terraform state pull`` JSON)."""
    found = []
    for res, inst, address in _instances(state):
        label = str(res.get("name"))
        if res.get("type") in DATA_TYPES.get(provider, ()) and _DATA_LABEL.match(label):
            if str(res.get("type")).endswith("_public_access_block"):
                continue  # part of its bucket
            found.append(_describe(res, inst, address, "deployed"))
    return found


def _matches(res: Dict[str, Any], addresses: Iterable[str]) -> bool:
    base = _address(res)
    return any(a == base or a.startswith(base + "[") for a in addresses)


def save_kept(work_dir: Path, state: Dict[str, Any], addresses: List[str]) -> Path:
    """Copy the state of ``addresses`` into ``<work_dir>/kept/`` with just the provider configuration.

    That folder is a tiny Terraform workspace whose configuration declares no resources, so
    ``terraform destroy`` there deletes exactly the kept resources.
    """
    folder = work_dir / KEPT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    main = json.loads((work_dir / "main.tf.json").read_text("utf-8"))
    terraform = {k: v for k, v in (main.get("terraform") or {}).items() if k != "backend"}
    config: Dict[str, Any] = {"terraform": terraform}
    if main.get("provider"):
        config["provider"] = main["provider"]
    (folder / "main.tf.json").write_bytes((json.dumps(config, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    path = folder / "terraform.tfstate"
    if path.is_file():
        kept_state = json.loads(path.read_text("utf-8"))
        kept_state["serial"] = int(kept_state.get("serial") or 0) + 1
    else:
        kept_state = {
            "version": 4,
            "terraform_version": state.get("terraform_version") or "1.5.0",
            "serial": 1,
            "lineage": str(uuid.uuid4()),
            "outputs": {},
            "resources": [],
            "check_results": None,
        }
    have = {_address(r) for r in kept_state["resources"]}
    for res in state.get("resources") or []:
        if res.get("mode") == "managed" and _matches(res, addresses) and _address(res) not in have:
            kept_state["resources"].append(res)
    path.write_bytes(json.dumps(kept_state, indent=2).encode("utf-8"))
    return folder


def list_kept(work_dir: Path, provider: str = "") -> List[Dict[str, Any]]:
    path = work_dir / KEPT_DIR / "terraform.tfstate"
    if not path.is_file():
        return []
    try:
        state = json.loads(path.read_text("utf-8"))
    except ValueError:
        return []
    out = []
    for res, inst, address in _instances(state):
        if str(res.get("type")).endswith("_public_access_block"):
            continue
        out.append(_describe(res, inst, address, "kept"))
    return out


def delete_kept(
    work_dir: Path,
    addresses: Optional[List[str]] = None,
    *,
    binary: Optional[str] = None,
    echo: Callable[[str], None] = print,
) -> None:
    """Destroy kept resources (all of them, or ``addresses``) with the provider credentials of this machine."""
    from ..terraform.runner import TerraformRunner

    folder = work_dir / KEPT_DIR
    if not (folder / "terraform.tfstate").is_file():
        return
    runner = TerraformRunner(folder, binary=binary, echo=echo)
    runner.init()
    targets: List[str] = []
    for address in addresses or []:
        targets.append(address)
        if address.startswith("aws_s3_bucket."):
            # Its public access block goes with it.
            targets.append(address.replace("aws_s3_bucket.", "aws_s3_bucket_public_access_block.", 1))
    known = {r["address"] for r in list_kept(work_dir)} | {
        _address(res) for res in json.loads((folder / "terraform.tfstate").read_text("utf-8")).get("resources") or []
    }
    runner.destroy(auto_approve=True, targets=[t for t in targets if t in known] or None)
    if not list_kept(work_dir):
        shutil.rmtree(folder, ignore_errors=True)


__all__ = [
    "DATA_TYPES",
    "data_resources",
    "delete_kept",
    "kept_addresses",
    "list_kept",
    "save_kept",
    "supports",
]
