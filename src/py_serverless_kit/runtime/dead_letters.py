"""List and replay the messages of a dead-letter queue on any :class:`QueueDriver`.

Queue services cannot be read without receiving, so a walk claims messages, which hides them for ``VISIBILITY``
seconds, and gives back what it does not use when it ends. A message is deleted only after its copy was accepted by the
queue it goes to: a crash can replay one twice, but never loses one.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

VISIBILITY = 120.0
_BATCH = 10
_EMPTY_POLLS = 3  # some services answer empty now and then while messages wait
_NEVER = 1 << 30
SOURCE_ATTRIBUTE = "pskit_source_queue"
REPLAYS_ATTRIBUTE = "pskit_replays"
# What a move to the dead-letter queue added. The replayed message starts over without it.
_DEAD_ATTRIBUTES = (SOURCE_ATTRIBUTE, "pskit_receives", "pskit_error", "pskit_dead_at", "CloudPubSubDeadLetter")


def replay_attributes(attributes: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = {k: v for k, v in (attributes or {}).items() if not str(k).startswith(_DEAD_ATTRIBUTES) and not str(k).startswith("_")}
    try:
        out[REPLAYS_ATTRIBUTE] = int(out.get(REPLAYS_ATTRIBUTE) or 0) + 1
    except (TypeError, ValueError):
        out[REPLAYS_ATTRIBUTE] = 1
    return out


def public(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Without the keys a driver keeps for itself (receipts)."""
    return {k: v for k, v in msg.items() if not str(k).startswith("_")}


def _release(driver: Any, claimed: List[Dict[str, Any]], now: float) -> None:
    if claimed:
        driver.settle(claimed, {str(m["id"]) for m in claimed}, _NEVER, None, now)


def _walk(driver: Any, now: float, sleep: Callable[[float], None]) -> Iterable[List[Dict[str, Any]]]:
    empty = 0
    while empty < _EMPTY_POLLS:
        batch = list(driver.claim(_BATCH, VISIBILITY, now))
        if batch:
            empty = 0
            yield batch
        else:
            empty += 1
            if empty < _EMPTY_POLLS:
                sleep(0.5)


def page(
    driver: Any, offset: int, limit: int, now: float, *, ident: Optional[str] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> List[Dict[str, Any]]:
    """``limit`` messages after the first ``offset``, or just message ``ident``. All stay in the queue."""
    held: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    want = offset + limit
    try:
        for batch in _walk(driver, now, sleep):
            held.extend(batch)
            fresh = 0
            for msg in batch:
                if str(msg["id"]) not in seen:
                    seen[str(msg["id"])] = public(msg)
                    fresh += 1
            if (ident is not None and ident in seen) or (ident is None and len(seen) >= want) or not fresh:
                break
    finally:
        _release(driver, held, now)
    if ident is not None:
        return [seen[ident]] if ident in seen else []
    return list(seen.values())[offset:want]


def replay(
    driver: Any, submit: Callable[[str, str, Dict[str, Any]], Any], destination: Callable[[Dict[str, Any]], Optional[str]],
    ids: Optional[Iterable[str]], now: float, *, sleep: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Send messages ``ids`` (None: all) back with ``submit(queue, body, attributes)``.

    Returns ``replayed`` ({id, to}), ``failed`` ({id, error}; they stay in this queue) and ``missing`` (ids not found).
    """
    wanted: Optional[Set[str]] = None if ids is None else {str(i) for i in ids}
    done: Set[str] = set()
    tried: Set[str] = set()
    replayed: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    held: List[Dict[str, Any]] = []
    try:
        for batch in _walk(driver, now, sleep):
            finished: List[Dict[str, Any]] = []
            fresh = 0
            for msg in batch:
                ident = str(msg["id"])
                if ident in done:  # delivered twice by the service: the copy was already sent
                    finished.append(msg)
                    continue
                if ident in tried:
                    held.append(msg)
                    continue
                fresh += 1
                tried.add(ident)
                if wanted is not None and ident not in wanted:
                    held.append(msg)
                    continue
                to = destination(msg)
                if not to:
                    failed.append({"id": ident, "error": "the queue it came from is unknown: choose one with --to"})
                    held.append(msg)
                    continue
                try:
                    submit(to, str(msg.get("body") or ""), replay_attributes(msg.get("attributes")))
                except Exception as exc:  # noqa: BLE001 - reported per message; the message stays
                    failed.append({"id": ident, "error": f"{type(exc).__name__}: {exc}"})
                    held.append(msg)
                    continue
                done.add(ident)
                finished.append(msg)
                replayed.append({"id": ident, "to": to})
            if finished:
                driver.settle(finished, set(), _NEVER, None, now)
            if not fresh or (wanted is not None and wanted <= tried):
                break
    finally:
        _release(driver, held, now)
    return {"replayed": replayed, "failed": failed, "missing": sorted((wanted or set()) - tried)}
