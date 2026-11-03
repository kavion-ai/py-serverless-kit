import pytest

from py_serverless_kit.config.schema import ScheduleEvent
from py_serverless_kit.providers import schedule as s


@pytest.mark.parametrize(
    "rate,cron",
    [
        ("1 minute", "* * * * *"),
        ("5 minutes", "*/5 * * * *"),
        ("120 minutes", "0 */2 * * *"),
        ("1 hour", "0 * * * *"),
        ("6 hours", "0 */6 * * *"),
        ("48 hours", "0 0 */2 * *"),
        ("1 day", "0 0 * * *"),
        ("7 days", "0 0 */7 * *"),
    ],
)
def test_rate_to_cron(rate, cron):
    assert s.rate_to_cron(rate) == cron


@pytest.mark.parametrize("rate", ["7 minutes", "5 hours", "45 days"])
def test_rate_not_expressible(rate):
    with pytest.raises(s.ScheduleError):
        s.rate_to_cron(rate)


@pytest.mark.parametrize(
    "event,expected",
    [
        (ScheduleEvent(rate="1 minute"), "rate(1 minute)"),
        (ScheduleEvent(rate="10 minutes"), "rate(10 minutes)"),
        (ScheduleEvent(cron="0 12 * * *"), "cron(0 12 * * ? *)"),
        (ScheduleEvent(cron="0 12 * * 1-5"), "cron(0 12 ? * 2-6 *)"),
        (ScheduleEvent(cron="30 8 * * 0,6"), "cron(30 8 ? * 1,7 *)"),
        (ScheduleEvent(cron="0 0 1 * *"), "cron(0 0 1 * ? *)"),
        (ScheduleEvent(cron="0 9 * * MON"), "cron(0 9 ? * MON *)"),
    ],
)
def test_aws(event, expected):
    assert s.aws_expression(event) == expected


def test_aws_rejects_dom_and_dow():
    with pytest.raises(s.ScheduleError):
        s.aws_expression(ScheduleEvent(cron="0 0 1 * 1"))


def test_other_dialects():
    ev = ScheduleEvent(rate="5 minutes")
    assert s.ncrontab(ev) == "0 */5 * * * *"
    assert s.ncrontab(ScheduleEvent(cron="0 2 * * *")) == "0 0 2 * * *"
    assert s.cron_with_seconds(ev) == "0 */5 * * * *"
    assert s.tencent_cron(ScheduleEvent(cron="0 2 * * *")) == "0 0 2 * * * *"
    assert s.every_expression(ev) == "@every 5m"
    assert s.every_expression(ScheduleEvent(rate="2 hours")) == "@every 2h"
    assert s.to_seconds(ScheduleEvent(rate="2 hours")) == 7200
