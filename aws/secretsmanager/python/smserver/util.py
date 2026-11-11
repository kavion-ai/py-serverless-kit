"""Time helpers: dates are epoch seconds, as the Secrets Manager API returns them."""

from __future__ import annotations

import time


def now() -> float:
    return round(time.time(), 3)


def today() -> float:
    """Midnight UTC of today: ``LastAccessedDate`` has a resolution of one day, as on AWS."""
    return float(int(time.time()) // 86400 * 86400)
