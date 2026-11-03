"""Live monitoring, alerts and data import for on-prem databases (and the CPU / memory of any service container).

* :func:`sample` measures every container of a service at once: CPU and memory (``docker stats``), how full the
  disk holding its data is (``df`` inside the container), and for PostgreSQL, MySQL, MariaDB and MongoDB the open
  connections, the data size and each replica's lag. The studio polls it while *Live monitoring* is switched on.
* :func:`check` compares a sample with the service's alert settings (``entry["alert"]``: CPU / memory / disk percent,
  replica lag in seconds, a container down) and, at most once per cooldown, calls an alert **function** of the
  project (through the deployed host, like a cluster capacity alert) and / or POSTs a **webhook** (Slack, Teams, any
  URL). :class:`Watcher` runs the checks while the studio is open; ``pskit resources onprem alerts KEY --check`` does
  it from a shell (cron).
* :func:`import_data` loads a dump (``.sql``, ``.sql.gz``, ``.dump``, MongoDB ``.archive``) into a new database
  right after it starts, before any replica copies it.

Only ``docker`` and ``ssh`` / ``scp`` commands run, as everywhere in on-prem services.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

Emit = Callable[[str], None]
RunFn = Callable[[List[str], Optional[Path]], Tuple[int, str]]

DB_ENGINES = ("postgres", "mysql", "mariadb", "mongodb")
DEFAULT_ALERT: Dict[str, Any] = {
    "enabled": False,
    "function": "",
    "stage": "",
    "webhook": "",
    "cooldown_minutes": 30,
    "interval_seconds": 60,
    "cpu": 90,
    "memory": 90,
    "disk": 85,
    "lag_seconds": 60,
    "down": True,
}
_PERCENTS = ("cpu", "memory", "disk")
_MAX_ALERTS = 50
# Dumps a new database can start from, by engine.
IMPORT_TYPES = {
    "postgres": (".sql", ".sql.gz", ".dump"),
    "mysql": (".sql", ".sql.gz"),
    "mariadb": (".sql", ".sql.gz"),
    "mongodb": (".archive", ".archive.gz", ".gz"),
}


def _svc() -> Any:
    from . import onprem_services

    return onprem_services


def _error(message: str) -> Exception:
    return _svc().ServiceError(message)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------------------------- sample


def _containers(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``{name, role, target, container}`` of every container of a service (members and load balancer)."""
    topo = entry.get("topology")
    if isinstance(topo, dict) and topo.get("mode") == "replicated":
        items = [{"name": m["name"], "role": m["role"], "server": m.get("server") or "", "target": m["target"],
                  "container": m["container"]} for m in topo["members"]]
        lb = topo.get("balancer")
        if lb:
            items.append({"name": "lb", "role": "balancer", "server": lb.get("server") or "", "target": lb["target"],
                          "container": lb["container"]})
        return items
    target = entry.get("target") or {"method": "local"}
    return [{"name": entry["key"], "role": "server", "server": str(target.get("server") or ""), "target": target,
             "container": entry["container"]}]


def _pct(text: str) -> Optional[float]:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", text or "")
    return float(match.group(1)) if match else None


def _stats(svc: Any, run: RunFn, item: Dict[str, Any], data_path: str) -> Dict[str, Any]:
    target, container = item["target"], item["container"]
    out: Dict[str, Any] = {k: v for k, v in item.items() if k != "target"}
    code, text = run(svc.docker_argv(target, ["inspect", "-f", "{{.State.Status}}", container]), None)
    out["state"] = (text.strip().splitlines() or ["missing"])[-1] if code == 0 else "missing"
    if out["state"] != "running":
        return out
    fmt = "{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}"
    code, text = run(svc.docker_argv(target, ["stats", "--no-stream", "--format", fmt, container]), None)
    parts = (text.strip().splitlines() or [""])[-1].split("|") if code == 0 else []
    if len(parts) == 5:
        out.update({"cpu": _pct(parts[0]), "memory": _pct(parts[1]), "memory_usage": parts[2].strip(),
                    "net_io": parts[3].strip(), "block_io": parts[4].strip()})
    if data_path and item["role"] != "balancer":
        script = f"df -Pk {data_path} 2>/dev/null | awk 'NR==2 {{print $3, $2}}'"
        code, text = run(svc.docker_argv(target, ["exec", container, "sh", "-c", script]), None)
        nums = (text.strip().splitlines() or [""])[-1].split()
        if code == 0 and len(nums) == 2 and all(n.isdigit() for n in nums) and int(nums[1]):
            out["disk"] = round(100.0 * int(nums[0]) / int(nums[1]), 1)
            out["disk_total_gb"] = round(int(nums[1]) / 1024 / 1024, 1)
    return out


