"""Create, inspect, back up and remove the services on-premises functions use.

One call starts Redis, Valkey, RabbitMQ, an SQS-compatible queue (ElasticMQ),
PostgreSQL, MySQL, MariaDB, MongoDB, MinIO, Memcached or Mailpit as a Docker
container, either on this machine (``local``) or on any server reachable with
OpenSSH (``ssh``), which may or may not be the server the functions run on. It can
also install Python or Docker on an SSH server.

Each service produces a ``resources:`` entry (driver options and connection values)
that :func:`apply_to_raw` adds to ``pskit.yml``, optionally with a trigger on the
functions it is attached to. Passwords never go into ``pskit.yml``: they are written
to the project's on-prem env file (``provider.options.env_file``, default
``.env.onprem``), which the host loads at start, and referenced as ``<name>_env``.

What was created lives in ``.pskit/onprem-services.json`` (with the credentials, so
``.pskit/`` must stay out of version control). pskit runs no cloud API here: only
``docker`` and ``ssh`` / ``scp`` commands, shown in the output as they run.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlsplit

from . import onprem_monitor as monitor
from . import onprem_replication as replication
from . import onprem_s3, onprem_secretsmanager, onprem_smtp
from .onprem_apps import DEFAULT_USERS, NO_AUTH_APPS, SELF_LOGIN, apps
from .onprem_browser import browsers_for
from .onprem_runtimes import RUNTIME_SPECS, check_version, install_script

STATE_FILE = Path(".pskit") / "onprem-services.json"
BACKUP_DIR = Path(".pskit") / "backups"
DEFAULT_ENV_FILE = ".env.onprem"
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
_HOST = re.compile(r"^[A-Za-z0-9_.:\[\]-]{1,253}$")
_USER = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_.-]{0,63}$")
_IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,254}$")

Emit = Callable[[str], None]
# (argv, stdout file or None) -> (exit code, captured output). Injected by tests.
RunFn = Callable[[List[str], Optional[Path]], Tuple[int, str]]


class ServiceError(Exception):
    """A request that cannot be carried out; the message says what to change."""


def _svc(
    label: str,
    image: str,
    port: int,
    roles: Sequence[str],
    *,
    extra_ports: Sequence[int] = (),
    data: str = "",
    env: Optional[Dict[str, str]] = None,
    command: Sequence[str] = (),
    health: str = "",
    backup: str = "",
    backup_ext: str = "",
    notes: str = "",
    run_args: Sequence[str] = (),
    init: Any = "",
    gui: Sequence[Dict[str, Any]] = (),
    sidecars: Sequence[Dict[str, Any]] = (),
    connect: Optional[Dict[str, Any]] = None,
    generate: Optional[Dict[str, str]] = None,
    group: str = "",
    ready_path: str = "",
    data_owner: str = "",
    chown_volume: bool = False,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "init": init,
        "sidecars": [dict(c) for c in sidecars],
        "connect": dict(connect or {}),
        "generate": dict(generate or {}),
        "group": group,
        "gui": [dict(g) for g in gui],
        "label": label,
        "kind": "service",
        "image": image,
        "port": port,
        "extra_ports": list(extra_ports),
        "roles": list(roles),
        "data": data,
        "env": dict(env or {}),
        "command": list(command),
        "health": health,
        "backup": backup,
        "backup_ext": backup_ext,
        "notes": notes,
        "run_args": list(run_args),
    }
    if ready_path:
        out["ready_path"] = ready_path
    # uid:gid the process runs as. A bind-mounted data directory is created as the SSH user, which this
    # user cannot write; chown it before start. chown_volume: a Docker named volume needs the same fix
    # because the directory in the image is not already owned by that user.
    if data_owner:
        out["data_owner"] = data_owner
    if chown_volume:
        out["chown_volume"] = True
    return out


# `{password}`, `{user}`, `{database}`, `{bucket}`, `{name}` (the resource key), `{address}` and
# `{port}` are filled in when the service is created, plus each `generate` value (`{encryption_key}` ...) and
# `{container}`. `sidecars` are extra containers (a database, a cache) on a private network with the service,
# reachable from it as `{container}-<name>`. `connect` describes the resource pskit adds: `env` (names after
# PSKIT_<KEY>_, written to the env file) and `connection` (`{prefix}` is that PSKIT_<KEY>). `health`, `init` (once, after it is ready)
# and `backup` run inside the container with `sh -c`; backup writes to stdout.
# A role is the resource type the service is used as; `stream` is a queue on a Redis stream.
ROLE_TYPE = {"stream": "queue", "secrets": "custom"}

def _redis_start(binary: str, var: str) -> str:
    return (
        f'if [ "${var}_USER" = default ]; then exec {binary}-server --appendonly yes --requirepass "${var}_PASSWORD"; '
        f'else exec {binary}-server --appendonly yes --user default off --user "${var}_USER" on ">${var}_PASSWORD" '
        '"~*" "&*" "+@all"; fi'
    )


# Services that run without authentication in this setup (keep them on 127.0.0.1 or a private network).
NO_AUTH = ("elasticmq", "kafka", "apache-kafka", "memcached", "mailpit", "localstack", "fake-gcs", "smtp", *NO_AUTH_APPS)
# No pskit login either: the service asks you to create its admin account on the first visit.
NO_CREDENTIALS = (*NO_AUTH, *SELF_LOGIN)
DEFAULT_USER = {"redis": "default", "valkey": "default", "keydb": "default", "dragonfly": "default", **DEFAULT_USERS}
_PASSWORD_OK = re.compile(r"^[A-Za-z0-9!#%*+,.:=?@^_~-]{8,128}$")
_LOGIN_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,63}$")

# OpenBao (the open-source Vault fork): file storage in the volume, initialised on first start with one unseal
# key, unsealed on every start, KV v2 at secret/, and a token whose id is the service password.
_BAO_START = (
    "mkdir -p /openbao/file && cat > /tmp/pskit-bao.hcl <<'EOF'\n"
    'storage "file" { path = "/openbao/file" }\n'
    'listener "tcp" { address = "0.0.0.0:8200"\n  tls_disable = true }\n'
    "disable_mlock = true\nui = true\napi_addr = \"http://127.0.0.1:8200\"\nEOF\n"
    "bao server -config=/tmp/pskit-bao.hcl & pid=$!\n"
    "export BAO_ADDR=http://127.0.0.1:8200\n"
    "while :; do bao status >/dev/null 2>&1; c=$?; [ $c -ne 1 ] && break; sleep 1; done\n"
    "init=/openbao/file/pskit-init.json\n"
    "[ -s $init ] || bao operator init -key-shares=1 -key-threshold=1 -format=json > $init\n"
    "flat=$(tr -d ' \\n' < $init)\n"
    "key=$(echo \"$flat\" | sed 's/.*\"unseal_keys_b64\":\\[\"\\([^\"]*\\)\".*/\\1/')\n"
    "root=$(echo \"$flat\" | sed 's/.*\"root_token\":\"\\([^\"]*\\)\".*/\\1/')\n"
    "bao operator unseal \"$key\" >/dev/null\n"
    "if [ ! -f /openbao/file/pskit-ready ]; then\n"
    "  BAO_TOKEN=$root bao secrets enable -path=secret kv-v2 >/dev/null\n"
    "  BAO_TOKEN=$root bao token create -id=\"$PSKIT_TOKEN\" -policy=root -orphan -display-name=pskit >/dev/null\n"
    "  touch /openbao/file/pskit-ready\n"
    "fi\n"
    "wait $pid\n"
)

# Bitnami's entrypoint is pid 1 while it provisions (it even starts a temporary server, then stops it).
# /minio/health/ready during that window is not the server that keeps running. Wait until pid 1 is MinIO.
_MINIO_HEALTH = (
    "grep -q entrypoint /proc/1/cmdline && exit 1; "
    "grep -q setup.sh /proc/1/cmdline && exit 1; "
    "curl -fsS http://127.0.0.1:9000/minio/health/ready >/dev/null"
)

SERVICES: Dict[str, Dict[str, Any]] = {
    "redis": _svc(
        "Redis",
        "redis:7-alpine",
        6379,
        ("queue", "stream", "cache"),
        data="/data",
        env={"REDIS_USER": "{user}", "REDIS_PASSWORD": "{password}"},
        # `default` keeps requirepass; another user gets an ACL and the default user is disabled.
        command=("sh", "-c", _redis_start("redis", "REDIS")),
        health='redis-cli --user "$REDIS_USER" -a "$REDIS_PASSWORD" --no-auth-warning ping | grep -q PONG',
        backup='redis-cli --user "$REDIS_USER" -a "$REDIS_PASSWORD" --no-auth-warning SAVE >/dev/null '
        "&& cat /data/dump.rdb",
        backup_ext="rdb",
        notes="Queue (redis driver: leased lists), stream (redis_stream driver: consumer group, several hosts) "
        "or a cache for handlers.",
    ),
    "valkey": _svc(
        "Valkey",
        "valkey/valkey:8-alpine",
        6379,
        ("queue", "stream", "cache"),
        data="/data",
        env={"VALKEY_USER": "{user}", "VALKEY_PASSWORD": "{password}"},
        # `default` keeps requirepass; another user gets an ACL and the default user is disabled.
        command=("sh", "-c", _redis_start("valkey", "VALKEY")),
        health='valkey-cli --user "$VALKEY_USER" -a "$VALKEY_PASSWORD" --no-auth-warning ping | grep -q PONG',
        backup='valkey-cli --user "$VALKEY_USER" -a "$VALKEY_PASSWORD" --no-auth-warning SAVE >/dev/null '
        "&& cat /data/dump.rdb",
        backup_ext="rdb",
        notes="Open-source Redis fork; same redis and redis_stream drivers.",
    ),
    "rabbitmq": _svc(
        "RabbitMQ",
        "rabbitmq:3-management-alpine",
        5672,
        ("queue",),
        extra_ports=(15672,),
        data="/var/lib/rabbitmq",
        env={"RABBITMQ_DEFAULT_USER": "{user}", "RABBITMQ_DEFAULT_PASS": "{password}"},
        health="rabbitmq-diagnostics -q ping",
        backup="rabbitmqctl export_definitions -",
        backup_ext="definitions.json",
        notes="AMQP with manual acks through a small driver class pskit adds to your app (needs pika). "
        "Management UI on port 15672. Backups hold definitions (queues, users), not messages.",
        run_args=("--hostname", "pskit-rabbitmq"),
    ),
    "elasticmq": _svc(
        "ElasticMQ (SQS-compatible)",
        "softwaremill/elasticmq-native:1.6.11",
        9324,
        ("queue",),
        extra_ports=(9325,),
        notes="Amazon SQS API, used through the sqs driver. Keeps messages in memory: "
        "a restart empties it, so use it for development and tests. UI on port 9325.",
    ),
    "postgres": _svc(
        "PostgreSQL",
        "postgres:16-alpine",
        5432,
        ("database",),
        data="/var/lib/postgresql/data",
        env={"POSTGRES_USER": "{user}", "POSTGRES_PASSWORD": "{password}", "POSTGRES_DB": "{database}"},
        health='pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        backup='pg_dumpall -U "$POSTGRES_USER"',
        backup_ext="sql",
    ),
    "mysql": _svc(
        "MySQL",
        "mysql:8.4",
        3306,
        ("database",),
        data="/var/lib/mysql",
        env={
            "MYSQL_ROOT_PASSWORD": "{password}",
            "MYSQL_DATABASE": "{database}",
            "MYSQL_USER": "{user}",
            "MYSQL_PASSWORD": "{password}",
        },
        health='mysqladmin ping -h 127.0.0.1 -uroot -p"$MYSQL_ROOT_PASSWORD" --silent',
        backup='mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --all-databases --single-transaction',
        backup_ext="sql",
    ),
    "mariadb": _svc(
        "MariaDB",
        "mariadb:11",
        3306,
        ("database",),
        data="/var/lib/mysql",
        env={
            "MARIADB_ROOT_PASSWORD": "{password}",
            "MARIADB_DATABASE": "{database}",
            "MARIADB_USER": "{user}",
            "MARIADB_PASSWORD": "{password}",
        },
        health="healthcheck.sh --connect --innodb_initialized",
        backup='mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --all-databases --single-transaction',
        backup_ext="sql",
    ),
    "mongodb": _svc(
        "MongoDB",
        "mongo:7",
        27017,
        ("database",),
        data="/data/db",
        env={"MONGO_INITDB_ROOT_USERNAME": "{user}", "MONGO_INITDB_ROOT_PASSWORD": "{password}"},
        health="mongosh --quiet --eval 'db.runCommand({ping: 1}).ok' | grep -q 1",
        backup='mongodump --archive -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" '
        "--authenticationDatabase admin",
        backup_ext="archive",
    ),
    # MinIO no longer publishes images on Docker Hub or quay.io; Bitnami's archived build still
    # pulls anonymously. `image` can point at your own mirror.
    "minio": _svc(
        "MinIO (S3-compatible)",
        "bitnamilegacy/minio:2025.7.23",
        9000,
        ("storage",),
        extra_ports=(9001,),
        data="/bitnami/minio/data",
        # The image's USER is 1001, and its entrypoint only chowns the data directory when it is root.
        data_owner="1001:1001",
        chown_volume=True,
        env={"MINIO_ROOT_USER": "{user}", "MINIO_ROOT_PASSWORD": "{password}", "MINIO_DEFAULT_BUCKETS": "{bucket}"},
        health=_MINIO_HEALTH,
        init='mc alias set local http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null '
        "&& mc mb --ignore-existing local/{bucket}",
        backup="tar czf - -C /bitnami/minio/data .",
        backup_ext="tar.gz",
        notes="Buckets watched through the minio driver. Console on port 9001.",
    ),
    "kafka": _svc(
        "Kafka (Redpanda, single node)",
        "redpandadata/redpanda:v24.3.6",
        9092,
        ("queue",),
        data="/var/lib/redpanda/data",
        command=(
            "redpanda",
            "start",
            "--mode",
            "dev-container",
            "--smp",
            "1",
            "--memory",
            "1G",
            "--kafka-addr",
            "internal://0.0.0.0:9093,external://0.0.0.0:9092,docker://0.0.0.0:9095",
            "--advertise-kafka-addr",
            "internal://127.0.0.1:9093,external://{address}:{port},docker://{container}:9095",
        ),
        health="rpk cluster health -X brokers=127.0.0.1:9093 | grep -Eq 'Healthy:[[:space:]]+true'",
        init="rpk topic create {name} -X brokers=127.0.0.1:9093 || true",
        backup="tar czf - -C /var/lib/redpanda/data .",
        backup_ext="tar.gz",
        notes="Kafka API (Redpanda, no ZooKeeper). Consumed through a driver class pskit adds to your app "
        "(needs kafka-python). No authentication: keep the port on a private network.",
    ),
    "nats": _svc(
        "NATS JetStream",
        "nats:2.10-alpine",
        4222,
        ("queue",),
        extra_ports=(8222,),
        data="/data",
        env={"NATS_PASSWORD": "{password}"},
        command=("sh", "-c", 'exec nats-server -js -sd /data -m 8222 --user {user} --pass "$NATS_PASSWORD"'),
        health="wget -qO- 'http://127.0.0.1:8222/healthz?js-enabled-only=true' | grep -q ok",
        backup="tar czf - -C /data .",
        backup_ext="tar.gz",
        notes="A JetStream stream with a durable pull consumer, through a driver class pskit adds to your app "
        "(needs nats-py). Monitoring on port 8222.",
    ),
    "dragonfly": _svc(
        "Dragonfly (Redis-compatible)",
        "docker.dragonflydb.io/dragonflydb/dragonfly:v1.25.1",
        6379,
        ("queue", "stream", "cache"),
        data="/data",
        env={"DFLY_requirepass": "{password}"},
        health='redis-cli -a "$DFLY_requirepass" --no-auth-warning ping | grep -q PONG',
        backup='redis-cli -a "$DFLY_requirepass" --no-auth-warning SAVE >/dev/null && tar czf - -C /data .',
        backup_ext="tar.gz",
        notes="A faster Redis-compatible store: the same redis / redis_stream drivers and clients. Password only "
        "(user default).",
    ),
    "keydb": _svc(
        "KeyDB (Redis-compatible)",
        "eqalpha/keydb:latest",
        6379,
        ("queue", "stream", "cache"),
        data="/data",
        env={"KEYDB_USER": "{user}", "KEYDB_PASSWORD": "{password}"},
        command=("sh", "-c", _redis_start("keydb", "KEYDB")),
        health='keydb-cli --user "$KEYDB_USER" -a "$KEYDB_PASSWORD" --no-auth-warning ping | grep -q PONG',
        backup='keydb-cli --user "$KEYDB_USER" -a "$KEYDB_PASSWORD" --no-auth-warning SAVE >/dev/null '
        "&& cat /data/dump.rdb",
        backup_ext="rdb",
        notes="Multithreaded Redis fork: the same redis / redis_stream drivers and clients.",
    ),
    "apache-kafka": _svc(
        "Apache Kafka (KRaft, single node)",
        "apache/kafka:3.8.1",
        9092,
        ("queue",),
        data="/var/lib/kafka/data",
        env={
            "KAFKA_NODE_ID": "1",
            "KAFKA_PROCESS_ROLES": "broker,controller",
            "KAFKA_LISTENERS": "EXTERNAL://:9092,INTERNAL://:19092,DOCKER://:9095,CONTROLLER://:9093",
            "KAFKA_ADVERTISED_LISTENERS": "EXTERNAL://{address}:{port},INTERNAL://localhost:19092,DOCKER://{container}:9095",
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": "EXTERNAL:PLAINTEXT,INTERNAL:PLAINTEXT,DOCKER:PLAINTEXT,CONTROLLER:PLAINTEXT",
            "KAFKA_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
            "KAFKA_INTER_BROKER_LISTENER_NAME": "INTERNAL",
            "KAFKA_CONTROLLER_QUORUM_VOTERS": "1@localhost:9093",
            "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
            "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR": "1",
            "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR": "1",
            "KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS": "0",
            "KAFKA_LOG_DIRS": "/var/lib/kafka/data",
        },
        health="/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:19092 >/dev/null 2>&1",
        init="/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:19092 --create --if-not-exists --topic {name}",
        backup="tar czf - -C /var/lib/kafka/data .",
        backup_ext="tar.gz",
        notes="The Apache Kafka distribution (no ZooKeeper), consumed through the Kafka driver class pskit adds "
        "(needs kafka-python). No authentication: keep the port on a private network.",
    ),
    "lavinmq": _svc(
        "LavinMQ (AMQP 0.9.1)",
        "cloudamqp/lavinmq:latest",
        5672,
        ("queue",),
        extra_ports=(15672,),
        data="/var/lib/lavinmq",
        env={"LAVINMQ_APP_PASSWORD": "{password}"},
        health="lavinmqctl status >/dev/null 2>&1",
        init='lavinmqctl add_user {user} "$LAVINMQ_APP_PASSWORD" && lavinmqctl set_user_tags {user} administrator '
        '&& lavinmqctl set_permissions -p / {user} ".*" ".*" ".*" && (lavinmqctl delete_user guest || true)',
        backup="lavinmqctl definitions export /tmp/defs.json >/dev/null 2>&1 && cat /tmp/defs.json",
        backup_ext="definitions.json",
        notes="A light, fast AMQP broker that speaks RabbitMQ's protocol: the RabbitMQ driver class and clients work "
        "unchanged. Management UI on port 15672.",
        gui=({"port": 15672, "label": "Management UI", "login": "user"},),
    ),
    "azurite": _svc(
        "Azurite (Azure Blob + Queue emulator)",
        "mcr.microsoft.com/azure-storage/azurite:3.33.0",
        10000,
        ("queue", "storage"),
        extra_ports=(10001,),
        data="/data",
        env={"AZURITE_ACCOUNTS": "{user}:{account_key}"},
        command=(
            "azurite", "--blobHost", "0.0.0.0", "--queueHost", "0.0.0.0", "--location", "/data",  # noqa: S104 - inside the container
            "--skipApiVersionCheck", "--loose",
        ),
        backup="tar czf - -C /data .",
        backup_ext="tar.gz",
        notes="Azure Storage blobs (port 10000) and queues (10001) with your own account name and key: the "
        "azure_blob / azure_queue drivers and the Azure SDKs work unchanged. Browse it with Azure Storage Explorer.",
    ),
    "localstack": _svc(
        "LocalStack (SQS, S3, Secrets Manager)",
        "localstack/localstack:3.8",
        4566,
        ("queue", "storage", "secrets"),
        data="/var/lib/localstack",
        env={"SERVICES": "sqs,s3,secretsmanager,ssm", "PERSISTENCE": "1"},
        health="curl -fs localhost:4566/_localstack/health | grep -q '\"sqs\": \"\\(available\\|running\\)\"'",
        backup="tar czf - -C /var/lib/localstack .",
        backup_ext="tar.gz",
        notes="Amazon SQS, S3, Secrets Manager and SSM Parameter Store on one port: the sqs / s3 drivers, "
        "get_secret(), boto3 and the AWS CLI work with endpoint_url. Credentials are not checked (test / test). "
        "For development and tests.",
        gui=({"port": 4566, "path": "/_localstack/health", "label": "Status (JSON)", "login": "none"},),
    ),
    "openbao": _svc(
        "OpenBao (Vault-compatible secrets)",
        "openbao/openbao:2.1.0",
        8200,
        ("secrets",),
        data="/openbao/file",
        env={"PSKIT_TOKEN": "{password}", "SKIP_SETCAP": "1"},
        command=("sh", "-c", _BAO_START),
        health="BAO_ADDR=http://127.0.0.1:8200 bao status >/dev/null",
        backup="tar czf - -C /openbao/file .",
        backup_ext="tar.gz",
        notes="A secret manager with the HashiCorp Vault API (KV v2 at secret/): get_secret() / put_secret(), "
        "hvac, node-vault and the vault / bao CLI. The password is the access token. OpenBao's release images "
        "ship without its web UI, so use Browse secrets (pskit's UI: folders, versions, add / edit / delete). "
        "Backups hold the data and the unseal key: keep them safe.",
    ),
    "fake-gcs": _svc(
        "fake-gcs-server (Cloud Storage emulator)",
        "fsouza/fake-gcs-server:1.52",
        4443,
        ("storage",),
        data="/data",
        command=(
            "-scheme", "http", "-port", "4443", "-external-url", "http://{address}:{port}",
            "-backend", "filesystem", "-filesystem-root", "/data",
        ),
        backup="",
        notes="Google Cloud Storage JSON API: the gcs driver (emulator mode) and the google-cloud-storage library work "
        "with its endpoint. No authentication. For development and tests.",
    ),
    "rustfs": _svc(
        "RustFS (S3-compatible)",
        "rustfs/rustfs:latest",
        9000,
        ("storage",),
        extra_ports=(9001,),
        data="/data",
        # The image runs as user rustfs (uid 10001). A host directory owned by the SSH user is not writable.
        data_owner="10001:10001",
        ready_path="/health",
        env={
            "RUSTFS_ACCESS_KEY": "{user}",
            "RUSTFS_SECRET_KEY": "{password}",
            "RUSTFS_ADDRESS": ":9000",
            "RUSTFS_CONSOLE_ADDRESS": ":9001",
            "RUSTFS_CONSOLE_ENABLE": "true",
        },
        notes="An S3-compatible object store with a web console (port 9001), an alternative to MinIO: the s3 driver, "
        "boto3 and the AWS CLI work with its endpoint.",
        gui=({"port": 9001, "label": "Console", "login": "user"},),
    ),
    "memcached": _svc("Memcached", "memcached:1.6-alpine", 11211, ("cache",), notes="In-memory cache; nothing to back up."),
    "mailpit": _svc(
        "Mailpit (SMTP)",
        "axllent/mailpit:latest",
        1025,
        ("custom",),
        extra_ports=(8025,),
        notes="An SMTP server that keeps every mail for inspection (web UI on port 8025). For development and tests.",
    ),
    # Built by core/onprem_smtp.py (run arguments, resource, guide): Node.js smtp-server + mailparser.
    "smtp": _svc(
        "SMTP server (receive mail, Node.js)",
        "node:22-alpine",
        25,
        ("smtp",),
        data="/data",
        health=onprem_smtp.HEALTH,
        notes="Receives mail for your domains and runs the functions attached to it with the mail: from, to, cc, "
        "subject, text, html, headers and attachments (also in the Amazon SES event shape). Never relays. After "
        "creating it, How to use lists the DNS records (A, MX) to add at your domain provider.",
        group="Mail",
    ),
}

# Built by core/onprem_secretsmanager.py from aws/secretsmanager: pskit's AWS Secrets Manager compatible server.
for _name, _sm in onprem_secretsmanager.SERVICES.items():
    SERVICES[_name] = _svc(
        f"AWS Secrets Manager compatible ({_sm['lang']})",
        _sm["image"],
        onprem_secretsmanager.PORT,
        ("secrets",),
        data="/data",
        health=onprem_secretsmanager.health(_name),
        backup="tar czf - -C /data .",
        backup_ext="tar.gz",
        # The master key the values are encrypted with at rest (kept in the env file, reused on re-create).
        generate={"master_key": "b64_32"},
        notes=f"pskit's own Secrets Manager server ({_sm['lang']}, code in aws/secretsmanager): the Secrets Manager "
        "API with SigV4 authentication (user = access key ID, password = secret access key). boto3, the AWS SDKs, "
        "the AWS CLI and get_secret() work with its endpoint. Versions and stages, tags, delete with a recovery "
        "window, restore. Values are encrypted at rest (AES-256-GCM, a data key per version wrapped by a generated "
        "master key). Its own web console (/ui/) signs in with the same user and password.",
        gui=({"port": onprem_secretsmanager.PORT, "path": "/ui/", "label": "Secrets console", "login": "user"},),
    )

# Built by core/onprem_s3.py from aws/s3: pskit's Amazon S3 compatible server.
for _name, _s3 in onprem_s3.SERVICES.items():
    SERVICES[_name] = _svc(
        f"Amazon S3 compatible ({_s3['lang']})",
        _s3["image"],
        onprem_s3.PORT,
        ("storage",),
        data="/data",
        health=onprem_s3.health(_name),
        backup="tar czf - -C /data .",
        backup_ext="tar.gz",
        notes=f"pskit's own S3 server ({_s3['lang']}, code in aws/s3): the S3 API with SigV4 authentication (user = "
        "access key ID, password = secret access key). boto3, the AWS SDKs, the AWS CLI and the s3 driver work with "
        "its endpoint. Versioning, multipart uploads, presigned URLs, policies, CORS, lifecycle rules, object lock, "
        "website hosting. Its own web console (/ui/) signs in with the same user and password.",
        gui=({"port": onprem_s3.PORT, "path": "/ui/", "label": "S3 console", "login": "user"},),
    )

for _name, _path in (("azurite", "/"), ("fake-gcs", "/storage/v1/b"), ("elasticmq", "/"), ("mailpit", "/")):
    SERVICES[_name]["ready_path"] = _path

SERVICES.update(apps(_svc))
SERVICES["localstack"]["group"] = "AWS emulators"
SERVICES["azurite"]["group"] = "Object storage"

SERVICES["rabbitmq"]["gui"] = [{"port": 15672, "label": "Management UI", "login": "user"}]
SERVICES["elasticmq"]["gui"] = [{"port": 9325, "label": "Queue browser", "login": "none"}]
SERVICES["minio"]["gui"] = [{"port": 9001, "label": "Console", "login": "user"}]
SERVICES["nats"]["gui"] = [{"port": 8222, "label": "Monitoring (JSON)", "login": "none"}]
SERVICES["mailpit"]["gui"] = [{"port": 8025, "label": "Mailbox", "login": "none"}]

# Web UIs started next to a service that has none, on a private Docker network with it.
# `{target}` / `{target_port}` are the service container's name and port on that network.
COMPANIONS: Dict[str, Dict[str, Any]] = {
    "adminer": {
        "label": "Adminer (database UI)",
        "image": "adminer:4.8.1",
        "port": 8080,
        "default_port": 8089,
        "for": ("postgres", "mysql", "mariadb"),
        "env": {"ADMINER_DEFAULT_SERVER": "{target}:{target_port}"},
        "login": "the database user and password (server is filled in)",
        # Adminer has no login of its own: it always asks for the database login.
        "auth_env": (),
    },
    "redis-commander": {
        "label": "Redis Commander",
        "image": "rediscommander/redis-commander:latest",
        "port": 8081,
        "default_port": 8082,
        "for": ("redis", "valkey", "keydb", "dragonfly"),
        "env": {
            "REDIS_HOST": "{target}",
            "REDIS_PORT": "{target_port}",
            "REDIS_USERNAME": "{user}",
            "REDIS_PASSWORD": "{password}",
            "REDIS_LABEL": "{name}",
            "HTTP_USER": "admin",
            "HTTP_PASSWORD": "{gui_password}",
        },
        "login": "user admin, password in the env file",
        "password_login": True,
        "auth_env": ("HTTP_USER", "HTTP_PASSWORD"),
        "open_env": {},
    },
    "kafka-ui": {
        "label": "Kafka UI",
        "image": "provectuslabs/kafka-ui:v0.7.2",
        "port": 8080,
        "default_port": 8088,
        "for": ("kafka", "apache-kafka"),
        "env": {
            "KAFKA_CLUSTERS_0_NAME": "{name}",
            "KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS": "{target}:9095",
            "AUTH_TYPE": "LOGIN_FORM",
            "SPRING_SECURITY_USER_NAME": "admin",
            "SPRING_SECURITY_USER_PASSWORD": "{gui_password}",
        },
        "login": "user admin, password in the env file (sign-in page /auth)",
        "password_login": True,
        "auth_env": ("AUTH_TYPE", "SPRING_SECURITY_USER_NAME", "SPRING_SECURITY_USER_PASSWORD"),
        "open_env": {"AUTH_TYPE": "DISABLED"},
    },
    "mongo-express": {
        "label": "Mongo Express",
        "image": "mongo-express:1.0.2",
        "port": 8081,
        "default_port": 8081,
        "for": ("mongodb",),
        "env": {
            "ME_CONFIG_MONGODB_URL": "mongodb://{user}:{password}@{target}:{target_port}/?authSource=admin",
            "ME_CONFIG_BASICAUTH": "true",
            "ME_CONFIG_BASICAUTH_USERNAME": "{user}",
            "ME_CONFIG_BASICAUTH_PASSWORD": "{gui_password}",
        },
        "login": "the MongoDB user and password",
        "auth_env": ("ME_CONFIG_BASICAUTH", "ME_CONFIG_BASICAUTH_USERNAME", "ME_CONFIG_BASICAUTH_PASSWORD"),
        "open_env": {"ME_CONFIG_BASICAUTH": "false"},
        # Signs in with the service's own password unless you choose one for the UI.
        "service_password": True,
    },
}

RUNTIMES: Dict[str, Dict[str, Any]] = {
    "docker": {
        "label": "Docker",
        "kind": "runtime",
        "roles": [],
        "notes": "Installs and starts Docker on an SSH server (needed by every service above, and by method: docker).",
        "check": "docker --version",
    },
}

RUNTIMES["docker"]["group"] = "Languages and Docker"
for _name, _rt in RUNTIME_SPECS.items():
    RUNTIMES[_name] = {"label": _rt["label"], "kind": "runtime", "roles": [], "notes": _rt["notes"],
                       "check": _rt["check"], "group": _rt["group"]}

def _group_of(svc: Dict[str, Any]) -> str:
    roles = svc["roles"]
    if "secrets" in roles and len(roles) == 1:
        return "Secrets"
    if roles == ["storage"]:
        return "Object storage"
    if "database" in roles:
        return "Databases"
    if set(roles) & {"queue", "stream"}:
        return "Queues and streams" if "cache" not in roles else "Caches and queues"
    if "cache" in roles:
        return "Caches and queues"
    return "Tools"


def catalog() -> List[Dict[str, Any]]:
    """Everything that can be created, for forms and ``pskit resources catalog``."""
    out = []
    for name, svc in SERVICES.items():
        out.append(
            {
                "id": name,
                "label": svc["label"],
                "kind": "service",
                "image": svc["image"],
                "port": svc["port"],
                "extra_ports": svc["extra_ports"],
                "roles": svc["roles"],
                "backup": bool(svc["backup"]),
                "persistent": bool(svc["data"]),
                "auth": name not in NO_AUTH,
                "gui": [g["label"] for g in svc["gui"]],
                "companion": next((c["label"] for c in COMPANIONS.values() if name in c["for"]), None),
                "gui_logins": gui_login_choices(name),
                "default_user": DEFAULT_USER.get(name, "pskit"),
                "browsers": browsers_for(name),
                "replication": replication.catalog_info(name),
                "import_types": list(monitor.IMPORT_TYPES.get(name, ())),
                "group": svc.get("group") or _group_of(svc),
                "notes": svc["notes"],
            }
        )
    for name, rt in RUNTIMES.items():
        out.append({"id": name, "label": rt["label"], "kind": "runtime", "roles": [], "notes": rt["notes"],
                    "group": rt.get("group", ""), "versions": list((RUNTIME_SPECS.get(name) or {}).get("versions") or [])})
    return out


# ----------------------------------------------------------------------------- targets


def default_target(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The functions' scaling cluster (``provider.options.cluster``) or SSH server (``options.deploy``), else this
    machine. A cluster target (``{"cluster": NAME}``) is placed on one of its servers by :func:`check_request`."""
    provider = (raw or {}).get("provider") or {}
    options = provider.get("options") if provider.get("name") == "onprem" else None
    if options is None:
        options = ((((raw or {}).get("providers") or {}).get("onprem") or {}).get("provider") or {}).get("options")
    cluster = (options or {}).get("cluster") if isinstance(options, dict) else None
    name = cluster.get("name") if isinstance(cluster, dict) else cluster
    if isinstance(name, str) and name:
        return {"cluster": name}
    deploy = (options or {}).get("deploy") if isinstance(options, dict) else None
    if isinstance(deploy, dict) and deploy.get("server") and not deploy.get("host"):
        return {"method": "ssh", "server": str(deploy["server"])}      # a saved server, resolved with the root
    if isinstance(deploy, dict) and deploy.get("host"):
        target: Dict[str, Any] = {
            "method": "ssh",
            "host": str(deploy["host"]),
            "user": str(deploy.get("user") or "root"),
            "port": int(deploy.get("ssh_port") or deploy.get("port") or 22),
            "sudo": bool(deploy.get("sudo")),
        }
        identity = deploy.get("pem") or deploy.get("identity_file")
        if identity:
            target["identity_file"] = str(identity)
        if deploy.get("password_file"):
            target["password_file"] = str(Path(str(deploy["password_file"])).expanduser())
        if deploy.get("auth"):
            target["auth"] = str(deploy["auth"])
        return target
    return {"method": "local"}


