"""Order storage behind a tiny interface.

On AWS it uses the DynamoDB table that ``terraform.extra`` creates. Locally
(``PSKIT_PROVIDER=local``) it uses a dict, so ``pskit dev`` needs no
credentials. Swapping in Firestore / Cosmos DB for other clouds means adding
one class here; the handlers don't change.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Protocol


class OrderRepository(Protocol):
    def get(self, order_id: str) -> Optional[dict]: ...

    def put(self, order: dict) -> None: ...


class MemoryRepository:
    def __init__(self) -> None:
        self._items: Dict[str, dict] = {}

    def get(self, order_id: str) -> Optional[dict]:
        return self._items.get(order_id)

    def put(self, order: dict) -> None:
        self._items[order["id"]] = dict(order)


class DynamoRepository:
    def __init__(self, table_name: str) -> None:
        import boto3  # preinstalled in the Lambda runtime

        self._table = boto3.resource("dynamodb").Table(table_name)

    def get(self, order_id: str) -> Optional[dict]:
        return self._table.get_item(Key={"id": order_id}).get("Item")

    def put(self, order: dict) -> None:
        self._table.put_item(Item=order)


_REPO: Optional[OrderRepository] = None


def repository() -> OrderRepository:
    """Created once per cold start and reused by warm invocations."""
    global _REPO
    if _REPO is None:
        if os.environ.get("PSKIT_PROVIDER", "local") == "aws":
            _REPO = DynamoRepository(os.environ["ORDERS_TABLE"])
        else:
            _REPO = MemoryRepository()
    return _REPO