_MONGO_AUTH = '-u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin'


def _db_script(service: str) -> str:
    """Prints ``connections=N`` and ``size_bytes=N`` on the primary / single server."""
    if service == "postgres":
        return ('psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "SELECT \'connections=\' || count(*) FROM '
                "pg_stat_activity\" -c \"SELECT 'size_bytes=' || COALESCE(sum(pg_database_size(datname)), 0) FROM "
                'pg_database"')
    if service in ("mysql", "mariadb"):
        client, pw = ("mysql", "MYSQL_ROOT_PASSWORD") if service == "mysql" else ("mariadb", "MARIADB_ROOT_PASSWORD")
        return (f'MYSQL_PWD="${pw}" {client} -uroot -N -e "SHOW GLOBAL STATUS LIKE \'Threads_connected\'; SELECT '  # noqa: S608 - fixed text
                "'size_bytes', COALESCE(SUM(data_length + index_length), 0) FROM information_schema.tables\" | "
                "awk '{print ($1 == \"Threads_connected\" ? \"connections\" : $1) \"=\" $2}'")
    if service == "mongodb":
        js = ("const s = db.serverStatus(); print('connections=' + s.connections.current); "
              "print('size_bytes=' + db.adminCommand({listDatabases: 1}).totalSize);")
        return f"mongosh --quiet {_MONGO_AUTH} --eval \"{js}\""
    return ""


def _lag_script(service: str) -> str:
    """Prints ``lag=<seconds>`` (``lag=stopped`` when replication is broken) on a replica."""
    if service == "postgres":
        return ('psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -c "SELECT \'lag=\' || CASE WHEN '
                "pg_last_wal_receive_lsn() IS NULL THEN 'stopped' WHEN pg_last_wal_receive_lsn() = "
                "pg_last_wal_replay_lsn() THEN '0' ELSE COALESCE(EXTRACT(EPOCH FROM now() - "
                "pg_last_xact_replay_timestamp())::int::text, '0') END\"")
    if service in ("mysql", "mariadb"):
        client, pw, field = (("mysql", "MYSQL_ROOT_PASSWORD", "Seconds_Behind_Source") if service == "mysql" else
                             ("mariadb", "MARIADB_ROOT_PASSWORD", "Seconds_Behind_Master"))
        status = "SHOW REPLICA STATUS" if service == "mysql" else "SHOW SLAVE STATUS"
        return (f'MYSQL_PWD="${pw}" {client} -uroot -e "{status}\\G" | awk -F": " \'/{field}:/ '
                "{v=$2} END {print \"lag=\" (v == \"\" || v == \"NULL\" ? \"stopped\" : v)}'")
    return ""


def _mongo_lag_script() -> str:
    """On the primary: ``lag:<host>=<seconds>`` for every secondary."""
    js = ("const st = rs.status(); const p = st.members.find((m) => m.stateStr === 'PRIMARY'); "
          "st.members.filter((m) => m.stateStr !== 'PRIMARY').forEach((m) => print('lag:' + m.name + '=' + "
          "(m.stateStr === 'SECONDARY' && p ? Math.max(0, Math.round((p.optimeDate - m.optimeDate) / 1000)) : "
          "'stopped')));")
    return f"mongosh --quiet {_MONGO_AUTH} --eval \"{js}\""


