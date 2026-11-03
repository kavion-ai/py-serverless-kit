"""Live monitoring, alerts and data import of on-prem services; server check marks; settings export with pskit.yml."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from py_serverless_kit.core import onprem_monitor as mon
from py_serverless_kit.core import onprem_servers as srv
from py_serverless_kit.core import onprem_services as svc
from py_serverless_kit.core import settings_bundle as bundle

RAW = {"service": "shop", "provider": {"name": "onprem", "runtime": "python3.12"}, "package": {"source": "."},
       "functions": {"api": {"handler": "app.handlers.api"}}}


class FakeShell:
    """docker / ssh / scp answers: containers run, stats and df report numbers, the database counts."""

    def __init__(self, cpu: str = "12.5%", disk: str = "800 1000") -> None:
        self.calls: List[str] = []
        self.cpu, self.disk = cpu, disk

    def __call__(self, argv: List[str], stdout: Optional[Path]) -> Tuple[int, str]:
        text = " ".join(argv).replace("'\"'\"'", "'")
        self.calls.append(text)
        if "command -v docker" in text:
            return 0, "present"
        if "inspect" in text:
            return 0, "running"
        if " stats " in f" {text} ":
            return 0, f"{self.cpu}|40.0%|400MiB / 1GiB|1kB / 2kB|3MB / 4MB"
        if "df -Pk" in text:
            return 0, self.disk
        if "pg_stat_activity" in text:
            return 0, "connections=7\nsize_bytes=10485760"
        if "version" in argv and "--format" in argv:
            return 0, "27.1.0"
        return 0, ""

    def having(self, *parts: str) -> List[str]:
        return [c for c in self.calls if all(p in c for p in parts)]


def _postgres(root: Path, fake: FakeShell, **body):
    return svc.create(root, {"key": "orders", "service": "postgres", **body}, RAW, lambda _l: None, run=fake,
                      wait_seconds=1)


# ----------------------------------------------------------------------------------------------- alerts


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"enabled": True}, "somewhere to go"),
        ({"webhook": "ftp://x"}, "http"),
        ({"webhook": "https://x", "cpu": 120}, "1-100"),
        ({"webhook": "https://x", "lag_seconds": "soon"}, "a number"),
        ({"function": "1bad"}, "name of a function"),
        ({"function": "a", "function_handler": "nope"}, "package.module.function"),
    ],
)
def test_alert_settings_are_checked(body, message):
    with pytest.raises(svc.ServiceError, match=message):
        mon.check_alert(body)


def test_alert_defaults_and_disabled_alerts_need_no_destination():
    out = mon.check_alert({"webhook": "https://hooks.example/x", "disk": 70})
    assert out["enabled"] and out["disk"] == 70 and out["cpu"] == 90 and out["cooldown_minutes"] == 30
    assert mon.check_alert({"enabled": False})["enabled"] is False


def test_reasons_name_each_limit_that_is_crossed():
    settings = {**mon.DEFAULT_ALERT, "cpu": 50, "disk": 80, "lag_seconds": 30}
    sample = {"containers": [
        {"name": "primary", "server": "db1", "state": "running", "cpu": 75.0, "memory": 10.0, "disk": 81.0},
        {"name": "r1", "server": "db2", "state": "exited"},
    ], "lag": {"r1": None, "r2": 45}}
    why = mon.reasons(sample, settings)
    assert "primary on db1: CPU 75% (limit 50%)" in why and "primary on db1: disk 81% (limit 80%)" in why
    assert "r1 on db2 is exited" in why
    assert "replica r1: replication stopped" in why and "replica r2: 45 s behind the primary (limit 30 s)" in why
    assert mon.reasons(sample, {**settings, "down": False, "cpu": 99, "disk": 99, "lag_seconds": 99}) == [
        "replica r1: replication stopped"]


def test_sample_and_alert_once_per_cooldown(tmp_path):
    fake = FakeShell(cpu="97.1%")
    _postgres(tmp_path, fake, alert={"webhook": "https://hooks.example/x"})
    measured = mon.sample(tmp_path, "orders", run=fake)
    row = measured["containers"][0]
    assert (row["cpu"], row["memory"], row["disk"]) == (97.1, 40.0, 80.0)
    assert measured["database"] == {"connections": 7, "size_mb": 10.0}
    sent: List[List[str]] = []

    def send(root, key, sample, why):
        sent.append(why)
        record = {"sent": ["webhook"], "errors": []}
        state = svc.load_state(root)
        state["services"][key]["last_alert_ts"] = 10 ** 10  # just now (far future: inside any cooldown)
        svc.save_state(root, state)
        return record

    first = mon.check(tmp_path, "orders", run=fake, send=send)
    assert first["reasons"] == ["orders: CPU 97.1% (limit 90%)"] and first["alert"] == {"sent": ["webhook"],
                                                                                          "errors": []}
    second = mon.check(tmp_path, "orders", run=fake, send=send)
    assert second["alert"]["skipped"] == "cooldown" and len(sent) == 1


def test_send_alert_records_failures(tmp_path, monkeypatch):
    fake = FakeShell()
    _postgres(tmp_path, fake, alert={"webhook": "https://hooks.example/x"})

    def boom(url, event):
        raise OSError("no route")

    monkeypatch.setattr("py_serverless_kit.core.onprem_cluster._post_webhook", boom)
    record = mon.send_alert(tmp_path, "orders", {"containers": []}, ["x"])
    assert record["sent"] == [] and "no route" in record["errors"][0]
    assert svc.load_state(tmp_path)["services"]["orders"]["alerts"][-1]["errors"] == record["errors"]


def test_new_alert_function_goes_into_pskit_yml_with_the_resource(tmp_path):
    fake = FakeShell()
    entry = _postgres(tmp_path, fake, alert={"function": "orders-alert",
                                             "function_handler": "alerts.orders_alert.handler"})
    raw = svc.apply_to_raw(RAW, entry)
    assert raw["functions"]["orders-alert"]["handler"] == "alerts.orders_alert.handler"
    assert raw["resources"]["orders"]["type"] == "database"
    mine = {**RAW, "functions": {**RAW["functions"], "orders-alert": {"handler": "mine.x"}}}
    assert svc.apply_to_raw(mine, entry)["functions"]["orders-alert"]["handler"] == "mine.x"  # never replaced


# ----------------------------------------------------------------------------------------------- import


def test_import_checks_the_file(tmp_path):
    with pytest.raises(svc.ServiceError, match="no file"):
        mon.check_import("postgres", {"path": str(tmp_path / "missing.sql")})
    (tmp_path / "x.archive").write_text("a", "utf-8")
    with pytest.raises(svc.ServiceError, match="not x.archive"):
        mon.check_import("postgres", str(tmp_path / "x.archive"))
    with pytest.raises(svc.ServiceError, match="available for"):
        mon.check_import("redis", str(tmp_path / "x.archive"))
    assert mon.check_import("mongodb", str(tmp_path / "x.archive"))["name"] == "x.archive"
    assert mon.check_import("postgres", "") is None


def test_import_loads_the_dump_after_start(tmp_path):
    dump = tmp_path / "seed.sql.gz"
    dump.write_bytes(b"\x1f\x8b")
    fake = FakeShell()
    _postgres(tmp_path, fake, **{"import": {"path": str(dump)}})
    cp = fake.having("docker cp", "pskit-shop-orders:/tmp/pskit-import.sql.gz")
    load = fake.having("exec", "gunzip -c /tmp/pskit-import.sql.gz | psql")
    assert cp and load and fake.calls.index(cp[0]) < fake.calls.index(load[0])
    assert fake.having("rm", "-f", "/tmp/pskit-import.sql.gz")


def test_import_over_ssh_goes_through_the_server(tmp_path):
    dump = tmp_path / "seed.sql"
    dump.write_text("select 1;", "utf-8")
    fake = FakeShell()
    target = {"method": "ssh", "host": "10.0.0.9", "user": "ubuntu", "port": 22}
    mon.import_data(target, "pskit-shop-orders", "mysql", mon.check_import("mysql", str(dump)), lambda _l: None,
                    run=fake)
    assert fake.having("scp", str(dump), "ubuntu@10.0.0.9:/tmp/pskit-import-")
    assert fake.having("10.0.0.9", "docker", "cp", "pskit-shop-orders:/tmp/pskit-import.sql")
    assert fake.having("10.0.0.9", 'mysql -uroot "$MYSQL_DATABASE"')


# ----------------------------------------------------------------------------------------------- servers


def test_reachability_marks_open_and_closed_ssh_ports(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        open_port = listener.getsockname()[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed_port = probe.getsockname()[1]  # bound, not listening: refused
        servers = {"up": {"host": "127.0.0.1", "port": open_port}, "down": {"host": "127.0.0.1", "port": closed_port}}
        (tmp_path / ".pskit").mkdir()
        (tmp_path / ".pskit" / "onprem-servers.json").write_text(json.dumps({"servers": servers}), "utf-8")
        out = srv.reachability(tmp_path, timeout=1)
    assert out["up"]["ok"] is True and isinstance(out["up"]["ms"], int)
    assert out["down"]["ok"] is False and str(closed_port) in out["down"]["error"]


def test_server_metrics_parse_the_probe(tmp_path):
    (tmp_path / ".pskit").mkdir()
    (tmp_path / ".pskit" / "onprem-servers.json").write_text(
        json.dumps({"servers": {"edge": {"host": "10.0.0.5", "user": "u"}}}), "utf-8")

    def run(argv, stdout):
        return 0, ("cpu_a=cpu 100 0 100 700 100 0 0 0\ncpu_b=cpu 200 0 200 800 100 0 0 0\ncpus=4\n"
                   "mem_total_kb=4000000\nmem_avail_kb=1000000\ndisk_total_kb=1000\ndisk_used_kb=250\nload=0.1 0.2 0.3")

    m = srv.server_metrics(tmp_path, "edge", run=run)
    assert (m["cpu"], m["memory"], m["disk"], m["cpus"]) == (66.7, 75.0, 25.0, 4) and m["at"]


# ----------------------------------------------------------------------------------------------- settings


def test_settings_export_can_carry_pskit_yml(tmp_path):
    (tmp_path / ".pskit").mkdir()
    (tmp_path / ".pskit" / "onprem-servers.json").write_text(json.dumps({"servers": {}}), "utf-8")
    (tmp_path / "pskit.yml").write_text("service: shop\n", "utf-8")
    assert "pskit.yml" not in bundle.collect(tmp_path)["files"]
    payload = bundle.collect(tmp_path, config=True)
    assert "pskit.yml" in payload["files"]
    other = tmp_path / "other"
    other.mkdir()
    result = bundle.import_settings(other, payload)
    assert "pskit.yml" in result["written"] and (other / "pskit.yml").read_text("utf-8") == "service: shop\n"
