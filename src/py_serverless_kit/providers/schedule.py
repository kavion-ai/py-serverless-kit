"""Convert the portable schedule syntax into each provider's dialect.

The config accepts:

* ``rate: "<n> minutes|hours|days"``
* ``cron: "<min> <hour> <day-of-month> <month> <day-of-week>"`` (standard 5-field unix cron)
"""

from __future__ import annotations

import re
from typing import Tuple

from ..config.schema import ScheduleEvent

_RATE = re.compile(r"^\s*(\d+)\s+(minute|minutes|hour|hours|day|days)\s*$", re.I)


class ScheduleError(ValueError):
    pass


def parse_rate(rate: str) -> Tuple[int, str]:
    m = _RATE.match(rate)
    if not m:
        raise ScheduleError(f"invalid rate {rate!r}")
    value, unit = int(m.group(1)), m.group(2).lower().rstrip("s")
    if value <= 0:
        raise ScheduleError("rate must be positive")
    return value, unit  # unit in minute|hour|day


def rate_to_cron(rate: str) -> str:
    """Best-effort conversion of a rate to standard 5-field cron."""
    value, unit = parse_rate(rate)
    if unit == "minute":
        if value < 60 and 60 % value == 0:
            return "* * * * *" if value == 1 else f"*/{value} * * * *"
        if value % 60 == 0:
            return rate_to_cron(f"{value // 60} hours")
        raise ScheduleError(f"rate {rate!r} is not expressible as cron; use a divisor of 60 minutes")
    if unit == "hour":
        if value < 24 and 24 % value == 0:
            return "0 * * * *" if value == 1 else f"0 */{value} * * *"
        if value % 24 == 0:
            return rate_to_cron(f"{value // 24} days")
        raise ScheduleError(f"rate {rate!r} is not expressible as cron; use a divisor of 24 hours")
    if value == 1:
        return "0 0 * * *"
    if value <= 31:
        return f"0 0 */{value} * *"
    raise ScheduleError(f"rate {rate!r} is too long for cron")


def to_cron5(ev: ScheduleEvent) -> str:
    return ev.cron.strip() if ev.cron else rate_to_cron(ev.rate or "")


def to_seconds(ev: ScheduleEvent) -> int:
    value, unit = parse_rate(ev.rate or "")
    return value * {"minute": 60, "hour": 3600, "day": 86400}[unit]


# ----------------------------------------------------------------- dialects


def _aws_dow(field: str) -> str:
    """unix 0-6 (Sun=0) -> AWS 1-7 (Sun=1). Names pass through."""

    def conv(token: str) -> str:
        if token.isdigit():
            return str(int(token) % 7 + 1)
        return token

    out = []
    for part in field.split(","):
        step = ""
        if "/" in part:
            part, step = part.split("/", 1)
            step = "/" + step
        if "-" in part:
            a, b = part.split("-", 1)
            out.append(f"{conv(a)}-{conv(b)}{step}")
        else:
            out.append(conv(part) + step)
    return ",".join(out)


def aws_expression(ev: ScheduleEvent) -> str:
    if ev.rate:
        value, unit = parse_rate(ev.rate)
        return f"rate({value} {unit}{'' if value == 1 else 's'})"
    minute, hour, dom, month, dow = ev.cron.split()  # type: ignore[union-attr]
    if dow != "*" and dom == "*":
        dom = "?"
        dow = _aws_dow(dow)
    elif dow != "*" and dom != "*":
        raise ScheduleError("AWS cron cannot restrict both day-of-month and day-of-week")
    else:
        dow = "?"
    return f"cron({minute} {hour} {dom} {month} {dow} *)"


def ncrontab(ev: ScheduleEvent) -> str:
    """Azure Functions timer trigger: 6 fields, seconds first."""
    if ev.rate:
        value, unit = parse_rate(ev.rate)
        if unit == "minute" and value < 60:
            return f"0 */{value} * * * *"
    return "0 " + to_cron5(ev)


def cron_with_seconds(ev: ScheduleEvent) -> str:
    """Alibaba / Huawei style 6-field cron (seconds first)."""
    return "0 " + to_cron5(ev)


def tencent_cron(ev: ScheduleEvent) -> str:
    """Tencent SCF: 7 fields, seconds first, year last."""
    return "0 " + to_cron5(ev) + " *"


def every_expression(ev: ScheduleEvent) -> str:
    """``@every 5m`` style used by Alibaba FC and Huawei FunctionGraph."""
    if not ev.rate:
        raise ScheduleError("@every expressions require `rate`")
    value, unit = parse_rate(ev.rate)
    return f"@every {value}{unit[0]}"


_DOW_NAMES = ("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")


def named_cron5(ev: ScheduleEvent) -> str:
    """Standard 5-field cron with numeric day-of-week replaced by SUN..SAT.

    Clouds disagree on numeric weekdays (0=Sun vs 1=Sun); names are unambiguous.
    """
    minute, hour, dom, month, dow = to_cron5(ev).split()

    def conv(token: str) -> str:
        return _DOW_NAMES[int(token) % 7] if token.isdigit() else token

    parts = []
    for part in dow.split(","):
        base, slash, step = part.partition("/")
        if "-" in base:
            a, b = base.split("-", 1)
            base = f"{conv(a)}-{conv(b)}"
        else:
            base = conv(base)
        parts.append(base + slash + step)
    return " ".join([minute, hour, dom, month, ",".join(parts)])