def _values(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key:
            out[key.strip()] = value.strip()
    return out


def sample(root: Path, key: str, *, run: Optional[RunFn] = None) -> Dict[str, Any]:
    """One measurement of a service: ``containers`` (state, cpu / memory / disk percent), ``database``
    (connections, size_mb) and ``lag`` (replica name -> seconds, or None when replication stopped)."""
    svc = _svc()
    entry = svc._entry(root, key)
    if entry.get("kind") == "runtime":
        raise _error(f"{key!r} is installed software, not a container")
    run_fn = run or svc._default_run
    service = str(entry.get("service"))
    spec = svc.SERVICES.get(service) or {}
    items = _containers(entry)
    with ThreadPoolExecutor(max_workers=min(8, len(items))) as pool:
        rows = list(pool.map(lambda i: _stats(svc, run_fn, i, str(spec.get("data") or "")), items))
    out: Dict[str, Any] = {"key": key, "service": service, "at": _now(), "containers": rows, "database": {},
                           "lag": {}}
    main = next((r for r in rows if r["role"] in ("primary", "server")), None)
    main_item = next((i for i in items if i["role"] in ("primary", "server")), None)
    script = _db_script(service)
    if main and main_item and main["state"] == "running" and script:
        code, text = run_fn(svc.docker_argv(main_item["target"], ["exec", main_item["container"], "sh", "-c", script]),
                            None)
        values = _values(text) if code == 0 else {}
        if values.get("connections", "").isdigit():
            out["database"]["connections"] = int(values["connections"])
        if values.get("size_bytes", "").isdigit():
            out["database"]["size_mb"] = round(int(values["size_bytes"]) / 1024 / 1024, 1)
    replicas = [i for i in items if i["role"] == "replica"]
    if replicas and service == "mongodb" and main_item and main and main["state"] == "running":
        code, text = run_fn(svc.docker_argv(main_item["target"], ["exec", main_item["container"], "sh", "-c",
                                                                   _mongo_lag_script()]), None)
        by_host = {k[4:]: v for k, v in _values(text).items() if k.startswith("lag:")}
        for member in entry["topology"]["members"]:
            if member["role"] == "replica":
                value = by_host.get(f"{member['link_host']}:{member['link_port']}")
                out["lag"][member["name"]] = int(value) if value and value.isdigit() else None
    elif replicas and _lag_script(service):
        for item, row in ((i, next(r for r in rows if r["name"] == i["name"])) for i in replicas):
            if row["state"] != "running":
                out["lag"][item["name"]] = None
                continue
            code, text = run_fn(svc.docker_argv(item["target"], ["exec", item["container"], "sh", "-c",
                                                                 _lag_script(service)]), None)
            value = _values(text).get("lag", "") if code == 0 else ""
            out["lag"][item["name"]] = int(value) if value.isdigit() else None
    return out


# ----------------------------------------------------------------------------------------------- alerts


def alert_settings(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {**DEFAULT_ALERT, **(entry.get("alert") or {})}


def check_alert(body: Any) -> Dict[str, Any]:
    """Validated alert settings from a request (missing keys keep their defaults)."""
    if body is None:
        return dict(DEFAULT_ALERT)
    if not isinstance(body, dict):
        raise _error("alert must be an object: {enabled, webhook, function, cpu, memory, disk, lag_seconds, ...}")
    out = dict(DEFAULT_ALERT)
    out["enabled"] = bool(body.get("enabled", True))
    for name in ("function", "stage", "webhook"):
        out[name] = str(body.get(name) or "").strip()
    if out["webhook"] and not out["webhook"].lower().startswith(("http://", "https://")):
        raise _error("alert.webhook must be an http(s) URL")
    if out["function"] and not re.match(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$", out["function"]):
        raise _error("alert.function must be the name of a function in pskit.yml")
    handler = str(body.get("function_handler") or "").strip()
    if handler:
        # A new function for the alerts: pskit.yml gets it with the resource (apply_to_raw).
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*\.[A-Za-z_][A-Za-z0-9_]*$", handler) or not out["function"]:
            raise _error("alert.function_handler must look like package.module.function, with alert.function")
        out["function_handler"] = handler
    for name in (*_PERCENTS, "lag_seconds", "cooldown_minutes", "interval_seconds"):
        if body.get(name) in (None, ""):
            continue
        try:
            value = int(body[name])
        except (TypeError, ValueError):
            raise _error(f"alert.{name} must be a number") from None
        if name in _PERCENTS and not 1 <= value <= 100:
            raise _error(f"alert.{name} is a percent: 1-100")
        if value < 1:
            raise _error(f"alert.{name} must be at least 1")
        out[name] = value
    out["interval_seconds"] = max(15, int(out["interval_seconds"]))
    out["down"] = bool(body.get("down", True))
    if out["enabled"] and not out["function"] and not out["webhook"]:
        raise _error("alerts need somewhere to go: a function of the project, a webhook URL, or both")
    return out


def reasons(measured: Dict[str, Any], settings: Dict[str, Any]) -> List[str]:
    """Why a sample breaks the thresholds (empty: all fine)."""
    out: List[str] = []
    for row in measured.get("containers") or []:
        who = f"{row['name']}" + (f" on {row['server']}" if row.get("server") else "")
        if row.get("state") != "running":
            if settings.get("down", True):
                out.append(f"{who} is {row.get('state') or 'missing'}")
            continue
        for name, label in (("cpu", "CPU"), ("memory", "memory"), ("disk", "disk")):
            value = row.get(name)
            if isinstance(value, (int, float)) and value >= float(settings[name]):
                out.append(f"{who}: {label} {value:g}% (limit {settings[name]}%)")
    for name, lag in (measured.get("lag") or {}).items():
        if lag is None:
            out.append(f"replica {name}: replication stopped")
        elif lag >= int(settings["lag_seconds"]):
            out.append(f"replica {name}: {lag} s behind the primary (limit {settings['lag_seconds']} s)")
    return out


def alert_event(entry: Dict[str, Any], measured: Dict[str, Any], why: List[str], *, test: bool = False
                ) -> Dict[str, Any]:
    """``event.data`` of the alert function (also the webhook's JSON body)."""
    key = entry["key"]
    message = (f"[pskit] test alert for {entry.get('service')} {key}" if test else
               f"[pskit] {entry.get('service')} {key}: " + "; ".join(why))
    return {"kind": "pskit.database.alert" if entry.get("role") == "database" else "pskit.service.alert",
            "test": test, "key": key, "service": entry.get("service"), "reasons": why if not test else ["test alert"],
            "message": message, "at": _now(), "sample": measured}


def _invoke(root: Path, settings: Dict[str, Any], event: Dict[str, Any]) -> None:
    """``POST /__pskit/invoke/<function>`` on the host of the deployed stage (``stage``, else any on-prem stage)."""
    from urllib.parse import quote

    from .onprem_control import WORK_DIR, HostControl, deployed_host

    stage = str(settings.get("stage") or "")
    spec: Dict[str, Any] = {}
    if stage:
        spec = (deployed_host(root, stage) or {}).get("spec") or {}
    else:
        for folder in sorted((Path(root) / WORK_DIR).glob("onprem-*")):
            spec = (deployed_host(root, folder.name[len("onprem-"):]) or {}).get("spec") or {}
            if spec:
                break
    if not spec:
        raise _error("no deployed on-prem stage to run the alert function on (deploy the project, or set alert.stage)")
    ssh = (spec.get("deploy") or {}).get("ssh") or None
    control = HostControl(str(spec.get("endpoint")), token=str(spec.get("admin_token") or ""), ssh=ssh,
                          remote_port=int(spec.get("port") or 8080), timeout=60)
    control.request("POST", "/__pskit/invoke/" + quote(str(settings["function"]), safe=""), event)


def send_alert(root: Path, key: str, measured: Dict[str, Any], why: List[str], *, test: bool = False
               ) -> Dict[str, Any]:
    """Call the alert function and / or POST the webhook, and record it in the service's alert history."""
    from .onprem_cluster import _post_webhook

    svc = _svc()
    entry = svc._entry(root, key)
    settings = alert_settings(entry)
    event = alert_event(entry, measured, why, test=test)
    sent: List[str] = []
    failures: List[str] = []
    if settings["function"]:
        try:
            _invoke(root, settings, event)
            sent.append(f"function {settings['function']}")
        except Exception as exc:  # noqa: BLE001 - reported in the history, the webhook still goes out
            failures.append(f"function {settings['function']}: {exc}")
    if settings["webhook"]:
        try:
            _post_webhook(settings["webhook"], event)
            sent.append("webhook")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"webhook: {exc}")
    if not settings["function"] and not settings["webhook"]:
        failures.append("no alert function or webhook is set")
    record = {"at": event["at"], "test": test, "message": event["message"], "sent": sent, "errors": failures}
    state = svc.load_state(root)
    item = state["services"].get(key)
    if isinstance(item, dict):
        item["alerts"] = (list(item.get("alerts") or []) + [record])[-_MAX_ALERTS:]
        if sent and not test:
            item["last_alert_ts"] = time.time()
        svc.save_state(root, state)
    return record


def check(root: Path, key: str, *, run: Optional[RunFn] = None, alert: bool = True,
          send: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    """A sample, the reasons it breaks the thresholds, and the alert (at most once per cooldown)."""
    svc = _svc()
    entry = svc._entry(root, key)
    settings = alert_settings(entry)
    measured = sample(root, key, run=run)
    why = reasons(measured, settings)
    out: Dict[str, Any] = {"sample": measured, "reasons": why, "checked_at": measured["at"]}
    if why and alert and settings["enabled"]:
        last = float(entry.get("last_alert_ts") or 0)
        wait = float(settings["cooldown_minutes"]) * 60
        if time.time() - last >= wait:
            out["alert"] = (send or send_alert)(root, key, measured, why)
        else:
            out["alert"] = {"skipped": "cooldown", "next_after_minutes": round((last + wait - time.time()) / 60, 1)}
    return out


def set_alert(root: Path, key: str, body: Any) -> Dict[str, Any]:
    """Save a service's alert settings (``enabled: false`` keeps them but stops checking)."""
    svc = _svc()
    entry = svc._entry(root, key)
    settings = check_alert({**alert_settings(entry), **(body if isinstance(body, dict) else {})})
    state = svc.load_state(root)
    state["services"][key]["alert"] = settings
    svc.save_state(root, state)
    return settings


class Watcher:
    """Checks the services whose alerts are on, each on its interval, while the studio runs."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last: Dict[str, Dict[str, Any]] = {}
        self._due: Dict[str, float] = {}

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="pskit-service-alerts", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(5):
            try:
                services = _svc().load_state(self.root)["services"]
            except Exception:  # noqa: BLE001, S112 - a half-written state file: try again next round
                continue
            for key, entry in services.items():
                settings = alert_settings(entry) if isinstance(entry, dict) else DEFAULT_ALERT
                if not settings["enabled"] or time.time() < self._due.get(key, 0):
                    continue
                self._due[key] = time.time() + int(settings["interval_seconds"])
                try:
                    result = check(self.root, key)
                    self.last[key] = {"checked_at": result["checked_at"], "reasons": result["reasons"],
                                      "alert": result.get("alert")}
                except Exception as exc:  # noqa: BLE001 - keep watching the others
                    self.last[key] = {"error": str(exc), "checked_at": _now()}


# ----------------------------------------------------------------------------------------------- import


def check_import(service: str, raw: Any) -> Optional[Dict[str, str]]:
    """``{"path": absolute file}`` of a dump to load into a new database, or None."""
    if raw in (None, "", {}):
        return None
    path_text = str(raw.get("path") if isinstance(raw, dict) else raw).strip()
    if not path_text:
        return None
    if service not in IMPORT_TYPES:
        raise _error(f"importing data is available for {', '.join(IMPORT_TYPES)}")
    path = Path(path_text).expanduser()
    if not path.is_file():
        raise _error(f"import: no file at {path}")
    name = path.name.lower()
    if not name.endswith(IMPORT_TYPES[service]):
        raise _error(f"import: {service} loads {', '.join(IMPORT_TYPES[service])} files, not {path.name}")
    return {"path": str(path.resolve()), "name": path.name, "size": str(path.stat().st_size)}


def _load_script(service: str, remote: str, name: str) -> str:
    gz = name.lower().endswith(".gz")
    cat = f"gunzip -c {remote}" if gz else f"cat {remote}"
    if service == "postgres":
        if name.lower().endswith(".dump"):
            return (f'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges {remote} 2>&1 '
                    "| tail -20; echo 'restored'")
        # pg_dumpall output recreates roles that exist already: keep going and show the last messages.
        return f'{cat} | psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q 2>&1 | tail -20; echo loaded'
    if service in ("mysql", "mariadb"):
        client, pw, db = (("mysql", "MYSQL_ROOT_PASSWORD", "MYSQL_DATABASE") if service == "mysql" else
                          ("mariadb", "MARIADB_ROOT_PASSWORD", "MARIADB_DATABASE"))
        return f'set -e; {cat} | MYSQL_PWD="${pw}" {client} -uroot "${db}"; echo loaded'
    archive = "--gzip " if gz else ""
    return f"mongorestore {_MONGO_AUTH} {archive}--archive={remote} 2>&1 | tail -20; echo restored"


def import_data(target: Dict[str, Any], container: str, service: str, spec: Dict[str, str], emit: Emit, *,
                run: Optional[RunFn] = None) -> None:
    """Copy the dump to the container (through the server over SSH) and load it."""
    import uuid

    from ..providers.onprem_remote import scp_argv

    svc = _svc()
    sh = svc._Runner(emit, run)
    name = spec["name"]
    suffix = re.sub(r"[^A-Za-z0-9.]", "", "".join(Path(name).suffixes)) or ".dump"
    inside = f"/tmp/pskit-import{suffix}"  # noqa: S108 - removed right after
    size_mb = int(spec.get("size") or 0) / 1024 / 1024
    emit(f"Importing {name} ({size_mb:.1f} MB) into {container}")
    if target.get("method") == "ssh":
        remote = f"/tmp/pskit-import-{uuid.uuid4().hex[:8]}{suffix}"  # noqa: S108
        sh(scp_argv(svc.ssh_options(target), spec["path"], remote))
        try:
            sh(svc.docker_argv(target, ["cp", remote, f"{container}:{inside}"]))
        finally:
            sh(svc._ssh_argv(target, f"rm -f {svc._shq(remote)}"), check=False, show=False)
    else:
        sh(["docker", "cp", spec["path"], f"{container}:{inside}"])
    try:
        sh(svc.docker_argv(target, ["exec", container, "sh", "-c", _load_script(service, inside, name)]))
    finally:
        sh(svc.docker_argv(target, ["exec", "-u", "0", container, "rm", "-f", inside]), check=False, show=False)
    emit(f"imported {name}")
