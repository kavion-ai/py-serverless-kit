"""`resources:` across providers: bindings, standalone managed resources, external lookups."""

from __future__ import annotations

import json

import pytest

from py_serverless_kit.config.loader import ConfigError
from py_serverless_kit.core.describe import build_record

CONFIG = """
service: res
provider:
  name: {provider}
  {extra}
resources:
  uploads: {{type: storage, name: res-uploads-123}}
  jobs: {{type: queue}}
  alerts: {{type: topic, name: res-alerts}}
  legacy: {{type: queue, external: true, name: legacy-q}}
  db:
    type: database
    external: true
    connection: {{host: pg.internal, port: 5432, ssl: true}}
    functions: [api]
functions:
  api:
    handler: app.handlers.hello
    events: [{{http: GET /hello}}]
  worker:
    handler: app.handlers.worker
    events:
      - queue: {{resource: jobs}}
      - queue: {{resource: legacy}}
"""


def _project(make_project, provider, extra=""):
    return make_project(CONFIG.format(provider=provider, extra=extra))


def _errors(project):
    return [str(i) for i in project.validate() if i.level == "error"]


def test_event_resource_resolution(make_project):
    project = _project(make_project, "aws")
    worker = project.config.functions["worker"]
    q1, q2 = worker.events_of("queue")
    assert (q1.name, q1.existing) == ("jobs", False)
    assert (q2.name, q2.existing) == ("legacy-q", True)
    assert project.config.resource_functions("db") == ["api"]
    assert project.config.resource_functions("uploads") == ["api", "worker"]


def test_aws_bindings_iam_and_standalone(make_project, render):
    project = _project(make_project, "aws")
    assert _errors(project) == []
    tf = render(project)
    res = tf["resource"]
    assert res["aws_s3_bucket"]["b_res_uploads_123"]["bucket"] == "res-uploads-123"
    assert res["aws_sns_topic"]["t_res_alerts"]["name"] == "res-alerts"
    assert "q_jobs" in res["aws_sqs_queue"]  # from the event
    assert tf["data"]["aws_sqs_queue"]["q_legacy_q"] == {"name": "legacy-q"}
    env = res["aws_lambda_function"]["api"]["environment"]["variables"]
    assert env["PSKIT_RESOURCES"] == "alerts,db,jobs,legacy,uploads"
    assert env["PSKIT_RESOURCE_UPLOADS_ARN"] == "${aws_s3_bucket.b_res_uploads_123.arn}"
    assert env["PSKIT_RESOURCE_JOBS_URL"] == "${aws_sqs_queue.q_jobs.url}"
    assert env["PSKIT_RESOURCE_LEGACY_ARN"] == "${data.aws_sqs_queue.q_legacy_q.arn}"
    assert env["PSKIT_RESOURCE_DB_HOST"] == "pg.internal" and env["PSKIT_RESOURCE_DB_SSL"] == "true"
    assert env["PSKIT_RESOURCE_DB_EXTERNAL"] == "true"
    worker_env = res["aws_lambda_function"]["worker"]["environment"]["variables"]
    assert "PSKIT_RESOURCE_DB_HOST" not in worker_env
    policy = json.loads(res["aws_iam_role_policy"]["lambda_resources"]["policy"])
    by_action = {s["Action"][0]: s["Resource"] for s in policy["Statement"]}
    assert by_action["s3:GetObject"] == [
        "${aws_s3_bucket.b_res_uploads_123.arn}",
        "${aws_s3_bucket.b_res_uploads_123.arn}/*",
    ]
    assert "${data.aws_sqs_queue.q_legacy_q.arn}" in by_action["sqs:SendMessage"]
    assert by_action["sns:Publish"] == ["${aws_sns_topic.t_res_alerts.arn}"]


def test_aws_external_by_arn_needs_no_lookup(make_project, render):
    project = make_project(
        """
        service: res
        provider: {name: aws}
        resources:
          ext:
            type: queue
            external: true
            connection: {arn: "arn:aws:sqs:eu-west-1:111122223333:shared"}
        functions:
          w: {handler: app.handlers.worker, events: [{queue: {resource: ext}}]}
        """
    )
    assert project.config.functions["w"].events_of("queue")[0].name == "shared"
    tf = render(project)
    env = tf["resource"]["aws_lambda_function"]["w"]["environment"]["variables"]
    assert env["PSKIT_RESOURCE_EXT_ARN"] == "arn:aws:sqs:eu-west-1:111122223333:shared"
    policy = json.loads(tf["resource"]["aws_iam_role_policy"]["lambda_resources"]["policy"])
    assert policy["Statement"][0]["Resource"] == ["arn:aws:sqs:eu-west-1:111122223333:shared"]


def test_gcp_and_azure_standalone(make_project, render):
    gcp = _project(make_project, "gcp", "options: {project: p1}")
    assert _errors(gcp) == []
    tf = render(gcp)
    assert tf["resource"]["google_storage_bucket"]["b_res_uploads_123"]["name"] == "res-uploads-123"
    assert "t_res_alerts" in tf["resource"]["google_pubsub_topic"]
    fn = next(iter(tf["resource"]["google_cloudfunctions2_function"].values()))
    env = fn["service_config"]["environment_variables"]
    assert env["PSKIT_RESOURCE_JOBS_ID"] == "${google_pubsub_topic.t_jobs.id}"

    azure = _project(make_project, "azure", "options: {subscription_id: x}")
    assert _errors(azure) == []
    tf = render(azure)
    assert tf["resource"]["azurerm_storage_container"]["b_res_uploads_123"]["name"] == "res-uploads-123"
    assert tf["resource"]["azurerm_servicebus_topic"]["t_res_alerts"]["name"] == "res-alerts"