CONFIG_SERVER = "pskit.yml provider.options.deploy.server"


def normalize_target(raw: Any, root: Path, *, origin: str = "") -> Dict[str, Any]:
    """``origin``: where a saved server's name came from, named when that server no longer exists."""
    if not isinstance(raw, dict):
        raw = {"method": "local"}
    if raw.get("server"):
        from .onprem_servers import ServerError, server_target

        try:
            saved = server_target(root, str(raw["server"]), origin=origin)
        except ServerError as exc:
            raise ServiceError(str(exc)) from None
        if "sudo" in raw and raw.get("sudo") is not None:
            saved["sudo"] = bool(raw["sudo"])
        return saved
    method = str(raw.get("method") or "local")
    if method == "local":
        return {"method": "local"}
    if method != "ssh":
        raise ServiceError("target.method must be local or ssh")
    host = str(raw.get("host") or "").strip()
    if not _HOST.match(host) or host.startswith("-"):
        raise ServiceError("target.host must be a host name or IP address")
    user = str(raw.get("user") or "root").strip()
    if not _USER.match(user):
        raise ServiceError("target.user must be a plain user name")
    try:
        port = int(raw.get("port") or 22)
    except (TypeError, ValueError):
        raise ServiceError("target.port must be a number") from None
    if not 1 <= port <= 65535:
        raise ServiceError("target.port must be between 1 and 65535")
    target: Dict[str, Any] = {"method": "ssh", "host": host, "user": user, "port": port, "sudo": bool(raw.get("sudo"))}
    auth = str(raw.get("auth") or "").strip().lower()
    if auth not in ("", "key", "agent", "password"):
        raise ServiceError("target.auth must be key, agent or password")
    identity = str(raw.get("identity_file") or raw.get("pem") or "").strip()
    if identity and auth in ("", "key"):
        path = Path(identity).expanduser()
        if not path.is_absolute():
            path = root / path
        target["identity_file"] = str(path)
    if auth == "password" or raw.get("password") or raw.get("password_file"):
        target["auth"] = "password"
        password = str(raw.get("password") or "")
        password_file = str(raw.get("password_file") or "").strip()
        if password:
            # Typed in the studio: kept in .pskit/ssh (out of git, owner-only), never in state or pskit.yml.
            target["password_file"] = str(save_ssh_password(root, user, host, port, password))
        elif password_file:
            path = Path(password_file).expanduser()
            target["password_file"] = str(path if path.is_absolute() else root / path)
    elif auth == "agent":
        target["auth"] = "agent"
    known = str(raw.get("known_hosts") or "").strip()
    if known:
        target["known_hosts"] = known
    return target


