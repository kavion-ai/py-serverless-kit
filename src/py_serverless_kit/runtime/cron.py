"""5-field cron and rate schedules for the on-premises host.

Stdlib only, Python 3.9. A field is unrestricted only when it is a bare ``*``.
When both day-of-month and day-of-week are restricted, either one matching is
enough (standard cron). Day-of-week ``0`` and ``7`` are Sunday.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set, Tuple

_RATE = re.compile(r"^\s*(\d+)\s+(minute|minutes|hour|hours|day|days)\s*$", re.I)
_DOW = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
_MON = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


class CronError(ValueError):
    pass


def rate_seconds(rate: str) -> int:
    match = _RATE.match(rate or "")
    if not match:
        raise CronError(f"invalid rate {rate!r}; use '<n> minutes|hours|days'")
    value = int(match.group(1))
    if value <= 0:
        raise CronError("rate must be positive")
    unit = match.group(2).lower().rstrip("s")
    return value * {"minute": 60, "hour": 3600, "day": 86400}[unit]


def resolve_zone(name: str):
    """Return a tzinfo, or None when the name is not UTC and zone data is missing."""
    if not name or name.upper() == "UTC":
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, ModuleNotFoundError):
        return None


def _token(text: str, names: Optional[Dict[str, int]]) -> int:
    key = text.strip().lower()
    if names and key in names:
        return names[key]
    if key.isdigit():
        return int(key)
    raise CronError(f"invalid cron value {text!r}")


def _field(expr: str, low: int, high: int, names: Optional[Dict[str, int]] = None) -> Tuple[Set[int], bool]:
    text = (expr or "").strip().lower()
    if not text:
        raise CronError("empty cron field")
    if text == "*":
        return set(range(low, high + 1)), True
    values: Set[int] = set()
    for part in text.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            if not step_text.isdigit() or int(step_text) <= 0:
                raise CronError(f"invalid cron step {step_text!r}")
            step = int(step_text)
        if part in ("", "*"):
            start, end = low, high
        elif "-" in part:
            left, _, right = part.partition("-")
            start, end = _token(left, names), _token(right, names)
        else:
            start = end = _token(part, names)
        if start > end or step <= 0:
            raise CronError(f"invalid cron range {expr!r}")
        for number in range(start, end + 1, step):
            values.add(number)
    if not values:
        raise CronError(f"cron field {expr!r} matches nothing")
    return values, False


def parse_cron(expr: str) -> Tuple[Tuple[Set[int], bool], ...]:
    fields = (expr or "").split()
    if len(fields) != 5:
        raise CronError("cron must be 5 fields: min hour day month dow")
    minute, _ = _field(fields[0], 0, 59)
    hour, _ = _field(fields[1], 0, 23)
    day, day_star = _field(fields[2], 1, 31)
    month, _ = _field(fields[3], 1, 12, _MON)
    dow, dow_star = _field(fields[4], 0, 7, _DOW)
    if 7 in dow:
        dow.add(0)
        dow.discard(7)
    return (minute, False), (hour, False), (day, day_star), (month, False), (dow, dow_star)


def cron_matches(expr: str, when: datetime) -> bool:
    parsed = parse_cron(expr)
    minute, hour, day, month, dow = parsed
    # Python weekday(): Monday 0 .. Sunday 6. Cron: Sunday 0 .. Saturday 6.
    cron_dow = (when.weekday() + 1) % 7
    if when.minute not in minute[0] or when.hour not in hour[0] or when.month not in month[0]:
        return False
    day_ok = when.day in day[0]
    dow_ok = cron_dow in dow[0]
    if day[1] and dow[1]:
        return True
    if day[1]:
        return dow_ok
    if dow[1]:
        return day_ok
    return day_ok or dow_ok


def next_cron(expr: str, after: datetime, zone=None) -> datetime:
    """First minute strictly after ``after`` that matches. ``after`` may be naive (UTC)."""
    parse_cron(expr)  # fail fast on a bad expression
    tz = zone or timezone.utc
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    cursor = after.astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if cron_matches(expr, cursor):
            return cursor
        cursor += timedelta(minutes=1)
    raise CronError(f"cron {expr!r} does not match any minute in the next year")
