"""Cron and rate helpers used by the on-premises scheduler."""

from datetime import datetime, timezone

import pytest

from py_serverless_kit.runtime.cron import CronError, cron_matches, next_cron, rate_seconds


def test_rate_seconds():
    assert rate_seconds("5 minutes") == 300
    assert rate_seconds("1 hour") == 3600
    assert rate_seconds("2 days") == 172800
    with pytest.raises(CronError):
        rate_seconds("7")


def test_cron_dom_and_dow_are_or():
    # 09:00 on the 1st or on Monday. 2026-10-01 is a Thursday and the 1st.
    thursday = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    monday = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
    other = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)
    assert cron_matches("0 9 1 * 1", thursday)
    assert cron_matches("0 9 1 * 1", monday)
    assert not cron_matches("0 9 1 * 1", other)


def test_weekday_range_and_sunday():
    sunday = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)  # Sunday
    monday = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
    assert cron_matches("0 9 * * 1-5", monday)
    assert not cron_matches("0 9 * * 1-5", sunday)
    assert cron_matches("0 9 * * 0", sunday)
    assert cron_matches("0 9 * * 7", sunday)


def test_next_cron_skips_impossible_days():
    with pytest.raises(CronError):
        next_cron("0 0 31 2 *", datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_next_cron_is_strictly_after():
    monday = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
    nxt = next_cron("0 9 * * 1", monday)
    assert nxt.weekday() == 0  # Monday
    assert nxt > monday