def save_ssh_password(root: Path, user: str, host: str, port: int, password: str) -> Path:
    if not password or "\n" in password or len(password) > 256:
        raise ServiceError("the SSH password must be one line of at most 256 characters")
    folder = root / ".pskit" / "ssh"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (re.sub(r"[^A-Za-z0-9._-]", "_", f"{user}@{host}-{port}") + ".pass")
    path.write_bytes(password.encode("utf-8"))
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - Windows ACLs
        pass
    return path


def ssh_options(target: Dict[str, Any]) -> Dict[str, Any]:
    """The ``ssh`` dict the deploy helpers take (key, password file, known hosts) for a service target."""
    ssh: Dict[str, Any] = {
        "host": target["host"],
        "user": target["user"],
        "port": target.get("port") or 22,
        "identity_file": target.get("identity_file") or "",
        "known_hosts": target.get("known_hosts") or "accept-new",
    }
    for name in ("password_file", "auth"):
        if target.get(name):
            ssh[name] = target[name]
    return ssh


def check_ssh_login(target: Dict[str, Any]) -> None:
    """Fail early (with what to do) when the SSH login cannot work from this machine."""
    if target.get("method") != "ssh":
        return
    from ..providers.onprem_remote import ssh_auth_problem

    problem = ssh_auth_problem(ssh_options(target))
    if problem:
        raise ServiceError(problem)


def install_ssh_key(
    target: Dict[str, Any],
    emit: Emit,
    *,
    key_path: Optional[str] = None,
    password: str = "",
    run: Optional[Callable[..., subprocess.CompletedProcess[bytes]]] = None,
) -> Path:
    """Create ``~/.ssh/pskit_ed25519`` (if missing) and add its public key to the server's authorized_keys.

    Logs in with the password once: through sshpass when ``password`` is given, else ssh asks for it in the
    terminal. Then checks that the key alone logs in. Returns the private key path.
    """
    import shutil
    import tempfile

    normalize_target({**target, "method": "ssh"}, Path.cwd())  # validates host / user / port
    call = run or subprocess.run
    key = Path(key_path).expanduser() if key_path else Path.home() / ".ssh" / "pskit_ed25519"
    if not key.is_file():
        key.parent.mkdir(parents=True, exist_ok=True)
        emit(f"Creating {key}")
        made = call(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "pskit", "-f", str(key)])  # noqa: S603
        if made.returncode:
            raise ServiceError("ssh-keygen failed; install the OpenSSH client")
    public = Path(str(key) + ".pub")
    if not public.is_file():
        raise ServiceError(f"{public} is missing; recreate it with: ssh-keygen -y -f {key} > {public}")
    opts = ["-p", str(target.get("port") or 22), "-o", "StrictHostKeyChecking=accept-new",
            "-o", "PreferredAuthentications=password,keyboard-interactive", "-o", "PubkeyAuthentication=no"]
    dest = f"{target['user']}@{target['host']}"
    command = ("umask 077; mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && k=\"$(cat)\" && "
               "(grep -qxF \"$k\" ~/.ssh/authorized_keys || printf '%s\\n' \"$k\" >> ~/.ssh/authorized_keys)")
    emit(f"Installing {public.name} on {dest}" + ("" if password else " (enter the SSH password when asked)"))
    if password:
        if not shutil.which("sshpass"):
            raise ServiceError("sending the password needs sshpass; leave the password out and type it when ssh asks")
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "p"
            secret.write_bytes(password.encode("utf-8"))
            with open(public, "rb") as handle:
                done = call(["sshpass", "-f", str(secret), "ssh", *opts, dest, command], stdin=handle)  # noqa: S603
    else:
        with open(public, "rb") as handle:
            done = call(["ssh", *opts, dest, command], stdin=handle)  # noqa: S603
    if done.returncode:
        raise ServiceError(f"could not log in to {dest} with the password (ssh exit {done.returncode})")
    check = call(["ssh", "-p", str(target.get("port") or 22), "-i", str(key), "-o", "IdentitiesOnly=yes",  # noqa: S603
                  "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", dest, "true"])
    if check.returncode:
        raise ServiceError(f"the key was added, but {dest} still refuses it (PubkeyAuthentication off on the server?)")
    return key


def describe_target(target: Dict[str, Any]) -> str:
    if target.get("method") == "ssh":
        where = f"{target.get('user')}@{target.get('host')}:{target.get('port', 22)}"
        label = f"{target['server']} ({where})" if target.get("server") else where
        return f"{label} in cluster {target['cluster']}" if target.get("cluster") else label
    if target.get("cluster"):
        return f"cluster {target['cluster']}"
    return "this machine"


def functions_target(raw: Optional[Dict[str, Any]], root: Path) -> Dict[str, Any]:
    """Where the functions' host answers: pskit.yml's SSH server or cluster, else where the stage was last deployed
    (``pskit deploy --cluster`` / ``--server``, the studio's machine picker), else this machine. A cluster gives its
    master, tagged with ``cluster`` and the master's cluster ``address``."""
    target = default_target(raw)
    origin = CONFIG_SERVER
    if target == {"method": "local"}:
        from .onprem_servers import deployed_cluster, deployed_server

        stage = str(((raw or {}).get("provider") or {}).get("stage") or "dev")
        remembered = deployed_cluster(root, stage)
        if remembered:
            target = {"cluster": remembered}
        elif deployed_server(root, stage):
            target, origin = {"server": deployed_server(root, stage)}, f"the last deploy of onprem-{stage}"
    if target.get("cluster"):
        from .onprem_cluster import ClusterError, get_cluster

        try:
            cluster = get_cluster(root, str(target["cluster"]))
        except ClusterError as exc:
            raise ServiceError(str(exc)) from None
        master = str(cluster["master"])
        out = normalize_target({"server": master}, root)
        address = str(((cluster.get("nodes") or {}).get(master) or {}).get("address") or "")
        return {**out, "cluster": str(target["cluster"]), "orchestrator": str(cluster.get("orchestrator") or ""),
                "address": address or str(out.get("host") or "")}
    return normalize_target(target, root, origin=origin)


def default_target_problem(raw: Optional[Dict[str, Any]], root: Path) -> str:
    """Why pskit.yml's deploy target cannot be used as the default (a saved server that no longer exists), or ""."""
    target = default_target(raw)
    if not target.get("server"):
        return ""
    from .onprem_servers import load_servers, missing_server_message

    servers = load_servers(root)
    name = str(target["server"])
    return "" if name in servers else missing_server_message(name, servers, CONFIG_SERVER)


def cluster_target(root: Path, raw: Dict[str, Any], *, run: Optional[RunFn] = None,
                   measure: bool = True) -> Tuple[Dict[str, Any], str]:
    """``{"cluster": NAME, "server": optional member}`` -> the saved server it runs on (tagged with the cluster) and
    that server's cluster address. Without a server the one with the most free memory is picked."""
    from .onprem_cluster import ClusterError, place

    name = str(raw.get("cluster") or "")
    try:
        spot = place(root, name, str(raw.get("server") or ""), run=run, measure=measure)
    except ClusterError as exc:
        raise ServiceError(str(exc)) from None
    target = normalize_target({"server": spot["server"], "sudo": raw.get("sudo")}, root)
    target["cluster"] = name
    return target, str(spot["address"] or "")


def _ssh_argv(target: Dict[str, Any], command: str) -> List[str]:
    from ..providers.onprem_remote import _ssh_base, _target

    ssh = ssh_options(target)
    return _ssh_base(ssh) + [_target(ssh), command]