@pytest.mark.parametrize("provider", ["alibaba", "cloudflare"])
def test_standalone_is_an_error_elsewhere(make_project, provider):
    project = make_project(
        f"""
        service: res
        provider: {{name: {provider}}}
        resources:
          uploads: {{type: storage}}
          db: {{type: database, external: true, connection: {{url: "postgres://x"}}}}
        functions:
          api: {{handler: app.handlers.hello, events: [{{http: GET /hello}}]}}
        """
    )
    errors = _errors(project)
    assert any("resources.uploads" in e and "external: true" in e for e in errors)
    assert not any("resources.db" in e for e in errors)


def test_onprem_spec_and_drivers(make_project, render):
    project = make_project(
        """
        service: res
        provider: {name: onprem}
        resources:
          jobs:
            type: queue
            external: true
            options: {driver: redis, url: "redis://cache:6379/1"}
          media:
            type: storage
            external: true
            options: {driver: s3, endpoint: "http://minio:9000", bucket: media, access_key: a, secret_key: b}
          scratch: {type: storage}
        functions:
          w:
            handler: app.handlers.worker
            events: [{queue: {resource: jobs}}, {storage: {resource: media}}]
        """
    )
    assert _errors(project) == []
    render(project)
    spec = json.loads((project.work_dir / "onprem_app" / "pskit_host.json").read_text("utf-8"))
    assert spec["resources"]["jobs"] == {
        "type": "queue",
        "external": True,
        "name": "jobs",
        "functions": ["w"],
        "driver": {"use": "redis", "url": "redis://cache:6379/1", "key": "jobs"},
    }
    assert spec["resources"]["scratch"]["driver"] == {"use": "builtin"}
    events = spec["functions"]["w"]["events"]
    assert events[0]["driver"]["use"] == "redis"
    assert events[1]["driver"] == {
        "use": "s3",
        "endpoint": "http://minio:9000",
        "bucket": "media",
        "region": "us-east-1",
        "access_key": "a",
        "secret_key": "b",
        "session_token": "",
        "prefix": "",
        "path_style": True,
    }
    assert spec["functions"]["w"]["environment"]["PSKIT_RESOURCE_MEDIA_TYPE"] == "storage"


@pytest.mark.parametrize(
    "options,message",
    [
        ({"driver": "kafka"}, "driver must be one of"),
        ({"driver": "redis"}, "needs `url"),
        ({"driver": "directory"}, "needs `path`"),
    ],
)
def test_onprem_driver_validation(make_project, options, message):
    project = make_project(
        f"""
        service: res
        provider: {{name: onprem}}
        resources:
          jobs: {{type: queue, options: {json.dumps(options)}}}
        functions:
          w: {{handler: app.handlers.worker, events: [{{queue: {{resource: jobs}}}}]}}
        """
    )
    assert any(message in e for e in _errors(project))


def test_record_lists_resources_without_values(make_project):
    record = build_record(_project(make_project, "aws"))
    assert record["key"] == "aws-dev"
    db = next(r for r in record["resources"] if r["name"] == "db")
    assert db == {
        "name": "db",
        "type": "database",
        "external": True,
        "native_name": "db",
        "functions": ["api"],
        "connection_keys": ["host", "port", "ssl"],
    }
    worker = next(f for f in record["functions"] if f["name"] == "worker")
    assert worker["events"][1]["resource"] == "legacy"
    assert "pg.internal" not in json.dumps(record)


@pytest.mark.parametrize(
    "resources,events,message",
    [
        ("{db: {type: database}}", "[]", "external: true"),
        ("{q: {type: queue}}", "[{storage: {resource: q}}]", "which is a queue"),
        ("{}", "[{queue: {resource: nope}}]", "unknown resource 'nope'"),
        ("{q: {type: queue, name: a}}", "[{queue: {resource: q, name: b}}]", "not both"),
        ("{q: {type: queue, functions: [ghost]}}", "[]", "unknown function 'ghost'"),
        ("{a-b: {type: queue}, a_b: {type: queue}}", "[]", "same variable prefix"),
        ("{q: {type: queue, connection: {name: x}}}", "[]", "reserved"),
        ("{q: {type: queue, connection: {nested: {a: 1}}}}", "[]", "scalar"),
        ("{}", "[{queue: {batch_size: 2}}]", "needs `name` or `resource`"),
    ],
)
def test_schema_errors(make_project, resources, events, message):
    with pytest.raises(ConfigError, match=message):
        make_project(
            f"""
            service: res
            provider: {{name: aws}}
            resources: {resources}
            functions:
              w: {{handler: app.handlers.worker, events: {events}}}
            """
        )


def test_storage_event_bucket_on_a_resource_is_onprem_only(make_project):
    project = make_project(
        """
        service: res
        provider: {name: aws}
        resources: {s: {type: storage}}
        functions:
          w: {handler: app.handlers.worker, events: [{storage: {resource: s, bucket: other}}, {storage: {resource: s}}]}
        """
    )
    errors = [i.message for i in project.validate() if i.level == "error"]
    assert len([e for e in errors if "on-premises only" in e]) == 1, errors


def test_local_runner_injects_bindings(make_project):
    from py_serverless_kit.local import LocalRunner, build_event

    project = make_project(
        """
        service: res
        provider: {name: aws}
        resources:
          db: {type: database, external: true, connection: {host: pg}}
        functions:
          probe: {handler: app.probe.main}
        """,
        files={
            "app/probe.py": """
            from py_serverless_kit import resource

            def main(event, ctx):
                return resource("db").get("host")
            """
        },
    )
    assert LocalRunner(project, env_file=None).invoke("probe", build_event("invoke", None)) == "pg"
