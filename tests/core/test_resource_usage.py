"""`pskit resources usage`: a complete guide for every provider and resource type, with valid code."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from py_serverless_kit.config.schema import PROVIDERS
from py_serverless_kit.core.resource_usage import usage

RESOURCES = """
resources:
  jobs: {type: queue, external: true, name: jobs}
  uploads: {type: storage, external: true, name: uploads, connection: {region: r1, namespace: ns, account_id: acc}}
  events: {type: topic, external: true, name: events}
  orders-db:
    type: database
    external: true
    connection: {host: db.internal, port: 5432, database: orders, password_env: ORDERS_DB_PASSWORD}
  cache: {type: cache, external: true, connection: {host: cache.internal, port: 6379}}
  mail: {type: custom, external: true, connection: {smtp_host: mail.internal, smtp_port: 25}}
functions:
  worker:
    handler: app.handlers.hello
"""

KINDS = {"jobs": "queue", "uploads": "storage", "events": "topic"}


def _blocks(markdown: str, lang: str):
    return re.findall(rf"```{lang}\n(.*?)```", markdown, re.DOTALL)


@pytest.mark.parametrize("provider", [p for p in PROVIDERS])
def test_every_resource_gets_a_complete_guide(make_project, provider):
    project = make_project(f"service: guide\nprovider:\n  name: {provider}\n{RESOURCES}")
    supported = project.provider.capabilities
    for key in ("jobs", "uploads", "events", "orders-db", "cache", "mail"):
        kind = KINDS.get(key)
        if kind and kind not in supported:
            continue
        out = usage(project, None, key)
        md = out["markdown"]
        for heading in ("## 1. Install the libraries", "## 2. Declare it in pskit.yml", "## 3. Use it in your code",
                        "## 4. Test it locally", "## 5. Deploy and test for real", "## 8. Troubleshooting"):
            assert heading in md, (provider, key, heading)
        assert f'resource("{key}")' in md
        for block in _blocks(md, "python"):
            compile(block, f"{provider}-{key}.py", "exec")
        if shutil.which("node"):
            for block in _blocks(md, "js"):
                proc = subprocess.run(["node", "--check", "-"], input=block, capture_output=True, text=True)
                assert proc.returncode == 0, (provider, key, proc.stderr, block)
        if kind:
            assert f"pskit invoke -f worker -t {kind}" in md
        else:
            assert f"pskit resources check {key}" in md


def test_library_choices(make_project):
    project = make_project("service: gg\nprovider:\n  name: aws\n" + RESOURCES)
    assert usage(project, None, "jobs")["requirements"] == {"python": ["boto3"], "node": ["@aws-sdk/client-sqs"]}
    assert usage(project, None, "orders-db")["requirements"]["python"] == ["psycopg[binary]"]
    assert usage(project, None, "cache")["requirements"]["node"] == ["ioredis"]
    oracle = make_project("service: gg\nprovider:\n  name: oracle\n" + RESOURCES)
    storage = usage(oracle, None, "uploads")
    assert "https://ns.compat.objectstorage.r1.oraclecloud.com" in storage["markdown"]
    assert storage["requirements"]["node"] == ["@aws-sdk/client-s3"]