def _shq(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def docker_argv(target: Dict[str, Any], args: Sequence[str]) -> List[str]:
    """``docker <args>`` on the target. Over SSH it falls back to ``sudo -n docker``."""
    if target.get("method") != "ssh":
        return ["docker", *args]
    quoted = " ".join(_shq(str(a)) for a in args)
    if target.get("sudo"):
        command = f"sudo -n docker {quoted}"
    else:
        command = f"if docker info >/dev/null 2>&1; then docker {quoted}; else sudo -n docker {quoted}; fi"
    return _ssh_argv(target, command)


# ----------------------------------------------------------------------------- running commands


def _default_run(argv: List[str], stdout: Optional[Path]) -> Tuple[int, str]:
    try:
        if stdout is not None:
            with open(stdout, "wb") as handle:
                proc = subprocess.run(argv, stdout=handle, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)  # noqa: S603
            return proc.returncode, proc.stderr.decode("utf-8", "replace")
        proc = subprocess.run(  # noqa: S603 - explicit argv, no shell
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
        )
    except FileNotFoundError:
        return 127, f"command not found: {argv[0]}. Install it on this machine and retry."
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def _stream_run(argv: List[str], emit: Emit) -> Tuple[int, str]:
    """Run ``argv`` and emit each line as it arrives. A cluster apply waits for minutes; buffering that until
    the SSH session ends hides the allocation status the script is printing."""
    try:
        proc = subprocess.Popen(  # noqa: S603 - explicit argv, no shell
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return 127, f"command not found: {argv[0]}. Install it on this machine and retry."
    lines: List[str] = []
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        lines.append(line)
        if line:
            emit("  " + line)
    return proc.wait(), "\n".join(lines)


class _Runner:
    def __init__(self, emit: Emit, run: Optional[RunFn]) -> None:
        self.emit = emit
        self.run_fn = run or _default_run

    def __call__(self, argv: List[str], *, check: bool = True, show: bool = True, stdout: Optional[Path] = None) -> str:
        if show:
            self.emit("$ " + " ".join(_mask(a) for a in argv))
        if show and stdout is None and self.run_fn is _default_run:
            code, out = _stream_run(argv, self.emit)
        else:
            code, out = self.run_fn(argv, stdout)
            text = out.strip()
            if text and show:
                for line in text.splitlines()[-40:]:
                    self.emit("  " + line)
        text = out.strip()
        if check and code:
            last = text.splitlines()[-1] if text else "no output"
            raise ServiceError(f"command failed ({code}): {_mask(last)}")
        return out


def _mask(arg: str) -> str:
    # `-e NAME=secret` and URLs with passwords stay out of logs; the SMTP service's script is only named.
    text = re.sub(r"(PSKIT_SMTP_JS=)[A-Za-z0-9+/=]+", r"\1<onprem_smtp.js in base64>", str(arg))
    if re.match(r"^[A-Z0-9_]*(PASSWORD|PASS|SECRET|TOKEN|KEY)[A-Z0-9_]*=", text):
        return text.split("=", 1)[0] + "=***"
    text = re.sub(r"(://[^:/@\s]*:)[^@\s]+@", r"\1***@", text)
    return re.sub(r"((?:PASSWORD|PASS|SECRET|TOKEN|KEY)[A-Z0-9_]*=)[^ ']+", r"\1***", text)


# ----------------------------------------------------------------------------- state and env file


def load_state(root: Path) -> Dict[str, Any]:
    path = root / STATE_FILE
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {"services": {}}
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        return {"services": {}}
    return data


def save_state(root: Path, state: Dict[str, Any]) -> None:
    path = root / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def env_file_of(raw: Optional[Dict[str, Any]]) -> str:
    provider = (raw or {}).get("provider") or {}
    options = provider.get("options") if provider.get("name") == "onprem" else None
    if not isinstance(options, dict):
        override = (((raw or {}).get("providers") or {}).get("onprem") or {}).get("provider") or {}
        options = override.get("options")
    value = options.get("env_file") if isinstance(options, dict) else None
    return str(value) if value else DEFAULT_ENV_FILE


def update_env_file(path: Path, values: Dict[str, Optional[str]]) -> None:
    """Set (or with ``None`` remove) ``KEY=value`` lines, keeping everything else."""
    lines = path.read_text("utf-8").splitlines() if path.is_file() else []
    pending = dict(values)
    out: List[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key.startswith("export "):
            key = key[7:].strip()
        if "=" in line and key in pending:
            value = pending.pop(key)
            if value is not None:
                out.append(f"{key}={value}")
            continue
        out.append(line)
    for key, value in pending.items():
        if value is not None:
            out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(out).rstrip("\n") + "\n" if out else "").encode("utf-8"))


def _ensure_ignored(root: Path, entry: str) -> None:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return
    lines = [line.strip() for line in gitignore.read_text("utf-8").splitlines()]
    if entry in lines or "/" + entry in lines:
        return
    text = gitignore.read_text("utf-8")
    gitignore.write_bytes((text.rstrip("\n") + f"\n# pskit on-prem service credentials\n{entry}\n").encode("utf-8"))


# ----------------------------------------------------------------------------- create


def _var_prefix(key: str) -> str:
    return "PSKIT_" + re.sub(r"[^A-Za-z0-9]", "_", key).upper()


def _bucket_name(key: str) -> str:
    name = re.sub(r"[^a-z0-9.-]", "-", key.lower()).strip("-.")
    return (name + "-bucket")[:63] if len(name) < 3 else name[:63]


def _container_name(project: str, key: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]", "-", f"pskit-{project}-{key}" if project else f"pskit-{key}")
    return base[:120]


def check_request(body: Dict[str, Any], root: Path, raw: Optional[Dict[str, Any]], *, run: Optional[RunFn] = None,
                  place: bool = True) -> Dict[str, Any]:
    """Validate a create request and fill in defaults. Raises :class:`ServiceError`.

    A cluster target is placed on one of its servers (``place=False``: names checked only, no SSH)."""
    key = str(body.get("key") or "").strip()
    if not _NAME.match(key):
        raise ServiceError("key must start with a letter and use letters, digits, - or _ (max 63)")
    service = str(body.get("service") or "")
    if service not in SERVICES and service not in RUNTIMES:
        raise ServiceError(f"service must be one of {', '.join([*SERVICES, *RUNTIMES])}")
    wanted = body.get("target") or default_target(raw)
    replicated = replication.is_replicated(body)
    if replicated:
        wanted = {"method": "local"}  # placeholder: the topology's members say where it runs
    cluster_address = ""
    if isinstance(wanted, dict) and wanted.get("cluster"):
        target, cluster_address = cluster_target(root, wanted, run=run, measure=place)
    else:
        target = normalize_target(wanted, root, origin="" if body.get("target") else CONFIG_SERVER)
    if service in RUNTIMES:
        if target["method"] != "ssh":
            raise ServiceError(f"{RUNTIMES[service]['label']} is installed on an SSH server; set target.method: ssh")
        try:
            version = check_version(service, body.get("version")) if service in RUNTIME_SPECS else ""
        except ValueError as exc:
            raise ServiceError(str(exc)) from None
        return {"key": key, "service": service, "kind": "runtime", "target": target, "version": version}
    spec = SERVICES[service]
    if key in load_state(root)["services"] and not body.get("replace"):
        raise ServiceError(f"{key!r} already exists; remove it first or pick another key")
    role = str(body.get("role") or spec["roles"][0])
    if role not in spec["roles"]:
        raise ServiceError(f"{spec['label']} can be used as {', '.join(spec['roles'])}, not {role!r}")
    try:
        port = int(body.get("port") or spec["port"])
    except (TypeError, ValueError):
        raise ServiceError("port must be a number") from None
    if not 1 <= port <= 65535:
        raise ServiceError("port must be between 1 and 65535")
    image = str(body.get("image") or spec["image"]).strip()
    if not _IMAGE.match(image):
        raise ServiceError("image must be a Docker image reference such as redis:7-alpine")
    address = str(body.get("address") or "").strip()
    if address and (not _HOST.match(address) or address.startswith("-")):
        raise ServiceError("address must be a host name or IP address")
    if not address:
        # On a cluster: the server's cluster address, which the replicas on every server reach.
        address = cluster_address or (target["host"] if target["method"] == "ssh" else "127.0.0.1")
    default_bind = target.get("bind") or ("0.0.0.0" if target["method"] == "ssh" else "127.0.0.1")  # noqa: S104
    bind = str(body.get("bind") or default_bind)
    if bind not in ("0.0.0.0", "127.0.0.1") and not re.match(r"^[0-9.]{7,15}$", bind):  # noqa: S104
        raise ServiceError("bind must be 0.0.0.0, 127.0.0.1 or an IPv4 address of the server")
    attach = body.get("attach") or []
    if isinstance(attach, str):
        attach = [attach]
    if not isinstance(attach, list) or not all(isinstance(a, str) and _NAME.match(a) for a in attach):
        raise ServiceError("attach must be a list of function names")
    user = str(body.get("user") or "").strip()
    password = str(body.get("password") or "")
    if service in NO_AUTH and (user or password):
        raise ServiceError(
            f"{spec['label']} runs without authentication here; leave user and password empty and keep it on "
            "bind 127.0.0.1 or a private network"
        )
    if service in SELF_LOGIN and (user or password):
        raise ServiceError(f"{spec['label']} asks you to create its admin account on the first visit; "
                           "leave user and password empty")
    if service == "neo4j" and user not in ("", "neo4j"):
        raise ServiceError("Neo4j's user is always neo4j; leave user empty")
    if user and not _LOGIN_OK.match(user):
        raise ServiceError("user must be 3-64 characters: a letter, then letters, digits, _ . or -")
    if password and not _PASSWORD_OK.match(password):
        raise ServiceError("password must be 8-128 characters of letters, digits and !#%*+,.:=?@^_~-")
    if service == "dragonfly" and user not in ("", "default"):
        raise ServiceError("Dragonfly has a password only; leave user empty (default)")
    if service == "azurite" and user and not re.match(r"^[a-z0-9]{3,24}$", user):
        raise ServiceError("the Azurite account name must be 3-24 lowercase letters and digits")
    if service == "mongodb" and user == "admin":
        raise ServiceError("pick another user than admin for MongoDB")
    if body.get("gui"):
        gui_login = str(body.get("gui_login") or "password")
        choices = gui_login_choices(service)
        if gui_login not in GUI_LOGINS:
            raise ServiceError("gui_login must be password or none")
        if choices and gui_login not in choices:
            raise ServiceError(f"the web UI of {spec['label']} always asks for a login")
        gui_password = str(body.get("gui_password") or "")
        if gui_password and (gui_login == "none" or not _PASSWORD_OK.match(gui_password)):
            raise ServiceError("gui_password must be 8-128 characters of letters, digits and !#%*+,.:=?@^_~- "
                               "(and only with gui_login: password)")
    project = str((raw or {}).get("service") or "")
    extra: Dict[str, Any] = {}
    # Optional: alert settings, and a dump to load once it is up (before any replica copies it).
    if body.get("alert") and (not isinstance(body["alert"], dict) or body["alert"].get("enabled", True)):
        extra["alert"] = monitor.check_alert(body["alert"])
    data_import = monitor.check_import(service, body.get("import"))
    if data_import:
        extra["import"] = data_import
    if service == "smtp":
        extra["smtp"] = onprem_smtp.check(body, raw, root, target)
        extra["token"] = onprem_smtp.admin_token(raw, root, env_file_of(raw))
    out = {
        **extra,
        "user": user or DEFAULT_USER.get(service, "pskit"),
        "password": password,
        "project": project,
        "key": key,
        "service": service,
        "kind": "service",
        "role": role,
        "target": target,
        "port": port,
        "image": image,
        "address": address,
        "address_auto": not body.get("address"),
        "bind": bind,
        "attach": list(attach),
        "container": _container_name(project, key),
        "volume": data_mount(target, _container_name(project, key)) if spec["data"] else "",
        "data_dir": str(target.get("data_dir") or ""),
    }
    # A replicated database: primary, replicas and load balancer on the servers the topology names.
    return replication.check(body, out, root) if replicated else out


def data_mount(target: Dict[str, Any], name: str) -> str:
    """Where a container's data lives: ``<data_dir>/<name>`` (a bind mount) when the server has a data directory,
    else the Docker volume ``<name>-data``."""
    data_dir = str(target.get("data_dir") or "").rstrip("/")
    return f"{data_dir}/{name}" if data_dir else f"{name}-data"


def host_port(item: Dict[str, Any], container_port: int) -> int:
    """The host port of a container port: extra ports (consoles, Azurite queues) move with the main port,
    so two instances of one service on a server don't collide."""
    spec = SERVICES.get(str(item.get("service"))) or {}
    main = int(item.get("port") or spec.get("port") or 0)
    if container_port == spec.get("port"):
        return main
    if container_port in (spec.get("extra_ports") or []):
        return container_port + (main - int(spec["port"]))
    return container_port


def _connection(req: Dict[str, Any], password: str) -> Tuple[Dict[str, Any], Dict[str, str], List[str]]:
    """(resource entry, env file values, notes) for a service used in ``req['role']``."""
    key, service, role = req["key"], req["service"], req["role"]
    addr, port = req["address"], req["port"]
    prefix = _var_prefix(key)
    user = str(req.get("user") or "pskit")
    safe_user, safe_pw = quote(user, safe=""), quote(password, safe="")
    database = re.sub(r"[^A-Za-z0-9_]", "_", key)
    env: Dict[str, str] = {}
    notes: List[str] = []
    res: Dict[str, Any] = {"type": ROLE_TYPE.get(role, role), "external": True}
    if service in ("redis", "valkey"):
        login = "" if user == "default" else safe_user
        env[f"{prefix}_URL"] = f"redis://{login}:{safe_pw}@{addr}:{port}/0"
        env[f"{prefix}_PASSWORD"] = password
        if role in ("queue", "stream"):
            driver = "redis" if role == "queue" else "redis_stream"
            res["options"] = {"driver": driver, "url_env": f"{prefix}_URL", "key": key}
        else:
            res["connection"] = {
                "host": addr,
                "port": port,
                "url_env": f"{prefix}_URL",
                "password_env": f"{prefix}_PASSWORD",
            }
    elif service == "rabbitmq":
        env[f"{prefix}_URL"] = f"amqp://{safe_user}:{safe_pw}@{addr}:{port}/%2F"
        env[f"{prefix}_PASSWORD"] = password
        res["options"] = {
            "driver": "custom",
            "class": "pskit_drivers.rabbitmq_queue:RabbitQueue",
            "url_env": f"{prefix}_URL",
            "queue": key,
        }
        res["connection"] = {"management_url": f"http://{addr}:{host_port(req, 15672)}", "user": user}
        notes.append("added pskit_drivers/rabbitmq_queue.py to your code and pika to requirements.txt")
    elif service == "kafka":
        project = re.sub(r"[^A-Za-z0-9_.-]", "-", str(req.get("project") or "pskit"))
        res["options"] = {
            "driver": "custom",
            "class": "pskit_drivers.kafka_queue:KafkaQueue",
            "bootstrap_servers": f"{addr}:{port}",
            "topic": key,
            "group_id": f"{project}-{key}",
        }
        notes.append("added pskit_drivers/kafka_queue.py to your code and kafka-python to requirements.txt")
    elif service == "nats":
        env[f"{prefix}_URL"] = f"nats://{safe_user}:{safe_pw}@{addr}:{port}"
        env[f"{prefix}_PASSWORD"] = password
        res["options"] = {
            "driver": "custom",
            "class": "pskit_drivers.nats_queue:NatsQueue",
            "url_env": f"{prefix}_URL",
            "stream": re.sub(r"[^A-Za-z0-9_-]", "_", key),
            "subject": f"{key}.jobs",
            "durable": "pskit",
        }
        res["connection"] = {"monitor_url": f"http://{addr}:{host_port(req, 8222)}"}
        notes.append("added pskit_drivers/nats_queue.py to your code and nats-py to requirements.txt")
    elif service == "elasticmq":
        res["options"] = {
            "driver": "sqs",
            "queue_url": f"http://{addr}:{port}/000000000000/{key}",
            "endpoint": f"http://{addr}:{port}",
            "region": "us-east-1",
            # ElasticMQ accepts any credentials; these are not secrets.
            "access_key": "pskit",
            "secret_key": "pskit",
            # ElasticMQ forgets queues on restart; the driver recreates this one when it is missing.
            "create_queue": True,
        }
        res["connection"] = {"ui_url": f"http://{addr}:{host_port(req, 9325)}"}
    elif service in ("postgres", "mysql", "mariadb"):
        scheme = "postgresql" if service == "postgres" else "mysql"
        env[f"{prefix}_URL"] = f"{scheme}://{safe_user}:{safe_pw}@{addr}:{port}/{database}"
        env[f"{prefix}_PASSWORD"] = password
        res["connection"] = {
            "host": addr,
            "port": port,
            "database": database,
            "user": user,
            "password_env": f"{prefix}_PASSWORD",
            "url_env": f"{prefix}_URL",
        }
    elif service == "mongodb":
        env[f"{prefix}_URL"] = f"mongodb://{safe_user}:{safe_pw}@{addr}:{port}/?authSource=admin"
        env[f"{prefix}_PASSWORD"] = password
        res["connection"] = {
            "host": addr,
            "port": port,
            "user": user,
            "password_env": f"{prefix}_PASSWORD",
            "url_env": f"{prefix}_URL",
        }
    elif service == "minio":
        bucket = _bucket_name(key)
        env[f"{prefix}_ACCESS_KEY"] = user
        env[f"{prefix}_SECRET_KEY"] = password
        if bucket != key:
            res["name"] = bucket
        res["options"] = {
            "driver": "minio",
            "endpoint": f"http://{addr}:{port}",
            "bucket": bucket,
            "access_key_env": f"{prefix}_ACCESS_KEY",
            "secret_key_env": f"{prefix}_SECRET_KEY",
        }
        res["connection"] = {"console_url": f"http://{addr}:{host_port(req, 9001)}"}
    elif service in ("dragonfly", "keydb"):
        login = "" if user == "default" else safe_user
        env[f"{prefix}_URL"] = f"redis://{login}:{safe_pw}@{addr}:{port}/0"
        env[f"{prefix}_PASSWORD"] = password
        if role in ("queue", "stream"):
            res["options"] = {"driver": "redis" if role == "queue" else "redis_stream", "url_env": f"{prefix}_URL", "key": key}
        else:
            res["connection"] = {"host": addr, "port": port, "url_env": f"{prefix}_URL", "password_env": f"{prefix}_PASSWORD"}
    elif service == "apache-kafka":
        project = re.sub(r"[^A-Za-z0-9_.-]", "-", str(req.get("project") or "pskit"))
        res["options"] = {
            "driver": "custom",
            "class": "pskit_drivers.kafka_queue:KafkaQueue",
            "bootstrap_servers": f"{addr}:{port}",
            "topic": key,
            "group_id": f"{project}-{key}",
        }
        notes.append("added pskit_drivers/kafka_queue.py to your code and kafka-python to requirements.txt")
    elif service == "lavinmq":
        env[f"{prefix}_URL"] = f"amqp://{safe_user}:{safe_pw}@{addr}:{port}/%2F"
        env[f"{prefix}_PASSWORD"] = password
        res["options"] = {
            "driver": "custom",
            "class": "pskit_drivers.rabbitmq_queue:RabbitQueue",
            "url_env": f"{prefix}_URL",
            "queue": key,
        }
        res["connection"] = {"management_url": f"http://{addr}:{host_port(req, 15672)}", "user": user}
        notes.append("added pskit_drivers/rabbitmq_queue.py to your code and pika to requirements.txt")
    elif service == "azurite":
        account_key = base64.b64encode(password.encode("utf-8")).decode("ascii")
        name = _bucket_name(key)
        env[f"{prefix}_CONNECTION_STRING"] = (
            f"DefaultEndpointsProtocol=http;AccountName={user};AccountKey={account_key};"
            f"BlobEndpoint=http://{addr}:{port}/{user};QueueEndpoint=http://{addr}:{host_port(req, 10001)}/{user};"
        )
        if name != key:
            res["name"] = name
        if role == "queue":
            res["options"] = {"driver": "azure_queue", "connection_string_env": f"{prefix}_CONNECTION_STRING",
                              "queue": name, "create_queue": True}
        else:
            res["options"] = {"driver": "azure_blob", "connection_string_env": f"{prefix}_CONNECTION_STRING",
                              "container": name, "create_bucket": True}
        res["connection"] = {"account": user, "blob_endpoint": f"http://{addr}:{port}/{user}",
                             "queue_endpoint": f"http://{addr}:{host_port(req, 10001)}/{user}"}
    elif service in ("localstack", "localemu"):
        if role == "queue":
            res["options"] = {
                "driver": "sqs",
                "queue_url": f"http://{addr}:{port}/000000000000/{key}",
                "endpoint": f"http://{addr}:{port}",
                "region": "us-east-1",
                "access_key": "test",
                "secret_key": "test",
                "create_queue": True,
            }
        else:
            bucket = _bucket_name(key)
            if bucket != key:
                res["name"] = bucket
            res["options"] = {
                "driver": "s3",
                "endpoint": f"http://{addr}:{port}",
                "bucket": bucket,
                "access_key": "test",
                "secret_key": "test",
                "path_style": True,
                "create_bucket": True,
            }
    elif service == "fake-gcs":
        bucket = _bucket_name(key)
        if bucket != key:
            res["name"] = bucket
        res["options"] = {"driver": "gcs", "endpoint": f"http://{addr}:{port}", "emulator": True, "bucket": bucket,
                          "project": "pskit", "create_bucket": True}
    elif service == "rustfs":
        bucket = _bucket_name(key)
        env[f"{prefix}_ACCESS_KEY"] = user
        env[f"{prefix}_SECRET_KEY"] = password
        if bucket != key:
            res["name"] = bucket
        res["options"] = {
            "driver": "s3",
            "endpoint": f"http://{addr}:{port}",
            "bucket": bucket,
            "access_key_env": f"{prefix}_ACCESS_KEY",
            "secret_key_env": f"{prefix}_SECRET_KEY",
            "path_style": True,
            "create_bucket": True,
        }
        res["connection"] = {"console_url": f"http://{addr}:{host_port(req, 9001)}"}
    elif service in onprem_s3.SERVICES:
        bucket = _bucket_name(key)
        if bucket != key:
            res["name"] = bucket
        s3 = onprem_s3.resource(req, password, prefix, bucket)
        env.update(s3["env"])
        res["options"] = s3["options"]
        res["connection"] = s3["connection"]
    elif service == "memcached":
        res["connection"] = {"host": addr, "port": port}
    elif service == "mailpit":
        res["connection"] = {"smtp_host": addr, "smtp_port": port, "web_url": f"http://{addr}:{host_port(req, 8025)}"}
    elif service == "smtp":
        res = onprem_smtp.resource(req)
        notes.append("add the DNS records in How to use (A and MX) so mail for "
                     f"{', '.join(req['smtp']['domains'])} reaches this server")
    connect = (SERVICES.get(service) or {}).get("connect") or {}
    if connect:
        values = {**_values(req, password), "prefix": prefix, "address": addr, "port": str(port),
                  **{f"port_{n}": str(host_port(req, n)) for n in SERVICES[service]["extra_ports"]}}
        for name, template in (connect.get("env") or {}).items():
            env[f"{prefix}_{name}"] = _fill(template, values)
        if connect.get("connection"):
            res["connection"] = {k: (int(_fill(v, values)) if k == "port" else _fill(v, values))
                                 for k, v in connect["connection"].items()}
        if connect.get("note"):
            notes.append(_fill(connect["note"], values))
    if role == "secrets":
        # get_secret(name, store=key) reads PSKIT_<KEY>_DRIVER / _URL / _TOKEN ...; key "secrets" is the default store.
        url = f"http://{addr}:{port}"
        if service == "infisical":
            env.update({f"{prefix}_DRIVER": "infisical", f"{prefix}_URL": url, f"{prefix}_CLIENT_ID": "",
                        f"{prefix}_CLIENT_SECRET": "", f"{prefix}_PROJECT_ID": "", f"{prefix}_ENVIRONMENT": "dev"})
            res["connection"] = {"driver": "infisical", "url": url, "client_id_env": f"{prefix}_CLIENT_ID",
                                 "client_secret_env": f"{prefix}_CLIENT_SECRET", "project_id_env": f"{prefix}_PROJECT_ID"}
            notes.append(f"open {url}, create the admin account, a project and a machine identity (Universal Auth); "
                         f"fill {prefix}_CLIENT_ID, {prefix}_CLIENT_SECRET and {prefix}_PROJECT_ID in the env file")
        elif service in onprem_secretsmanager.SERVICES:
            conn = onprem_secretsmanager.connection(req, password, prefix)
            env.update(conn["env"])
            res["connection"] = conn["connection"]
        elif service == "openbao":
            env.update({f"{prefix}_DRIVER": "vault", f"{prefix}_URL": url, f"{prefix}_TOKEN": password,
                        f"{prefix}_MOUNT": "secret"})
            res["connection"] = {"driver": "vault", "url": url, "mount": "secret", "token_env": f"{prefix}_TOKEN"}
        else:
            env.update({f"{prefix}_DRIVER": "aws", f"{prefix}_URL": url, f"{prefix}_REGION": "us-east-1",
                        f"{prefix}_ACCESS_KEY": "test", f"{prefix}_SECRET_KEY": "test"})
            res["connection"] = {"driver": "aws", "url": url, "region": "us-east-1"}
        res.pop("options", None)
        res.pop("name", None)
        py_store, js_store = ("", "") if key == "secrets" else (f', store="{key}"', f', {{ store: "{key}" }}')
        notes.append(f'read secrets in handlers with get_secret("name"{py_store}) (Python) / '
                     f'getSecret("name"{js_store}) (Node.js)')
    return res, env, notes


def _fill(text: str, values: Dict[str, str]) -> str:
    for name, value in values.items():
        text = text.replace("{" + name + "}", value)
    return text


_GENERATORS = {
    "hex16": lambda: secrets.token_hex(16),
    "hex32": lambda: secrets.token_hex(32),
    "b64_32": lambda: base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    "token": lambda: secrets.token_urlsafe(24),
}


def _generated(root: Path, raw: Optional[Dict[str, Any]], req: Dict[str, Any]) -> Dict[str, str]:
    """Random keys a service needs (``generate``). A value already in the env file is kept: re-creating the
    service must not change an encryption key its data was written with."""
    from ..runtime.onprem_host import parse_env_text

    spec = SERVICES[req["service"]]
    if not spec.get("generate"):
        return {}
    path = root / env_file_of(raw)
    existing = parse_env_text(path.read_text("utf-8")) if path.is_file() else {}
    prefix = _var_prefix(req["key"])
    return {name: existing.get(f"{prefix}_{name.upper()}") or _GENERATORS[kind]()
            for name, kind in spec["generate"].items()}


def _values(req: Dict[str, Any], password: str = "") -> Dict[str, str]:
    return {
        **{k: str(v) for k, v in (req.get("generated") or {}).items()},
        "password": password,
        "user": str(req.get("user") or "pskit"),
        "database": re.sub(r"[^A-Za-z0-9_]", "_", req["key"]),
        "bucket": _bucket_name(req["key"]),
        "name": req["key"],
        "address": str(req.get("address") or "127.0.0.1"),
        "port": str(req.get("port") or ""),
        "container": str(req.get("container") or ""),
        "account_key": base64.b64encode(password.encode("utf-8")).decode("ascii") if password else "",
    }


def run_args(req: Dict[str, Any], password: str) -> List[str]:
    """``docker run`` arguments for a service request (password included)."""
    if req["service"] == "smtp":
        return onprem_smtp.run_args(req, str(req.get("token") or ""))
    spec = SERVICES[req["service"]]
    values = _values(req, password)
    argv = ["run", "-d", "--name", req["container"], "--restart", "unless-stopped"]
    argv += ["--label", f"pskit.service={req['service']}", "--label", f"pskit.key={req['key']}"]
    bind = req["bind"]
    argv += ["-p", f"{bind}:{req['port']}:{spec['port']}"]
    for extra in spec["extra_ports"]:
        argv += ["-p", f"{bind}:{host_port(req, extra)}:{extra}"]
    for name, template in spec["env"].items():
        argv += ["-e", f"{name}={_fill(template, values)}"]
    if spec["data"]:
        argv += ["-v", f"{req['volume']}:{spec['data']}"]
    if spec.get("sidecars"):
        argv += ["--network", f"{req['container']}-net"]
    argv += list(spec["run_args"])
    argv.append(req["image"])
    argv += [_fill(part, values) for part in spec["command"]]
    return argv


def sidecar_args(req: Dict[str, Any], side: Dict[str, Any], password: str) -> List[str]:
    """``docker run`` arguments for one sidecar of a service (no published port: only the service reaches it)."""
    values = _values(req, password)
    name = f"{req['container']}-{side['name']}"
    argv = ["run", "-d", "--name", name, "--restart", "unless-stopped", "--network", f"{req['container']}-net",
            "--network-alias", name, "--label", f"pskit.key={req['key']}", "--label", f"pskit.sidecar={side['name']}"]
    for env_name, template in (side.get("env") or {}).items():
        argv += ["-e", f"{env_name}={_fill(template, values)}"]
    if side.get("data"):
        argv += ["-v", f"{data_mount({'data_dir': req.get('data_dir')}, name)}:{side['data']}"]
    argv.append(side["image"])
    argv += [_fill(part, values) for part in side.get("command") or ()]
    return argv


def _start_sidecars(req: Dict[str, Any], spec: Dict[str, Any], target: Dict[str, Any], sh: Any, password: str,
                    emit: Emit, timeout: float) -> None:
    sh(docker_argv(target, ["network", "create", f"{req['container']}-net"]), check=False, show=False)
    for side in spec["sidecars"]:
        name = f"{req['container']}-{side['name']}"
        sh(docker_argv(target, ["rm", "-f", name]), check=False, show=False)
        if side.get("data") and req.get("data_dir"):
            _make_volume(target, sh, data_mount({"data_dir": req["data_dir"]}, name))
        sh(docker_argv(target, ["pull", side["image"]]))
        sh(docker_argv(target, sidecar_args(req, side, password)))
        if side.get("health"):
            emit(f"waiting for {side['name']} ({side['image']})...")
            deadline = time.monotonic() + timeout
            while True:
                code, _out = sh.run_fn(docker_argv(target, ["exec", name, "sh", "-c", side["health"]]), None)
                if code == 0:
                    break
                if time.monotonic() > deadline:
                    logs = sh(docker_argv(target, ["logs", "--tail", "30", name]), check=False, show=False)
                    raise ServiceError(f"{side['name']} did not become ready. Last log lines:\n{logs.strip()}")
                time.sleep(2)


def create(
    root: Path,
    body: Dict[str, Any],
    raw: Optional[Dict[str, Any]],
    emit: Emit,
    *,
    run: Optional[RunFn] = None,
    wait_seconds: float = 90,
) -> Dict[str, Any]:
    """Start the service (or install the runtime) and record it. Returns the state entry."""
    req = check_request(body, root, raw, run=run)
    if req.get("topology"):
        entry = replication.create(root, req, body, raw, emit, run=run, wait_seconds=wait_seconds)
        if body.get("gui") and companion_for(req["service"]):
            entry["gui"] = add_gui(root, req["key"], emit, run=run, login=str(body.get("gui_login") or "password"),
                                   password=str(body.get("gui_password") or ""))
        return entry
    sh = _Runner(emit, run)
    target = req["target"]
    if run is None:
        check_ssh_login(target)
    emit(f"Creating {req['service']} as {req['key']!r} on {describe_target(target)}")
    if req["kind"] == "runtime":
        _install_runtime(req["service"], target, sh, version=req.get("version") or "")
        entry = {
            "key": req["key"],
            "service": req["service"],
            "kind": "runtime",
            "target": target,
            **({"version": req["version"]} if req.get("version") else {}),
            "created_at": _now(),
        }
        state = load_state(root)
        state["services"][req["key"]] = entry
        save_state(root, state)
        return entry
    spec = SERVICES[req["service"]]
    _ensure_docker(target, sh, install=bool(body.get("install_docker", True)))
    password = req["password"] or secrets.token_urlsafe(18).replace("-", "x").replace("_", "y")
    req["generated"] = _generated(root, raw, req)
    sh(docker_argv(target, ["rm", "-f", req["container"]]), check=False, show=False)
    if spec.get("sidecars"):
        _start_sidecars(req, spec, target, sh, password, emit, wait_seconds)
    sh(docker_argv(target, ["pull", req["image"]]))
    if req["volume"]:
        _prepare_volume(req, spec, target, sh, emit)
    if req["service"] in onprem_secretsmanager.SERVICES:
        onprem_secretsmanager.launch(req, password, target, sh)
    elif req["service"] in onprem_s3.SERVICES:
        onprem_s3.launch(req, password, target, sh)
    else:
        sh(docker_argv(target, run_args(req, password)))
    if req["service"] == "smtp":
        emit("installing smtp-server and mailparser in the container (once, about a minute)...")
        wait_seconds = max(wait_seconds, 300)
    _wait_ready(req, spec, target, sh, wait_seconds, emit)
    init = spec["init"].get(req["role"], "") if isinstance(spec["init"], dict) else spec["init"]
    if init:
        sh(docker_argv(target, ["exec", req["container"], "sh", "-c", _fill(init, _values(req, password))]))
    if req.get("import"):
        monitor.import_data(target, req["container"], req["service"], req["import"], emit, run=run)
    if req["service"] == "elasticmq":
        _elasticmq_queue(req, emit, sh)
    resource, env_values, notes = _connection(req, password)
    for name, value in (req.get("generated") or {}).items():
        # Kept in the env file: re-creating the service reuses them (data encrypted with them stays readable).
        env_values[f"{_var_prefix(req['key'])}_{name.upper()}"] = value
    if req["service"] in DRIVER_TEMPLATES:
        _add_driver(root, raw, req["service"])
    env_file = env_file_of(raw)
    if env_values:
        update_env_file(root / env_file, dict(env_values))
        _ensure_ignored(root, env_file)
        notes.append(f"credentials written to {env_file} (loaded by the host; keep it out of git)")
    entry = {
        "key": req["key"],
        "service": req["service"],
        "kind": "service",
        "role": req["role"],
        "target": target,
        "image": req["image"],
        "container": req["container"],
        "volume": req["volume"],
        **({"data_dir": req["data_dir"]} if req.get("data_dir") else {}),
        "port": req["port"],
        "address": req["address"],
        "address_auto": req["address_auto"],
        "bind": req["bind"],
        "user": req["user"] if req["service"] not in NO_CREDENTIALS else "",
        "attach": req["attach"],
        "env_file": env_file,
        "env": env_values,
        "resource": resource,
        "notes": notes,
        "created_at": _now(),
    }
    if spec.get("sidecars"):
        entry["sidecars"] = [f"{req['container']}-{side['name']}" for side in spec["sidecars"]]
    if req.get("smtp"):
        entry["smtp"] = req["smtp"]
    if req.get("alert"):
        entry["alert"] = req["alert"]
    state = load_state(root)
    state["services"][req["key"]] = entry
    save_state(root, state)
    for note in notes:
        emit(note)
    emit(f"{spec['label']} is ready at {req['address']}:{req['port']}")
    from . import onprem_network as network

    network.emit_rules(emit, f"{spec['label']} {req['key']!r}", network.resource(entry, network.function_hosts(root)))
    if body.get("gui") and companion_for(req["service"]):
        entry["gui"] = add_gui(root, req["key"], emit, run=run, login=str(body.get("gui_login") or "password"),
                               password=str(body.get("gui_password") or ""))
    return entry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_OWNER_PAIR = re.compile(r"^[0-9]{1,10}:[0-9]{1,10}$")
_OWNER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}")


