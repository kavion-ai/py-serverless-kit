"""Partial batch failure reporting for queue / topic / storage events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Union

from .event import Record


class BatchFailure(Exception):
    """Raised on providers without partial-batch support so the whole batch retries."""

    def __init__(self, failed_ids: List[str]) -> None:
        self.failed_ids = failed_ids
        super().__init__(f"{len(failed_ids)} record(s) failed: {', '.join(failed_ids[:10])}")


@dataclass
class BatchResult:
    """Return this from a batch handler to retry only the records that failed.

    On AWS SQS it becomes ``batchItemFailures``; on every other provider any
    failure makes the whole invocation fail (and therefore retry).
    """

    failed: List[str] = field(default_factory=list)

    def fail(self, record: Union[Record, str]) -> None:
        rid: Optional[str] = record.id if isinstance(record, Record) else record
        if rid is not None:
            self.failed.append(rid)

    @classmethod
    def of(cls, failed: Iterable[Union[Record, str]]) -> BatchResult:
        result = cls()
        for item in failed:
            result.fail(item)
        return result

    @property
    def ok(self) -> bool:
        return not self.failed

    def raise_if_failed(self) -> None:
        if self.failed:
            raise BatchFailure(self.failed)