def _numeric_owner(user: str) -> Tuple[bool, str]:
    """``(understood, uid:gid)``. A name (``rustfs``, ``nobody``) is not understood here.

    An empty owner means the image runs as root and chowns its own data directory.
    """
    if user in ("", "0", "root", "0:0", "root:root"):
        return True, ""
    if re.fullmatch(r"[0-9]{1,10}", user):
        return True, user + ":" + user
    if _OWNER_PAIR.match(user):
        return True, user
    return False, ""


def _image_owner(target: Dict[str, Any], sh: _Runner, image: str) -> str:
    """The uid:gid of the image's ``USER``, or ``""`` when it runs as root (or it cannot be read)."""
    out = sh(docker_argv(target, ["inspect", "-f", "{{.Config.User}}", image]), check=False, show=False)
    named = ""
    for line in (ln.strip() for ln in out.splitlines()):
        if not line or " " in line:
            continue
        understood, owner = _numeric_owner(line)
        if understood:
            return owner
        if _OWNER_NAME.fullmatch(line):
            named = line
            break
    if not named:
        return ""
    script = "awk -F: '$1==\"" + named + "\" {print $3 \":\" $4; exit}' /etc/passwd"
    lookup = ["run", "--rm", "--network", "none", "--user", "0", "--entrypoint", "sh", image, "-c", script]
    looked = sh(docker_argv(target, lookup), check=False, show=False)
    for line in reversed([ln.strip() for ln in looked.splitlines()]):
        understood, owner = _numeric_owner(line)
        if understood:
            return owner
    return ""


def _data_owner(spec: Dict[str, Any], target: Dict[str, Any], sh: _Runner, image: str) -> str:
    declared = str(spec.get("data_owner") or "")
    if declared:
        understood, owner = _numeric_owner(declared)
        if understood and owner:
            return owner
        raise ServiceError(f"invalid data directory owner {declared!r}")
    if not spec.get("data"):
        return ""
    return _image_owner(target, sh, image)


def _prepare_volume(req: Dict[str, Any], spec: Dict[str, Any], target: Dict[str, Any], sh: _Runner, emit: Emit) -> None:
    """Create the data volume and, when the image is not root, give that user the directory."""
    volume = req["volume"]
    host_path = volume.startswith("/")
    owner = ""
    if host_path or spec.get("chown_volume"):
        owner = _data_owner(spec, target, sh, req["image"])
    _make_volume(target, sh, volume, owner if host_path else "")
    if owner and not host_path and spec.get("chown_volume"):
        _chown_named_volume(target, sh, volume, str(spec["data"]), owner, req["image"])
    if owner:
        where = volume if host_path else volume + " (Docker volume)"
        emit(f"data directory {where} owned by {owner} (the user the container runs as)")


def _chown_named_volume(target: Dict[str, Any], sh: _Runner, volume: str, mount: str, owner: str, image: str) -> None:
    if not _OWNER_PAIR.match(owner):
        raise ServiceError(f"invalid data directory owner {owner!r}")
    sh(
        docker_argv(
            target,
            ["run", "--rm", "--user", "0", "--network", "none", "--entrypoint", "chown", "-v", f"{volume}:{mount}",
             image, "-R", owner, mount],
        ),
        show=False,
    )


def _make_volume(target: Dict[str, Any], sh: _Runner, volume: str, owner: str = "") -> None:
    """A Docker volume, or the bind-mounted folder under the server's data directory.

    ``owner`` (``uid:gid``) is applied to a bind mount. Images that do not run as root cannot write a
    directory created as the SSH user, and the process then exits with permission denied.
    """
    if not volume.startswith("/"):
        sh(docker_argv(target, ["volume", "create", volume]), show=False)
        return
    if owner and not _OWNER_PAIR.match(owner):
        raise ServiceError(f"invalid data directory owner {owner!r}")
    path = _shq(volume)
    command = f"mkdir -p {path} 2>/dev/null || sudo -n mkdir -p {path}"
    if owner:
        who = _shq(owner)
        command += f" && (chown -R {who} {path} 2>/dev/null || sudo -n chown -R {who} {path})"
    sh(_ssh_argv(target, command), show=False)


def _drop_volume(target: Dict[str, Any], sh: _Runner, volume: str) -> None:
    if not volume.startswith("/"):
        sh(docker_argv(target, ["volume", "rm", volume]), check=False, show=False)
        return
    path = _shq(volume)
    sh(_ssh_argv(target, f"rm -rf {path} 2>/dev/null || sudo -n rm -rf {path}"), check=False)


def _ensure_docker(target: Dict[str, Any], sh: _Runner, *, install: bool) -> None:
    if target.get("method") != "ssh":
        out = sh(["docker", "version", "--format", "{{.Server.Version}}"], check=False, show=False)
        if not re.search(r"\d+\.\d+", out):
            raise ServiceError(
                "Docker is not running on this machine. Start Docker Desktop (or the docker service) and retry."
            )
        return
    probe = "command -v docker >/dev/null 2>&1 && echo present || echo missing"
    out = sh(_ssh_argv(target, probe), show=False)
    if "present" in out:
        return
    if not install:
        raise ServiceError(f"Docker is not installed on {target['host']}; create the `docker` runtime first")
    _install_runtime("docker", target, sh)


def _install_runtime(name: str, target: Dict[str, Any], sh: _Runner, *, version: str = "") -> None:
    from ..providers.onprem_remote import _docker_install_block, _docker_ready_block, _docker_shell_header

    header = _docker_shell_header()
    if name == "docker":
        script = header + _docker_install_block() + _docker_ready_block() + "dk --version\n"
    else:
        script = header + install_script(name, version)
    # A script file: multi-line SSH commands are re-quoted by Windows OpenSSH.
    import tempfile

    from ..providers.onprem_remote import scp_argv

    ssh = ssh_options(target)
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / f"pskit-install-{name}.sh"
        local.write_bytes(script.encode("utf-8"))
        remote = f"/tmp/pskit-install-{name}.sh"  # noqa: S108 - removed right after
        sh(scp_argv(ssh, str(local), remote))
        sh(_ssh_argv(target, f"sh {remote}; code=$?; rm -f {remote}; exit $code"))


def _container_logs(target: Dict[str, Any], sh: _Runner, container: str) -> str:
    return sh(docker_argv(target, ["logs", "--tail", "40", container]), check=False, show=False)


def _fail_ready(spec: Dict[str, Any], why: str, logs: str) -> None:
    text = (logs or "").strip() or "(no logs)"
    hint = ""
    low = text.lower()
    if "permission denied" in low or "os error 13" in low:
        hint = (
            "\nThe data directory is not writable by the user the container runs as. "
            "Create the service again so pskit can fix the directory owner."
        )
    raise ServiceError(f"{spec['label']} {why}. Last log lines:\n{text}{hint}")


def _remote_http_ok(target: Dict[str, Any], sh: _Runner, port: int, path: str) -> bool:
    """True when the server itself gets any HTTP answer from the service (a firewall here does not matter)."""
    url = "http://127.0.0.1:" + str(int(port)) + path
    quoted = _shq(url)
    script = (
        "url=" + quoted + "; "
        "if command -v curl >/dev/null 2>&1; then "
        "code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 \"$url\" || true); "
        "case \"$code\" in [1-5][0-9][0-9]) exit 0;; esac; "
        "fi; "
        "if command -v wget >/dev/null 2>&1; then "
        "wget -S -O /dev/null --timeout=3 \"$url\" 2>&1 | grep -q HTTP/; "
        "else exit 1; fi"
    )
    code, _out = sh.run_fn(_ssh_argv(target, script), None)
    return code == 0


def _wait_ready(
    req: Dict[str, Any], spec: Dict[str, Any], target: Dict[str, Any], sh: _Runner, timeout: float, emit: Emit
) -> None:
    started = time.monotonic()
    deadline = started + timeout
    health = _fill(spec["health"], _values(req))
    emit("waiting for the service to accept connections...")
    while True:
        state = sh(
            docker_argv(target, ["inspect", "-f", "{{.State.Status}}", req["container"]]), check=False, show=False
        ).strip()
        if state and state not in ("running", "created", "restarting"):
            _fail_ready(spec, f"the container stopped ({state})", _container_logs(target, sh, req["container"]))
        if state == "restarting":
            # The process already exited and Docker is starting it again. Waiting out the timeout only hides the cause.
            _fail_ready(
                spec,
                "keeps restarting, so it is not accepting connections",
                _container_logs(target, sh, req["container"]),
            )
        if state == "running":
            if health:
                code, _out = sh.run_fn(docker_argv(target, ["exec", req["container"], "sh", "-c", health]), None)
                if code == 0:
                    return
            elif spec.get("ready_path"):
                # Docker's port proxy accepts TCP before the app listens: wait for an HTTP answer.
                # On an SSH server the check runs there. The port is often closed from this machine.
                path = str(spec["ready_path"])
                if target.get("method") == "ssh" and _remote_http_ok(target, sh, int(req["port"]), path):
                    return
                if _http_answers(f"http://{req['address']}:{req['port']}{path}"):
                    return
            elif _tcp_open(req["address"], req["port"]):
                return
            elif target.get("method") == "ssh" and time.monotonic() - started > 10:
                # The port may be firewalled from here but open to the functions' server.
                emit(f"note: {req['address']}:{req['port']} is not reachable from this machine; check the firewall")
                return
        if time.monotonic() >= deadline:
            _fail_ready(
                spec,
                f"did not become ready within {int(timeout)} s",
                _container_logs(target, sh, req["container"]),
            )
        time.sleep(2)


def _http_answers(url: str) -> bool:
    """True once the URL gives any HTTP response (403 / 400 included)."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=3):  # noqa: S310 - the service just started
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:  # noqa: BLE001 - not listening yet / connection dropped
        return False


def _tcp_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _elasticmq_queue(req: Dict[str, Any], emit: Emit, sh: Optional[_Runner] = None) -> None:
    """Create the queue through the SQS query API (ElasticMQ needs no signature).

    From this machine first; a server's firewall often hides the port from here, so then
    from the server itself over SSH. The driver also recreates it (``create_queue``).
    """
    from urllib.parse import urlencode
    from urllib.request import urlopen

    query = urlencode({"Action": "CreateQueue", "QueueName": req["key"], "Version": "2012-11-05"})
    attempts = 3 if req["target"].get("method") == "ssh" else 15
    for _ in range(attempts):
        try:
            with urlopen(f"http://{req['address']}:{req['port']}/?{query}", timeout=5) as resp:  # noqa: S310
                resp.read()
            emit(f"created queue {req['key']}")
            return
        except OSError:
            time.sleep(2)
    if sh is not None and req["target"].get("method") == "ssh":
        local = f"http://127.0.0.1:{req['port']}/?{query}"
        command = f"curl -fsS {_shq(local)} >/dev/null || wget -qO- {_shq(local)} >/dev/null"
        code, _out = sh.run_fn(_ssh_argv(req["target"], command), None)
        if code == 0:
            emit(f"created queue {req['key']} (from the server; port {req['port']} is not reachable from here)")
            return
    emit(f"note: could not create queue {req['key']} now; the sqs driver creates it on first use (create_queue)")


# service -> (module written to <source>/pskit_drivers/, requirement added to requirements.txt)
DRIVER_TEMPLATES = {
    "rabbitmq": ("rabbitmq_queue", "pika>=1.3"),
    "lavinmq": ("rabbitmq_queue", "pika>=1.3"),
    "kafka": ("kafka_queue", "kafka-python>=2.0.3"),
    "apache-kafka": ("kafka_queue", "kafka-python>=2.0.3"),
    "nats": ("nats_queue", "nats-py>=2.6"),
}


def _add_driver(root: Path, raw: Optional[Dict[str, Any]], service: str) -> None:
    """Copy the driver class into the app (once) and add its client library to requirements."""
    module, requirement = DRIVER_TEMPLATES[service]
    package = ((raw or {}).get("package") or {}) if isinstance((raw or {}).get("package"), dict) else {}
    source = root / str(package.get("source") or ".")
    folder = source / "pskit_drivers"
    folder.mkdir(parents=True, exist_ok=True)
    init = folder / "__init__.py"
    if not init.exists():
        init.write_bytes(b'"""Queue drivers added by pskit for on-premises services."""\n')
    template = Path(__file__).with_name("onprem_templates") / f"{module}.py.txt"
    target = folder / f"{module}.py"
    if not target.exists():
        target.write_bytes(template.read_bytes().replace(b"\r\n", b"\n"))
    reqs = root / str(package.get("requirements") or "requirements.txt")
    text = reqs.read_text("utf-8") if reqs.is_file() else ""
    name = re.split(r"[<>=!~\[ ]", requirement, maxsplit=1)[0]
    if not re.search(rf"^\s*{re.escape(name)}\b", text, re.MULTILINE | re.IGNORECASE):
        reqs.write_bytes((text.rstrip("\n") + ("\n" if text.strip() else "") + requirement + "\n").encode("utf-8"))


# ----------------------------------------------------------------------------- inspect / back up / remove


def _entry(root: Path, key: str) -> Dict[str, Any]:
    entry = load_state(root)["services"].get(key)
    if not isinstance(entry, dict):
        raise ServiceError(f"no on-prem service {key!r} was created from this project")
    return entry


def public_entry(entry: Dict[str, Any], reveal: bool = False) -> Dict[str, Any]:
    """The state entry without secrets (unless ``reveal``), for the UI and ``--json``."""
    out = copy.deepcopy(entry)
    if not reveal and isinstance(out.get("env"), dict):
        out["env"] = {k: ("***" if any(s in k for s in ("PASSWORD", "SECRET", "URL")) else v) for k, v in out["env"].items()}
    if isinstance(out.get("topology"), dict):
        out["topology"] = replication.public(out["topology"])  # replication passwords and key file never leave
    out["target_label"] = describe_target(out.get("target") or {})
    return out


def list_services(root: Path) -> List[Dict[str, Any]]:
    return [public_entry(e) for _k, e in sorted(load_state(root)["services"].items()) if isinstance(e, dict)]


def status(root: Path, key: str, *, run: Optional[RunFn] = None, reveal: bool = False) -> Dict[str, Any]:
    entry = _entry(root, key)
    lines: List[str] = []
    sh = _Runner(lines.append, run)
    target = entry.get("target") or {"method": "local"}
    out = public_entry(entry, reveal)
    if entry.get("kind") == "runtime":
        check = RUNTIMES[entry["service"]]["check"]
        code, text = sh.run_fn(_ssh_argv(target, check), None)
        out.update({"state": "installed" if code == 0 else "missing", "version": text.strip().splitlines()[-1:]})
        return out
    fmt = "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}|{{.State.StartedAt}}|{{.Config.Image}}"
    code, text = sh.run_fn(docker_argv(target, ["inspect", "-f", fmt, entry["container"]]), None)
    if code:
        out.update({"state": "missing", "error": text.strip()[-300:]})
        return out
    parts = (text.strip().splitlines() or [""])[-1].split("|")
    parts += [""] * (4 - len(parts))
    out.update({"state": parts[0], "health": parts[1] or None, "started_at": parts[2], "running_image": parts[3]})
    out["reachable_from_here"] = reachable(str(entry.get("address")), int(entry.get("port") or 0))
    out["gui"] = gui_links(entry)
    out["companion"] = companion_for(str(entry.get("service")))
    out["gui_logins"] = gui_login_choices(str(entry.get("service")))
    spec = SERVICES.get(entry["service"]) or {}
    if parts[0] == "running" and spec.get("health"):
        health = _fill(spec["health"], _values({**entry, "key": key}))
        code, _ = sh.run_fn(docker_argv(target, ["exec", entry["container"], "sh", "-c", health]), None)
        out["ready"] = code == 0
    elif parts[0] == "running":
        out["ready"] = _tcp_open(str(entry.get("address")), int(entry.get("port") or 0))
    if replication.is_replicated(entry):
        out["topology"].update(replication.status(entry, run=run))
    return out


def logs(root: Path, key: str, *, tail: int = 200, run: Optional[RunFn] = None) -> str:
    entry = _entry(root, key)
    if entry.get("kind") == "runtime":
        return ""
    sh = _Runner(lambda _l: None, run)
    _code, text = sh.run_fn(docker_argv(entry["target"], ["logs", "--tail", str(int(tail)), entry["container"]]), None)
    return text


def backup(root: Path, key: str, emit: Emit, *, run: Optional[RunFn] = None, dest: Optional[Path] = None) -> Path:
    """Stream a dump from the container into ``.pskit/backups/<key>-<time>.<ext>``."""
    entry = _entry(root, key)
    spec = SERVICES.get(str(entry.get("service")))
    if not spec or not spec["backup"]:
        raise ServiceError(f"{entry.get('service')} keeps nothing to back up")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = dest or (root / BACKUP_DIR / f"{key}-{stamp}.{spec['backup_ext']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    sh = _Runner(emit, run)
    emit(f"Backing up {key} ({spec['label']}) from {describe_target(entry['target'])}")
    argv = docker_argv(entry["target"], ["exec", entry["container"], "sh", "-c", spec["backup"]])
    try:
        sh(argv, stdout=path)
    except ServiceError:
        path.unlink(missing_ok=True)
        raise
    size = path.stat().st_size if path.is_file() else 0
    if size == 0:
        path.unlink(missing_ok=True)
        raise ServiceError("the backup command produced no data")
    emit(f"saved {path} ({size} bytes)")
    state = load_state(root)
    item = state["services"].get(key)
    if isinstance(item, dict):
        item.setdefault("backups", []).append({"path": str(path), "size": size, "at": _now()})
        del item["backups"][:-20]
        save_state(root, state)
    return path


def remove(
    root: Path, key: str, emit: Emit, *, delete_data: bool = False, run: Optional[RunFn] = None
) -> Dict[str, Any]:
    """Stop and delete the container (and its volume with ``delete_data``) and forget it."""
    entry = _entry(root, key)
    sh = _Runner(emit, run)
    if entry.get("kind") != "runtime":
        gui = entry.get("gui")
        if isinstance(gui, dict):
            sh(docker_argv(entry["target"], ["rm", "-f", gui["container"]]), check=False)
        # The load balancer and the replicas first: they hold the members' private network.
        replication.remove_members(entry, emit, delete_data=delete_data, run=run)
        sh(docker_argv(entry["target"], ["rm", "-f", entry["container"]]), check=False)
        for side in entry.get("sidecars") or []:
            sh(docker_argv(entry["target"], ["rm", "-f", side]), check=False)
            if delete_data:
                _drop_volume(entry["target"], sh, data_mount({"data_dir": entry.get("data_dir")}, side))
        # After the service container: a network with a connected container cannot be removed.
        sh(docker_argv(entry["target"], ["network", "rm", _network(entry)]), check=False, show=False)
        if delete_data and entry.get("volume"):
            _drop_volume(entry["target"], sh, str(entry["volume"]))
        elif entry.get("volume"):
            emit(f"kept the data volume {entry['volume']} (delete it with --delete-data)")
        env_file = root / str(entry.get("env_file") or DEFAULT_ENV_FILE)
        if entry.get("env") and env_file.is_file():
            update_env_file(env_file, {name: None for name in entry["env"]})
    else:
        emit(f"{entry['service']} stays installed on {describe_target(entry['target'])}; pskit only forgets it")
    state = load_state(root)
    state["services"].pop(key, None)
    save_state(root, state)
    return entry


# ----------------------------------------------------------------------------- pskit.yml


def _event_kind(resource_type: str) -> Optional[str]:
    return resource_type if resource_type in ("queue", "storage", "topic", "smtp") else None


def apply_to_raw(raw: Dict[str, Any], entry: Dict[str, Any], attach: Optional[List[str]] = None) -> Dict[str, Any]:
    """``pskit.yml`` (as a dict) with the service's resource, env file and triggers added.

    When the main provider is not ``onprem``, everything goes under ``providers.onprem``
    so the other clouds are unaffected.
    """
    out = copy.deepcopy(raw)
    if entry.get("kind") == "runtime" or not isinstance(entry.get("resource"), dict):
        return out
    key = str(entry["key"])
    resource = copy.deepcopy(entry["resource"])
    onprem_main = ((out.get("provider") or {}).get("name")) == "onprem"
    scope = out if onprem_main else out.setdefault("providers", {}).setdefault("onprem", {})
    scope.setdefault("resources", {})[key] = resource
    if entry.get("env"):
        # `scope` is the whole file when onprem is the main provider, else providers.onprem.
        options = scope.setdefault("provider", {}).setdefault("options", {})
        options.setdefault("env_file", str(entry.get("env_file") or DEFAULT_ENV_FILE))
    kind = _event_kind(str(resource.get("type")))
    names = attach if attach is not None else list(entry.get("attach") or [])
    if kind:
        for fn in names:
            base_fn = (out.get("functions") or {}).get(fn)
            if not isinstance(base_fn, dict):
                raise ServiceError(f"unknown function {fn!r}")
            if onprem_main:
                events = base_fn.setdefault("events", [])
            else:
                override = scope.setdefault("functions", {}).setdefault(fn, {})
                if "events" not in override:
                    override["events"] = copy.deepcopy(base_fn.get("events") or [])
                events = override["events"]
            if not any(isinstance(e, dict) and (e.get(kind) or {}).get("resource") == key for e in events):
                events.append({kind: {"resource": key}})
    # An alert function made for this service (create form: "Create a new function"): added once, never replaced.
    alert: Dict[str, Any] = entry["alert"] if isinstance(entry.get("alert"), dict) else {}
    if alert.get("function") and alert.get("function_handler"):
        functions = out.setdefault("functions", {})
        if alert["function"] not in functions:
            functions[alert["function"]] = {"handler": alert["function_handler"],
                                            "description": f"Alerts of {entry.get('service')} {key} (CPU, memory, "
                                                           "disk, replica lag, down)"}
    return out


def remove_from_raw(raw: Dict[str, Any], key: str) -> Dict[str, Any]:
    """``pskit.yml`` without resource ``key`` and the triggers that use it."""
    out = copy.deepcopy(raw)
    scopes = [out, ((out.get("providers") or {}).get("onprem") or {})]
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        resources = scope.get("resources")
        if isinstance(resources, dict):
            resources.pop(key, None)
            if not resources and scope is not out:
                scope.pop("resources", None)
        for fn in (scope.get("functions") or {}).values():
            if isinstance(fn, dict) and isinstance(fn.get("events"), list):
                fn["events"] = [
                    e
                    for e in fn["events"]
                    if not (isinstance(e, dict) and any(isinstance(v, dict) and v.get("resource") == key for v in e.values()))
                ]
    return out


def snippet(entry: Dict[str, Any]) -> str:
    """The YAML a user would paste by hand."""
    import yaml

    if entry.get("kind") == "runtime":
        return ""
    return yaml.safe_dump({"resources": {entry["key"]: entry["resource"]}}, sort_keys=False)


if __name__ == "__main__":  # pragma: no cover - manual check of the catalog
    json.dump(catalog(), sys.stdout, indent=2)


# ----------------------------------------------------------------------------- how to use (any program)


def client_values(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Names, endpoints and variable names a client needs, from a service's state entry."""
    res = entry.get("resource") or {}
    values: Dict[str, Any] = {"env_file": entry.get("env_file") or DEFAULT_ENV_FILE, "host": entry.get("address"),
                              "container": entry.get("container"),
                              "port": entry.get("port"), "user": entry.get("user") or ""}
    values.update({k: v for k, v in (res.get("connection") or {}).items()})
    values.update({k: v for k, v in (res.get("options") or {}).items() if k not in ("driver", "class")})
    if "bucket" not in values and res.get("type") == "storage":
        values["bucket"] = res.get("name") or entry.get("key")
    values.setdefault("key", entry.get("key"))
    values.setdefault("url_env", _var_prefix(str(entry.get("key"))) + "_URL")
    return values


def service_usage(root: Path, key: str, *, reveal: bool = False, probe: bool = True) -> Dict[str, Any]:
    """Markdown: connection details, credentials, client code (Python / Node.js), terminal and security."""
    from .onprem_clients import direct, flavor_for, markdown

    entry = _entry(root, key)
    if entry.get("kind") == "runtime":
        check = RUNTIMES[entry["service"]]["check"]
        text = (f"# {entry['service']} on {describe_target(entry['target'])}\n\nInstalled by pskit. Check it with:\n\n"
                f"```bash\nssh {entry['target'].get('user')}@{entry['target'].get('host')} '{check}'\n```\n")
        return {"key": key, "markdown": text}
    if entry["service"] == "smtp":
        return {"key": key, "markdown": onprem_smtp.usage_markdown(entry)}
    spec = SERVICES[entry["service"]]
    res = entry.get("resource") or {}
    shown = public_entry(entry, reveal)
    values = client_values(entry)
    role = entry.get("role") or res.get("type")
    md: List[str] = [f"# How to use {spec['label']} `{key}`\n", spec["notes"] + "\n" if spec["notes"] else ""]
    rows = [
        ("Where", describe_target(entry["target"])),
        ("Address", f"`{entry.get('address')}:{entry.get('port')}`"),
        ("Used as", f"`{role}` (resource type `{res.get('type')}`)"),
        ("Container", f"`{entry.get('container')}` (image `{entry.get('image')}`)"),
    ]
    if entry.get("volume"):
        rows.append(("Data volume", f"`{entry['volume']}`"))
    if entry["service"] in NO_AUTH:
        rows.append(("Authentication", "none: keep it on `127.0.0.1` or a private network"))
    else:
        rows.append(("User", f"`{entry.get('user') or 'pskit'}`"))
    for name, value in sorted((shown.get("env") or {}).items()):
        rows.append((f"`{name}`", f"`{value}`"))
    for extra in spec["extra_ports"]:
        rows.append((f"Port {host_port(entry, extra)}", f"http://{entry.get('address')}:{host_port(entry, extra)}"))
    md.append("| | |\n|---|---|\n" + "".join(f"| {a} | {b} |\n" for a, b in rows))
    if probe and not reachable(str(entry.get("address")), int(entry.get("port") or 0)):
        md.append(
            f"**This machine cannot reach `{entry.get('address')}:{entry.get('port')}` right now** (connections time "
            "out or are refused). The service may be fine and only the port closed. Pick one:\n\n"
            f"1. **SSH tunnel** (nothing to open): `pskit resources onprem tunnel {key}` forwards "
            f"`127.0.0.1:{entry.get('port')}` here to the service and prints the variables to use.\n"
            f"2. **Open the port** to your IP in the server's firewall (Azure: network security group inbound rule; "
            "AWS: security group; Linux: `ufw allow`). Keep it closed to the internet.\n"
            "3. **Go through the pskit host** with the pskit client or HTTP (only the host port, usually 8080, must be "
            "open): see *Resources > How to use* for this resource, or `pskit client info`.\n"
        )
    env_file = entry.get("env_file") or DEFAULT_ENV_FILE
    exports = [f"export {n}='<value from {env_file}>'" for n in sorted(entry.get("env") or {})]
    if exports:
        md.append(
            f"The credentials live in `{env_file}` in your project (shipped to the pskit host as `host.env`). "
            "For a script on another machine, export the same variables there"
            + ("" if reveal else " (open *Details > Show values* or `pskit resources onprem status " + key + " --reveal`)")
            + ":\n"
        )
        md.append("```bash\n" + "\n".join(exports) + "\n```\n")
    if entry["service"] in onprem_secretsmanager.SERVICES:
        md.append(onprem_secretsmanager.usage_markdown(entry, _var_prefix(key)))
    elif entry["service"] in onprem_s3.SERVICES:
        bucket = str((res.get("options") or {}).get("bucket") or key)
        md.append(onprem_s3.usage_markdown(entry, _var_prefix(key), bucket))
    else:
        flavor = flavor_for(str(res.get("type")), res.get("options") or {}, res.get("connection") or {},
                            entry["service"])
        snip = direct(flavor, values) if flavor else None
        md.append(markdown(
            "Use it from any program",
            "Any script, web app, cron job or service (not only pskit functions) can add, read and consume data "
            "with the service's own client library:",
            None,
            snip,
            "With the client library",
        ))
    md.append(
        "## Use it from pskit functions\n\n"
        f"Add it to `pskit.yml` (*Add to pskit.yml*, or it was added on create), then open **Resources → How to use** "
        f"on `{key}`, or run `pskit resources usage {key}`: handler code, triggers and tests. Through the deployed "
        "host, scripts can also publish and browse with plain HTTP (shown there).\n"
    )
    md.append(gui_markdown(entry, key))
    md.append(
        "## Security\n\n"
        + (f"- Listens on `{entry.get('bind')}`. " + ("Only this machine can connect. " if entry.get("bind") == "127.0.0.1"
           else "Allow the port only from the servers that need it (cloud security group / firewall). ") + "\n")
        + ("- No authentication in this setup: never publish the port to the internet.\n" if entry["service"] in NO_AUTH else
           "- Change the password: remove the service with *keep data*, create it again with the same key and a new "
           "password (`--password-env`), then redeploy so the host gets the new env file.\n")
        + f"- Keep `{env_file}` and `.pskit/` out of version control.\n"
    )
    md.append(
        "## Test it\n\n```bash\n"
        f"pskit resources onprem status {key}\n"
        f"pskit resources check {key}           # once it is in pskit.yml (from the host when deployed)\n"
        f"pskit resources onprem logs {key}\n```\n"
    )
    return {"key": key, "markdown": "\n".join(md)}


# ----------------------------------------------------------------------------- reachability / tunnels


def reachable(host: str, port: int) -> bool:
    """Can this machine open a TCP connection to ``host:port``? (2 s)"""
    return _tcp_open(host, port)


def tunnel_argv(target: Dict[str, Any], local_port: int, remote_port: int) -> List[str]:
    """``ssh -N -L local:127.0.0.1:remote user@host``: the service's port on localhost here."""
    from ..providers.onprem_remote import _ssh_options, _sshpass, _target

    if target.get("method") != "ssh":
        raise ServiceError("the service runs on this machine; connect to 127.0.0.1 directly")
    ssh = ssh_options(target)
    opts = [o for o in _ssh_options(ssh, port_flag="-p") if o not in ("BatchMode=yes", "BatchMode=no")]
    # _ssh_options pairs every value with "-o"; drop the orphaned flag left by removing BatchMode.
    cleaned: List[str] = []
    for item in opts:
        if cleaned and cleaned[-1] == "-o" and item.startswith("-"):
            cleaned.pop()
        cleaned.append(item)
    return [*_sshpass(ssh), "ssh", "-N", "-L", f"{int(local_port)}:127.0.0.1:{int(remote_port)}", *cleaned, _target(ssh)]


def local_env(entry: Dict[str, Any], local_port: int) -> Dict[str, str]:
    """The service's variables rewritten to reach it through a tunnel on ``127.0.0.1:local_port``."""
    out: Dict[str, str] = {}
    address, port = str(entry.get("address")), str(entry.get("port"))
    for name, value in (entry.get("env") or {}).items():
        out[name] = str(value).replace(f"@{address}:{port}", f"@127.0.0.1:{local_port}")
    return out


# ----------------------------------------------------------------------------- web UIs


def companion_for(service: str) -> Optional[str]:
    return next((name for name, c in COMPANIONS.items() if service in c["for"]), None)


def gui_links(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every web UI of a service: built in (RabbitMQ, MinIO, ...) or a companion pskit started."""
    spec = SERVICES.get(str(entry.get("service"))) or {}
    address = entry.get("address")
    user = entry.get("user") or ""
    out: List[Dict[str, Any]] = []
    for gui in spec.get("gui") or []:
        login = {"user": f"user `{user}`, password in the env file",
                 "signup": "create the admin account on the first visit",
                 "token": f"Token method: the token in {_var_prefix(str(entry.get('key')))}_TOKEN (env file)"}.get(
            str(gui.get("login")), "no login")
        port = host_port(entry, int(gui["port"]))
        out.append({"label": gui["label"], "url": f"http://{address}:{port}{gui.get('path', '/')}",
                    "port": port, "login": login, "kind": "built-in"})
    companion = entry.get("gui")
    if isinstance(companion, dict):
        out.append({"label": companion["label"], "url": f"http://{address}:{companion['port']}/",
                    "port": companion["port"], "login": companion["login"], "kind": "companion",
                    "container": companion["container"]})
    return out


def _network(entry: Dict[str, Any]) -> str:
    return f"{entry['container']}-net"


def _free_gui_port(root: Path, key: str, entry: Dict[str, Any], comp: Dict[str, Any]) -> int:
    """The companion's default port, or the next one no other service on the same server already uses."""
    same = describe_target(entry.get("target") or {})
    used = set()
    for other_key, other in load_state(root)["services"].items():
        if other_key == key or describe_target(other.get("target") or {}) != same:
            continue
        spec = SERVICES.get(str(other.get("service"))) or {}
        used.add(int(other.get("port") or 0))
        used.update(host_port(other, int(extra)) for extra in spec.get("extra_ports") or [])
        if isinstance(other.get("gui"), dict):
            used.add(int(other["gui"].get("port") or 0))
    candidate = int(comp["default_port"])
    while candidate in used:
        candidate += 1
    return candidate


GUI_LOGINS = ("password", "none")


def gui_login_choices(service: str) -> List[str]:
    """How the web UI of ``service`` can sign in: ``password`` and, when the UI allows it, ``none``."""
    name = companion_for(service)
    if name and COMPANIONS[name].get("auth_env"):
        return list(GUI_LOGINS)
    return ["password"] if name else []


def add_gui(
    root: Path,
    key: str,
    emit: Emit,
    *,
    port: Optional[int] = None,
    run: Optional[RunFn] = None,
    login: str = "password",
    password: str = "",
) -> Dict[str, Any]:
    """Start the companion web UI of service ``key`` (Adminer, Redis Commander, Kafka UI, Mongo Express).

    ``login``: ``password`` (generated, or ``password`` when given) or ``none`` (no sign-in: keep the UI on
    127.0.0.1, a private network or behind a tunnel).
    """
    entry = _entry(root, key)
    name = companion_for(str(entry.get("service")))
    if name is None:
        builtin = [g["label"] for g in (SERVICES.get(str(entry.get("service"))) or {}).get("gui") or []]
        raise ServiceError(
            f"{entry.get('service')} has " + (f"a built-in web UI ({', '.join(builtin)})" if builtin else "no web UI pskit can add")
        )
    comp = COMPANIONS[name]
    host_port = int(port or _free_gui_port(root, key, entry, comp))
    if not 1 <= host_port <= 65535:
        raise ServiceError("port must be between 1 and 65535")
    login = str(login or "password")
    if login not in GUI_LOGINS:
        raise ServiceError("login must be password or none")
    if login == "none" and not comp.get("auth_env"):
        raise ServiceError(f"{comp['label']} always asks for a login ({comp['login']})")
    if password and not comp.get("auth_env"):
        raise ServiceError(f"{comp['label']} has no password of its own; it signs in with {comp['login']}")
    if password and not _PASSWORD_OK.match(password):
        raise ServiceError("the web UI password must be 8-128 characters of letters, digits and !#%*+,.:=?@^_~-")
    sh = _Runner(emit, run)
    target = entry["target"]
    container = f"{entry['container']}-ui"
    network = _network(entry)
    spec = SERVICES[entry["service"]]
    env_values = dict(entry.get("env") or {})
    service_password = next(
        (v for k, v in env_values.items() if k.endswith(("_PASSWORD", "_SECRET_KEY")) and not k.endswith("_GUI_PASSWORD")),
        "",
    )
    env_templates = dict(comp["env"])
    if login == "none":
        for name_ in comp.get("auth_env") or ():
            env_templates.pop(name_, None)
        env_templates.update(comp.get("open_env") or {})
    uses_gui_password = "{gui_password}" in json.dumps(env_templates)
    if not uses_gui_password:
        gui_password = ""
    elif password:
        gui_password = password
    elif comp.get("service_password"):
        gui_password = ""  # filled with the service's password below; nothing new to store
    else:
        gui_password = secrets.token_urlsafe(12)
    values = {
        "target": entry["container"],
        "target_port": str(spec["port"]),
        "user": str(entry.get("user") or ""),
        "password": service_password,
        "name": key,
        "gui_password": gui_password or (service_password if comp.get("service_password") else ""),
    }
    sh(docker_argv(target, ["network", "create", network]), check=False, show=False)
    sh(docker_argv(target, ["network", "connect", network, entry["container"]]), check=False, show=False)
    sh(docker_argv(target, ["rm", "-f", container]), check=False, show=False)
    sh(docker_argv(target, ["pull", comp["image"]]))
    argv = ["run", "-d", "--name", container, "--restart", "unless-stopped", "--network", network,
            "--label", f"pskit.gui-for={key}", "-p", f"{entry.get('bind') or '127.0.0.1'}:{host_port}:{comp['port']}"]
    for env_name, template in env_templates.items():
        argv += ["-e", f"{env_name}={_fill(template, values)}"]
    argv.append(comp["image"])
    sh(docker_argv(target, argv))
    login_text = _fill(comp["login"], values)
    if login == "none":
        login_text = "no login"
    elif password and comp.get("service_password"):
        login_text = f"user `{values['user']}`, the web UI password (env file)"
    gui = {"name": name, "label": comp["label"], "container": container, "image": comp["image"], "port": host_port,
           "login": login_text, "login_mode": login}
    if login == "none" and entry.get("bind") != "127.0.0.1":
        emit(f"warning: {comp['label']} has no login and listens on {entry.get('bind')}: anyone who reaches port "
             f"{host_port} can use it. Limit the port to your IP in the firewall, or use a tunnel.")
    if gui_password:
        var = _var_prefix(key) + "_GUI_PASSWORD"
        update_env_file(root / str(entry.get("env_file") or DEFAULT_ENV_FILE), {var: gui_password})
        gui["password_env"] = var
        if comp.get("password_login") or comp.get("service_password"):
            gui["login"] = login_text.replace("the env file", var).replace("(env file)", f"({var})")
        entry.setdefault("env", {})[var] = gui_password
    entry["gui"] = gui
    state = load_state(root)
    state["services"][key] = entry
    save_state(root, state)
    emit(f"{comp['label']} is starting at http://{entry.get('address')}:{host_port}/ ({gui['login']})")
    return gui


def remove_gui(root: Path, key: str, emit: Emit, *, run: Optional[RunFn] = None) -> None:
    entry = _entry(root, key)
    gui = entry.get("gui")
    if not isinstance(gui, dict):
        raise ServiceError(f"{key} has no companion web UI")
    sh = _Runner(emit, run)
    sh(docker_argv(entry["target"], ["rm", "-f", gui["container"]]), check=False)
    sh(docker_argv(entry["target"], ["network", "disconnect", _network(entry), entry["container"]]), check=False, show=False)
    sh(docker_argv(entry["target"], ["network", "rm", _network(entry)]), check=False, show=False)
    if gui.get("password_env"):
        update_env_file(root / str(entry.get("env_file") or DEFAULT_ENV_FILE), {gui["password_env"]: None})
        (entry.get("env") or {}).pop(gui["password_env"], None)
    entry.pop("gui", None)
    state = load_state(root)
    state["services"][key] = entry
    save_state(root, state)


_PRIVATE = re.compile(r"^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|127\.)")

# The UI's HTTP status from the server itself (curl, else wget).
_PROBE = (
    "u={url}; if command -v curl >/dev/null 2>&1; then curl -s -o /dev/null -m 5 -w '%{{http_code}}' \"$u\" || true; "
    "elif command -v wget >/dev/null 2>&1; then wget -S -q -O /dev/null -T 5 \"$u\" 2>&1 | "
    "awk '/^ *HTTP\\//{{c=$2}} END{{print c}}'; else echo unknown; fi"
)

# key=value lines: which cloud (instance metadata), host firewalls, the server's addresses.
_SERVER_FACTS = (
    "md=http://169.254.169.254; cloud=; "
    "if command -v curl >/dev/null 2>&1; then "
    "[ \"$(curl -s -o /dev/null -m 2 -w '%{http_code}' -H Metadata:true \"$md/metadata/instance?api-version=2021-02-01\")\" = 200 ] "
    "&& cloud=azure "
    "&& echo azure_rg=$(curl -s -m 2 -H Metadata:true \"$md/metadata/instance/compute/resourceGroupName?api-version=2021-02-01&format=text\") "
    "&& echo azure_vm=$(curl -s -m 2 -H Metadata:true \"$md/metadata/instance/compute/name?api-version=2021-02-01&format=text\"); "
    "[ -z \"$cloud\" ] && [ \"$(curl -s -o /dev/null -m 2 -w '%{http_code}' -X PUT "
    "-H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \"$md/latest/api/token\")\" = 200 ] && cloud=aws; "
    "[ -z \"$cloud\" ] && [ \"$(curl -s -o /dev/null -m 2 -w '%{http_code}' -H Metadata-Flavor:Google "
    "http://metadata.google.internal/computeMetadata/v1/)\" = 200 ] && cloud=gcp; "
    "fi; echo cloud=$cloud; "
    "echo ufw=$( (ufw status 2>/dev/null || sudo -n ufw status 2>/dev/null) | head -1 | awk '{print $2}'); "
    "echo firewalld=$(systemctl is-active firewalld 2>/dev/null); "
    "echo ips=$(hostname -I 2>/dev/null)"
)


def _probe_here(url: str) -> str:
    """``http NNN``, ``timeout``, ``refused`` or ``error: ...`` for a URL opened from this machine."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=6) as resp:  # noqa: S310 - the user's own service
            return f"http {resp.status}"
    except urllib.error.HTTPError as exc:
        return f"http {exc.code}"
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, socket.timeout) or "timed out" in str(reason):
            return "timeout"
        if isinstance(reason, ConnectionRefusedError) or "refused" in str(reason).lower():
            return "refused"
        return f"error: {reason}"
    except (socket.timeout, TimeoutError):
        return "timeout"
    except Exception as exc:  # noqa: BLE001 - reported to the user
        return f"error: {exc}"


def _port_mappings(text: str) -> Dict[int, List[Tuple[str, int]]]:
    """``docker port`` output -> {container port: [(host ip, host port)]}."""
    out: Dict[int, List[Tuple[str, int]]] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)/tcp\s*->\s*\[?([0-9a-fA-F:.]*)\]?:(\d+)\s*$", line)
        if m:
            out.setdefault(int(m.group(1)), []).append((m.group(2), int(m.group(3))))
    return out


def _firewall_fix(facts: Dict[str, str], port: int, host: str) -> List[str]:
    cloud = facts.get("cloud")
    fixes: List[str] = []
    if cloud == "azure":
        rg, vm = facts.get("azure_rg") or "<resource-group>", facts.get("azure_vm") or "<vm-name>"
        fixes += [
            f"Azure: add an inbound rule for TCP {port} to the network security group, e.g. "
            f"`az vm open-port -g {rg} -n {vm} --port {port} --priority {1000 + port % 3000}`.",
            "Azure applies EVERY NSG on the path: one on the subnet and one on the network interface both need the "
            "rule (VM > Networking lists both). The rule's Source must include your IP (Any to test), its priority "
            "number must be lower than any Deny rule's, the destination port the one above, the protocol TCP.",
        ]
    elif cloud == "aws":
        fixes.append(f"AWS: add an inbound rule for TCP {port} (source: your IP) to the instance's security group; "
                     "check the subnet's network ACL too.")
    elif cloud == "gcp":
        fixes.append(f"GCP: `gcloud compute firewall-rules create pskit-{port} --allow tcp:{port} "
                     "--source-ranges <your-ip>/32` (and the instance's network tags, if the rule uses target tags).")
    else:
        fixes.append(f"Open TCP {port} in the firewall in front of {host} (security group / NSG, router, appliance).")
    if facts.get("ufw") == "active":
        fixes.append(f"ufw is active on the server: `sudo ufw allow {port}/tcp`.")
    if facts.get("firewalld") == "active":
        fixes.append(f"firewalld is active on the server: `sudo firewall-cmd --add-port={port}/tcp --permanent "
                     "&& sudo firewall-cmd --reload`.")
    fixes.append("Your own network can block outgoing ports too (office VPN, proxy): test from another network, or "
                 f"`Test-NetConnection {host} -Port {port}` (Windows) / `nc -vz {host} {port}`.")
    return fixes


def gui_check(
    root: Path,
    key: str,
    emit: Emit,
    *,
    run: Optional[RunFn] = None,
    probe: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """Why a web UI does (not) open: container, port mapping, the server itself, this machine, firewalls.

    Every web UI of service ``key`` is checked on the server (over SSH) and from this machine; each gets a
    verdict and the fix. Nothing is changed.
    """
    entry = _entry(root, key)
    links = gui_links(entry)
    if not links:
        hint = (f"add one with `pskit resources onprem gui {key}`" if companion_for(str(entry.get("service")))
                else "see its guide")
        raise ServiceError(f"{key} has no web UI; {hint}")
    target = entry["target"]
    remote = target.get("method") == "ssh"
    if remote and run is None:
        check_ssh_login(target)
    sh = _Runner(emit, run)
    probe_here = probe or _probe_here
    facts: Dict[str, str] = {}
    if remote:
        _code, text = sh.run_fn(_ssh_argv(target, _SERVER_FACTS), None)
        for line in text.splitlines():
            if "=" in line:
                name, _, value = line.partition("=")
                facts[name.strip()] = value.strip()
    gui_entry = entry.get("gui") if isinstance(entry.get("gui"), dict) else {}
    comp = COMPANIONS.get(str(gui_entry.get("name"))) if gui_entry else None
    spec = SERVICES.get(str(entry.get("service"))) or {}
    results = [_check_link(link, entry, key, comp, spec, facts, sh, probe_here, emit) for link in links]
    for item in results:
        emit(f"{item['label']}: {item['verdict']}")
        for fix in item.get("fix") or []:
            emit(f"  - {fix}")
    return {"key": key, "server": facts, "links": results, "ok": all(r.get("ok") for r in results)}


def _check_link(
    link: Dict[str, Any],
    entry: Dict[str, Any],
    key: str,
    comp: Optional[Dict[str, Any]],
    spec: Dict[str, Any],
    facts: Dict[str, str],
    sh: _Runner,
    probe_here: Callable[[str], str],
    emit: Emit,
) -> Dict[str, Any]:
    target = entry["target"]
    remote = target.get("method") == "ssh"
    address = str(entry.get("address") or "127.0.0.1")
    companion = link["kind"] == "companion"
    container = str(link.get("container") or entry["container"])
    if companion and comp:
        container_port = int(comp["port"])
    else:
        gui: Dict[str, Any] = next((g for g in spec.get("gui") or [] if host_port(entry, int(g["port"])) == link["port"]), {})
        container_port = int(gui.get("port") or link["port"])
    path = urlsplit(link["url"]).path or "/"
    item: Dict[str, Any] = {"label": link["label"], "url": link["url"], "port": link["port"], "container": container}
    fixes: List[str] = []
    item["fix"] = fixes
    logs_hint = f"`pskit resources onprem logs {key}`" + (f" / `docker logs {container}`" if companion else "")
    emit(f"== {link['label']}: {link['url']}")

    code, status = sh.run_fn(docker_argv(target, ["inspect", "-f", "{{.State.Status}}", container]), None)
    lines = status.strip().splitlines()
    item["container_status"] = lines[-1].strip() if code == 0 and lines else "missing"
    emit(f"  container {container}: {item['container_status']}")
    if item["container_status"] != "running":
        item["verdict"] = "the container is not running"
        fixes.append(f"See why: {logs_hint}; then start it again "
                     + (f"with `pskit resources onprem gui {key}`." if companion else "(Remove keeping the data, then Create)."))
        return item

    _code, ports_text = sh.run_fn(docker_argv(target, ["port", container]), None)
    mapped = _port_mappings(ports_text).get(container_port, [])
    item["published"] = [f"{ip or '0.0.0.0'}:{port}" for ip, port in mapped]  # noqa: S104
    emit(f"  published: {', '.join(item['published']) or 'not published'} (container port {container_port})")
    if not mapped:
        item["verdict"] = f"container port {container_port} is not published on the server"
        fixes.append("The container was created without this port (older pskit, or another tool). Recreate it: Remove "
                     "(keep data), then Create with the same key" + (", or add the web UI again." if companion else "."))
        return item
    public = [port for ip, port in mapped if ip not in ("127.0.0.1", "::1")]
    port = public[0] if public else mapped[0][1]
    if port != link["port"]:
        fixes.append(f"The UI is published on port {port}, not {link['port']}: open http://{address}:{port}{path}")

    local_url = f"http://127.0.0.1:{port}{path}"
    if remote:
        _code, answer = sh.run_fn(_ssh_argv(target, _PROBE.format(url=_shq(local_url))), None)
        last = (answer.strip().splitlines() or [""])[-1].strip()
        server = "unknown" if last == "unknown" else (f"http {last}" if last.isdigit() and last != "000" else "no answer")
    else:
        server = probe_here(local_url)
        server = server if server.startswith("http") else "no answer"
    item["on_server"] = server
    emit(f"  on the server ({local_url}): {server}")
    if server == "no answer":
        item["verdict"] = "the UI does not answer on the server itself"
        fixes.append(f"The app inside the container is not serving (still starting, or failed): {logs_hint}. "
                     "Give it a minute after creating, then check again.")
        return item

    if not public and remote:
        item["verdict"] = "published on 127.0.0.1 only: other machines cannot connect"
        fixes.append(f"Open it through SSH: `pskit resources onprem tunnel {key} --remote-port {port}`, then browse "
                     f"http://127.0.0.1:{port}{path}")
        fixes.append("Or recreate the service with Bind 0.0.0.0 (Remove keeping the data, Create with the same key).")
        return item

    url = f"http://{address if public else '127.0.0.1'}:{port}{path}"
    here = probe_here(url)
    item["from_here"] = here
    emit(f"  from this machine ({url}): {here}")
    if here.startswith("http"):
        item["verdict"] = "reachable"
        item["ok"] = True
        fixes.append(f"Open {url} (http://, not https://). Login: {link['login']}.")
        if not public:
            fixes.append("It listens on 127.0.0.1: only this machine can open it (recreate with Bind 0.0.0.0 to share it).")
        return item
    if remote and _PRIVATE.match(address) and address != target.get("host"):
        fixes.append(f"The links use {address}, a private address. From outside that network use the server's public "
                     f"address ({target.get('host')}), or recreate the service with Address set to it.")
    if here == "refused":
        item["verdict"] = "the connection was refused (a host firewall rejects it, or the address is not this server)"
    elif here == "timeout":
        item["verdict"] = "no answer from outside: a firewall drops the connection"
    else:
        item["verdict"] = f"cannot connect from this machine ({here})"
    fixes.extend(_firewall_fix(facts, port, address))
    if remote:
        fixes.append(f"Works right away without opening any port: `pskit resources onprem tunnel {key} "
                     f"--remote-port {port}`, then http://127.0.0.1:{port}{path}")
    return item


def gui_markdown(entry: Dict[str, Any], key: str) -> str:
    """The "Web UI" section of a guide: URLs, logins, tunnel, or how to add one."""
    links = gui_links(entry)
    md = ["## Web UI\n"]
    if links:
        md.append("| UI | Open | Login |\n|---|---|---|\n" + "".join(
            f"| {g['label']} ({g['kind']}) | {g['url']} | {g['login']} |\n" for g in links))
        remote = entry.get("target", {}).get("method") == "ssh"
        first = links[0]
        ports = ", ".join(str(g["port"]) for g in links)
        md.append(
            "The UI listens on the same interface as the service (`" + str(entry.get("bind")) + "`). "
            + (f"From another machine, the server's firewall must allow TCP **{ports}** (the UI's port, not only "
               f"the service's {entry.get('port')}). Or skip the firewall: open it through SSH and browse "
               f"`http://127.0.0.1:{first['port']}`:\n\n```bash\npskit resources onprem tunnel {key} "
               f"--remote-port {first['port']}\n```\n" if remote else "Open the link on this machine.\n")
        )
        md.append(
            "**It does not open?** Check it: the container, the published port, the answer on the server and from "
            "this machine, then the fix (cloud firewall / NSG, bind address, tunnel):\n\n"
            f"```bash\npskit resources onprem gui {key} --check\n```\n\n"
            "In the studio: *On-prem services > Details > Check web UI*. Use `http://`, not `https://`.\n"
        )
    if not isinstance(entry.get("gui"), dict):
        name = companion_for(str(entry.get("service")))
        if name:
            comp = COMPANIONS[name]
            md.append(
                f"{'Add' if not links else 'Also available'}: **{comp['label']}**, started next to the service "
                f"(*On-prem services > Details > Add web UI*, or `pskit resources onprem gui {key}`); "
                f"login: {comp['login']}"
                + (f", or without a password: `pskit resources onprem gui {key} --login none` (keep it private)"
                   if comp.get("auth_env") else "") + ".\n"
            )
        elif not links:
            hint = {
                "azurite": "Use Azure Storage Explorer (desktop): *Attach to a resource > Storage account > Connection "
                "string* and paste the connection string from the env file.",
                "fake-gcs": "No web UI; list buckets with `curl http://<address>:<port>/storage/v1/b`.",
                "memcached": "No web UI; `printf 'stats\\r\\nquit\\r\\n' | nc <address> <port>` shows its counters.",
            }.get(str(entry.get("service")), "This service has no web UI; use its command-line tools shown above.")
            md.append(hint + "\n")
    return "\n".join(md)
