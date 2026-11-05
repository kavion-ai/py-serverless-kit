"""Dead-letter queues: ``dlq:`` in pskit.yml, what each provider generates, and ``pskit dlq`` end to end."""

from __future__ import annotations

import json
import threading
import time

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from py_serverless_kit.cli.main import cli
from py_serverless_kit.config.schema import FunctionConfig
from py_serverless_kit.core import dlq as core
from py_serverless_kit.core.deployer import Deployer
from py_serverless_kit.core.testing import TriggerError
from py_serverless_kit.runtime import dead_letters
from py_serverless_kit.runtime.onprem_host import Host, activate_layout
from py_serverless_kit.vault import permissions


def _yaml(provider: str, fn: str = "dlq: {queue: orders-dlq, max_retries: 2}", options: str = "{}") -> str:
    return f"""
    service: svc
    provider: {{name: {provider}, region: us-east-1, options: {options}}}
    functions:
      worker:
        handler: app.handlers.worker
        {fn}
        events: [{{queue: {{name: orders}}}}]
    """


# ------------------------------------------------------------------ config
@pytest.mark.parametrize(
    ("value", "queue", "retries"),
    [(True, None, 4), ("my-dlq", "my-dlq", 4), ({"queue": "q", "max_retries": 1}, "q", 1), ({}, None, 4)],
)
def test_dlq_shorthands(value, queue, retries):
    parsed = FunctionConfig(handler="a.b", dlq=value).dlq
    assert parsed.queue == queue and parsed.max_retries == retries


def test_dlq_can_be_off_and_retries_are_checked():
    assert FunctionConfig(handler="a.b", dlq=False).dlq is None
    with pytest.raises(ValidationError):
        FunctionConfig(handler="a.b", dlq={"max_retries": -1})
    with pytest.raises(ValidationError):
        FunctionConfig(handler="a.b", dlq={"nope": 1})


def test_dlq_fills_queue_events_and_what_an_event_sets_wins(make_project):
    project = make_project("""
    service: svc
    provider: {name: aws, region: us-east-1}
    resources:
      failures: {type: queue, name: failures-native}
      bucket: {type: storage}
    functions:
      a:
        handler: app.handlers.worker
        dlq: true
        events: [{queue: {name: q1}}]
      b:
        handler: app.handlers.worker
        dlq: {queue: failures, max_retries: 2}
        events:
          - queue: {name: q2}
          - queue: {name: q3, dead_letter: own, max_receive: 9}
      c:
        handler: app.handlers.worker
        events: [{queue: {name: q4}}]
    """)
    fns = project.config.functions
    first = fns["a"].events_of("queue")[0]
    assert (first.dead_letter, first.max_receive) == ("a-dlq", 5)
    second, third = fns["b"].events_of("queue")
    assert (second.dead_letter, second.max_receive) == ("failures-native", 3)
    assert (third.dead_letter, third.max_receive) == ("own", 9)
    assert fns["c"].events_of("queue")[0].dead_letter is None


def test_dlq_cannot_name_a_resource_of_another_type(make_project):
    with pytest.raises(Exception, match="dlq names resource 'bucket', which is a storage"):
        make_project("""
        service: svc
        provider: {name: aws, region: us-east-1}
        resources: {bucket: {type: storage}}
        functions:
          a:
            handler: app.handlers.worker
            dlq: bucket
            events: [{queue: {name: q1}}]
        """)


def _issues(project):
    return [(i.level, i.message) for i in project.provider.validate(project.config)]


def test_providers_without_dead_letter_queues_refuse_it(make_project):
    project = make_project(_yaml("alibaba"))
    assert any(level == "error" and "dead-letter" in text for level, text in _issues(project))


def test_dlq_without_a_queue_trigger_is_a_warning(make_project):
    project = make_project("""
    service: svc
    provider: {name: aws, region: us-east-1}
    functions:
      a: {handler: app.handlers.worker, dlq: true}
    """)
    assert ("warning", "`dlq` only applies to queue triggers, and this function has none") in _issues(project)


# ------------------------------------------------------------------ providers
def test_aws_redrive(make_project, render):
    tf = render(make_project(_yaml("aws")))
    queues = tf["resource"]["aws_sqs_queue"]
    assert queues["q-orders-dlq".replace("-", "_")]["name"] == "orders-dlq"
    policy = queues["q_orders"]["redrive_policy"]
    assert '"maxReceiveCount":3' in policy and "q_orders_dlq.arn" in policy


def test_aws_warns_about_an_existing_queue(make_project):
    project = make_project(_yaml("aws").replace("{name: orders}", "{name: orders, existing: true}"))
    assert any(level == "warning" and "redrive policy" in text for level, text in _issues(project))


def test_azure_poison_queue_and_delivery_limit(make_project, render):
    project = make_project(_yaml("azure", "dlq: {max_retries: 2}").replace("us-east-1", "eastus"))
    assert not any("ignored" in text for _level, text in _issues(project))
    tf = render(project)
    assert {q["name"] for q in tf["resource"]["azurerm_storage_queue"].values()} >= {"orders", "orders-poison"}
    host = json.loads((project.work_dir / "build" / "host.json").read_text("utf-8")) if (
        project.work_dir / "build" / "host.json").is_file() else json.loads(project.provider._host_json(project.config))
    assert host["extensions"]["queues"]["maxDequeueCount"] == 3


def test_azure_says_when_a_queue_name_cannot_be_used_and_when_limits_differ(make_project):
    named = make_project(_yaml("azure").replace("us-east-1", "eastus"))
    assert any("dead_letter is ignored" in text for _level, text in _issues(named))
    differ = make_project("""
    service: svc
    provider: {name: azure, region: eastus}
    functions:
      a:
        handler: app.handlers.worker
        dlq: {max_retries: 1}
        events: [{queue: {name: one}}]
      b:
        handler: app.handlers.worker
        dlq: {max_retries: 7}
        events: [{queue: {name: two}}]
    """)
    assert any("using 8" in text for _level, text in _issues(differ))


GCP = '{project: p1}'


def test_gcp_uses_a_push_subscription_with_a_dead_letter_policy(make_project, render):
    project = make_project(_yaml("gcp", "dlq: {queue: orders-dlq, max_retries: 6}", GCP))
    assert not [text for level, text in _issues(project) if level == "error"]
    tf = render(project)
    fn = tf["resource"]["google_cloudfunctions2_function"]["worker"]
    assert "event_trigger" not in fn and fn["build_config"]["entry_point"] == "pskit_http"
    assert fn["service_config"]["environment_variables"]["PSKIT_TRIGGER_KIND"] == "queue"
    subs = tf["resource"]["google_pubsub_subscription"]
    push = subs["worker_push"]
    assert push["dead_letter_policy"]["max_delivery_attempts"] == 7
    assert "orders_dlq.id" in push["dead_letter_policy"]["dead_letter_topic"]
    assert "google_cloudfunctions2_function.worker.url" in push["push_config"]["push_endpoint"]
    assert subs["dead_orders_dlq"]["name"] == "orders-dlq" + core.GCP_SUBSCRIPTION_SUFFIX
    # The Pub/Sub service agent moves the messages: it needs both of these.
    assert "gcp-sa-pubsub" in tf["resource"]["google_pubsub_topic_iam_member"]["dead_orders_dlq_agent"]["member"]
    assert "worker_push_agent" in tf["resource"]["google_pubsub_subscription_iam_member"]
    assert tf["data"]["google_project"]["pskit"]["project_id"] == "p1"


def test_gcp_without_a_dlq_keeps_the_eventarc_trigger(make_project, render):
    tf = render(make_project(_yaml("gcp", "description: plain", GCP)))
    assert "event_trigger" in tf["resource"]["google_cloudfunctions2_function"]["worker"]
    assert "google_pubsub_subscription" not in tf["resource"]


def test_gcp_dead_letter_on_an_event_alone_changes_nothing_for_existing_projects(make_project, render):
    project = make_project(_yaml("gcp", "description: plain", GCP).replace(
        "{name: orders}", "{name: orders, dead_letter: d, max_receive: 3}"))
    assert [(level, text[:30]) for level, text in _issues(project) if "dead_letter" in text] == [
        ("warning", "queue.dead_letter is not appli")]
    assert "event_trigger" in render(project)["resource"]["google_cloudfunctions2_function"]["worker"]
    assert core.dead_letter_queues(project.config) == []


def test_gcp_refuses_a_limit_pubsub_does_not_allow(make_project):
    project = make_project(_yaml("gcp", "dlq: {max_retries: 2}", GCP))
    assert any(level == "error" and "5 to 100" in text for level, text in _issues(project))


# ------------------------------------------------------------------ which queues
def test_dead_letter_queues_of_a_project(make_project):
    aws = make_project(_yaml("aws")).config
    assert [(q.name, q.sources, q.functions, q.max_receive) for q in core.dead_letter_queues(aws)] == [
        ("orders-dlq", ["orders"], ["worker"], 3)]
    assert core.find_queue(aws, "worker").name == core.find_queue(aws, "orders-dlq").name == "orders-dlq"
    with pytest.raises(TriggerError, match="no dead-letter queue for 'nope'"):
        core.find_queue(aws, "nope")
    azure = make_project(_yaml("azure", "description: plain").replace("us-east-1", "eastus")).config
    assert [q.name for q in core.dead_letter_queues(azure)] == ["orders-poison"]


def test_a_function_with_several_dead_letter_queues_must_say_which(make_project):
    config = make_project("""
    service: svc
    provider: {name: aws, region: us-east-1}
    functions:
      a:
        handler: app.handlers.worker
        events: [{queue: {name: one, dead_letter: d1}}, {queue: {name: two, dead_letter: d2}}]
    """).config
    with pytest.raises(TriggerError, match="d1 or d2"):
        core.find_queue(config, "a")


# ------------------------------------------------------------------ walking a queue
class FakeQueue:
    """Visibility like the services: a claimed message stays hidden until it is settled."""

    def __init__(self, messages, hiccups=0):
        self.messages = {m["id"]: dict(m) for m in messages}
        self.hidden = set()
        self.hiccups = hiccups
        self.released = []

    def claim(self, batch, visibility, now):
        if self.hiccups:
            self.hiccups -= 1
            return []
        free = [m for i, m in self.messages.items() if i not in self.hidden][:batch]
        self.hidden |= {m["id"] for m in free}
        return [{**m, "_handle": "h"} for m in free]

    def settle(self, claimed, failed_ids, max_receive, dead_letter, now):
        assert dead_letter is None
        for msg in claimed:
            self.hidden.discard(msg["id"])
            if msg["id"] in failed_ids:
                self.released.append(msg["id"])
            else:
                del self.messages[msg["id"]]


def _messages(count, **attrs):
    return [{"id": f"m{i}", "body": f"b{i}", "attributes": dict(attrs)} for i in range(count)]


def _no_sleep(_seconds):
    return None


def test_page_gives_everything_back_and_hides_private_keys():
    queue = FakeQueue(_messages(25))
    items = dead_letters.page(queue, 12, 5, 0.0, sleep=_no_sleep)
    assert [m["id"] for m in items] == ["m12", "m13", "m14", "m15", "m16"]
    assert "_handle" not in items[0] and not queue.hidden and len(queue.messages) == 25
    assert dead_letters.page(queue, 0, 1, 0.0, ident="m17", sleep=_no_sleep)[0]["body"] == "b17" and not queue.hidden
    assert dead_letters.page(queue, 0, 1, 0.0, ident="nope", sleep=_no_sleep) == [] and not queue.hidden


def test_an_empty_answer_now_and_then_does_not_end_a_walk():
    assert len(dead_letters.page(FakeQueue(_messages(3), hiccups=2), 0, 10, 0.0, sleep=_no_sleep)) == 3


def _replay(queue, ids, to="orders", fail=()):
    sent = []

    def submit(name, body, attributes):
        if body in fail:
            raise OSError("queue down")
        sent.append((name, body, attributes))

    result = dead_letters.replay(queue, submit, lambda _m: to, ids, 0.0, sleep=_no_sleep)
    return result, sent


def test_replay_all_moves_every_message():
    queue = FakeQueue(_messages(23))
    result, sent = _replay(queue, None)
    assert len(result["replayed"]) == 23 and not queue.messages and len(sent) == 23
    assert result["failed"] == [] and result["missing"] == []


def test_replay_one_leaves_the_others_visible_and_reports_unknown_ids():
    queue = FakeQueue(_messages(5))
    result, sent = _replay(queue, ["m3", "nope"])
    assert [r["id"] for r in result["replayed"]] == ["m3"] and result["missing"] == ["nope"]
    assert [s[1] for s in sent] == ["b3"] and set(queue.messages) == {"m0", "m1", "m2", "m4"} and not queue.hidden


def test_a_message_that_cannot_be_sent_stays_in_the_queue():
    queue = FakeQueue(_messages(3))
    result, _sent = _replay(queue, None, fail=("b1",))
    assert [f["id"] for f in result["failed"]] == ["m1"] and "queue down" in result["failed"][0]["error"]
    assert set(queue.messages) == {"m1"} and not queue.hidden


def test_a_message_with_no_known_source_stays_in_the_queue():
    queue = FakeQueue(_messages(1))
    result, sent = _replay(queue, None, to=None)
    assert sent == [] and "--to" in result["failed"][0]["error"] and "m0" in queue.messages


def test_replayed_messages_lose_the_marks_of_the_move_and_count_replays():
    assert dead_letters.replay_attributes({
        "type": "order", "pskit_source_queue": "q", "pskit_receives": 3, "pskit_error": "x", "pskit_dead_at": 1,
        "CloudPubSubDeadLetterSourceDeliveryCount": "5", "pskit_replays": "2",
    }) == {"type": "order", "pskit_replays": 3}


# ------------------------------------------------------------------ on premises, for real
HANDLERS = """
def worker(event, ctx):
    from pathlib import Path
    for record in event.records:
        if record.text() == "poison" and not Path(ctx.env["FIXED"]).exists():
            raise ValueError("cannot read this order")
        with open(ctx.env["SEEN"], "a") as handle:
            handle.write(record.text() + "\\n")
"""


@pytest.fixture
def onprem(make_project, tmp_path, monkeypatch):
    project = make_project(f"""
    service: svc
    provider:
      name: onprem
      options: {{data_dir: {(tmp_path / 'data').as_posix()}}}
    functions:
      worker:
        handler: app.handlers.worker
        environment: {{SEEN: {(tmp_path / 'seen.txt').as_posix()}, FIXED: {(tmp_path / 'fixed').as_posix()}}}
        dlq: {{queue: orders-dlq, max_retries: 1}}
        events: [{{queue: {{name: orders, batch_size: 1}}}}]
    """, files={"app/handlers.py": HANDLERS})
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    root = project.work_dir / "onprem_app"
    activate_layout(root)
    host = Host(root)
    host.open()
    httpd = host.make_server(0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    from py_serverless_kit.core import onprem_control

    token = str(host.spec.get("admin_token") or "")
    monkeypatch.setattr(core, "_host", lambda *_a: onprem_control.HostControl(base, token))
    monkeypatch.chdir(project.root)
    yield project, host, tmp_path
    httpd.shutdown()
    httpd.server_close()


def _fail_to_dlq(host, message="poison"):
    host.broker.submit_queue("orders", message)
    for _ in range(3):
        host.pump_queues(time.time() + 1000)


def test_a_failing_message_reaches_the_dlq_after_its_retries_and_replay_runs_it_again(onprem):
    project, host, tmp = onprem
    host.broker.submit_queue("orders", "fine")
    _fail_to_dlq(host)
    assert host.broker.queue_depth("orders") == 0 and host.broker.queue_depth("orders-dlq") == 1
    assert (tmp / "seen.txt").read_text().split() == ["fine"]

    assert core.overview(project, {})[0]["depth"] == 1
    page = core.messages(project, {}, "worker")
    assert page["total"] == 1 and page["items"][0]["body"] == "poison"
    ident = page["items"][0]["id"]
    assert host.broker.queue_depth("orders-dlq") == 1  # reading consumes nothing

    item = core.inspect(project, {}, "worker", ident)
    attrs = item["attributes"]
    assert attrs["pskit_source_queue"] == "orders" and attrs["pskit_receives"] == 2
    assert "cannot read this order" in attrs["pskit_error"]

    # Replayed before the fix, it fails its retries and comes back.
    assert core.replay(project, {}, "worker", [ident])["replayed"] == [{"id": ident, "to": "orders"}]
    assert host.broker.queue_depth("orders-dlq") == 0 and host.broker.queue_depth("orders") == 1
    for _ in range(3):
        host.pump_queues(time.time() + 1000)
    back = core.messages(project, {}, "worker")["items"][0]
    assert back["attributes"]["pskit_replays"] == 1

    (tmp / "fixed").write_text("")
    assert len(core.replay(project, {}, "worker", None)["replayed"]) == 1
    host.pump_queues(time.time() + 1000)
    assert (tmp / "seen.txt").read_text().split() == ["fine", "poison"]
    assert host.broker.queue_depth("orders") == 0 and host.broker.queue_depth("orders-dlq") == 0


def test_cli_list_inspect_replay(onprem):
    project, host, _tmp = onprem
    for _ in range(2):
        _fail_to_dlq(host)
    run = CliRunner().invoke
    shown = run(cli, ["dlq", "list"])
    assert shown.exit_code == 0 and "orders-dlq: 2 message(s)" in shown.output and "moved after 2 deliveries" in shown.output
    listed = json.loads(run(cli, ["dlq", "list", "worker", "-n", "1", "--json"]).output)
    assert listed["total"] == 2 and len(listed["items"]) == 1
    assert "next page: pskit dlq list worker --offset 1 -n 1" in run(cli, ["dlq", "list", "worker", "-n", "1"]).output
    ident = listed["items"][0]["id"]
    full = run(cli, ["dlq", "inspect", "worker", ident])
    assert full.exit_code == 0 and "poison" in full.output and "pskit_source_queue" in full.output

    assert run(cli, ["dlq", "replay", "worker"]).exit_code != 0
    assert run(cli, ["dlq", "replay", "worker", ident, "--all"]).exit_code != 0
    missing = run(cli, ["dlq", "replay", "worker", "nope"])
    assert missing.exit_code == 1 and "nope: not in orders-dlq" in missing.output
    assert run(cli, ["dlq", "replay", "worker", "--to", "typo", "--all", "-y"]).exit_code == 1
    assert host.broker.queue_depth("orders-dlq") == 2

    one = run(cli, ["dlq", "replay", "worker", ident])
    assert one.exit_code == 0 and "Replayed 1 message(s)" in one.output and f"{ident} -> orders" in one.output
    assert host.broker.queue_depth("orders-dlq") == 1
    assert run(cli, ["dlq", "replay", "worker", "--all"], input="n\n").exit_code != 0
    assert host.broker.queue_depth("orders-dlq") == 1
    assert run(cli, ["dlq", "replay", "worker", "--all", "-y"]).exit_code == 0
    assert host.broker.queue_depth("orders-dlq") == 0 and host.broker.queue_depth("orders") == 2


def test_only_known_queues_can_be_read(onprem):
    project, _host, _tmp = onprem
    with pytest.raises(TriggerError, match="unknown queue"):
        core._host_request(project, {}, "GET", "/__pskit/queues/other/messages")


def test_a_driver_queue_as_dlq_is_walked_and_tagged(onprem):
    _project, host, _tmp = onprem
    fake = FakeQueue([])
    fake.submit = lambda body, attrs: fake.messages.setdefault(  # type: ignore[attr-defined]
        "d1", {"id": "d1", "body": body, "attributes": dict(attrs)}
    )["id"]
    fake.depth = lambda: len(fake.messages)  # type: ignore[attr-defined]
    host.broker._queue_drivers["orders-dlq"] = fake
    _fail_to_dlq(host)
    page = host.broker.queue_messages("orders-dlq", 0, 10, time.time())
    assert page["total"] == 1 and page["items"][0]["attributes"]["pskit_source_queue"] == "orders"


# ------------------------------------------------------------------ the clouds' queue calls
class FakeSqsClient:
    def __init__(self):
        self.sent = []
        self.deleted = []
        self.visible = []
        self.waiting = [{
            "MessageId": "m1", "ReceiptHandle": "r1", "Body": "b1",
            "Attributes": {"ApproximateReceiveCount": "4", "DeadLetterQueueSourceArn": "arn:aws:sqs:us-east-1:1:orders"},
            "MessageAttributes": {"type": {"DataType": "String", "StringValue": "order"}},
        }]

    def get_queue_url(self, QueueName):  # noqa: N803
        return {"QueueUrl": f"https://sqs/{QueueName}"}

    def receive_message(self, **kwargs):
        assert kwargs["WaitTimeSeconds"] > 0  # a short poll can miss messages
        out, self.waiting = self.waiting, []
        return {"Messages": out}

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "new"}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs["ReceiptHandle"])

    def change_message_visibility(self, **kwargs):
        self.visible.append(kwargs["ReceiptHandle"])

    def get_queue_attributes(self, **_kwargs):
        return {"Attributes": {"ApproximateNumberOfMessages": "7"}}


class FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self, _service):
        return self._client


def test_aws_replay_goes_to_the_queue_sqs_recorded(make_project, monkeypatch):
    project = make_project(_yaml("aws"))
    client = FakeSqsClient()
    monkeypatch.setattr(core, "_boto3", lambda _region: FakeSession(client))
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    assert core.overview(project, None)[0]["depth"] == 7
    assert core.replay(project, None, "worker", None)["replayed"] == [{"id": "m1", "to": "orders"}]
    sent = client.sent[0]
    assert sent["QueueUrl"] == "https://sqs/orders" and sent["MessageBody"] == "b1"
    assert sent["MessageAttributes"]["type"]["StringValue"] == "order" and client.deleted == ["r1"]


def test_aws_listing_gives_messages_back(make_project, monkeypatch):
    project = make_project(_yaml("aws"))
    client = FakeSqsClient()
    monkeypatch.setattr(core, "_boto3", lambda _region: FakeSession(client))
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    page = core.messages(project, None, "worker")
    assert page["total"] == 7 and page["items"][0]["attributes"]["pskit_source_queue"] == "orders"
    assert client.visible == ["r1"] and client.deleted == [] and client.sent == []


def test_cloud_errors_are_one_line(make_project, monkeypatch):
    project = make_project(_yaml("aws"))

    def boom(_region):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(core, "_boto3", boom)
    with pytest.raises(TriggerError, match="RuntimeError: no credentials"):
        core.messages(project, None, "worker")
    assert "no credentials" in core.overview(project, None)[0]["error"]


def test_azure_reads_the_poison_queue_and_gcp_the_subscription(make_project, monkeypatch):
    azure = make_project(_yaml("azure", "dlq: true").replace("us-east-1", "eastus"))
    monkeypatch.setattr(core, "azure_connections", lambda _p: {
        "storage": "DefaultEndpointsProtocol=https;AccountName=a;AccountKey=a2V5;EndpointSuffix=core.windows.net"})
    assert core._driver(azure, "orders-poison").queue == "orders-poison"
    gcp = make_project(_yaml("gcp", "dlq: true", GCP))
    dead = core._driver(gcp, "orders-dlq")
    assert dead.subscription == "projects/p1/subscriptions/orders-dlq-sub"
    assert core._driver(gcp, "orders", dead=False).topic == "projects/p1/topics/orders"


def test_other_providers_are_told(make_project):
    project = make_project(_yaml("alibaba", "description: plain"))
    with pytest.raises(TriggerError, match="this project deploys to alibaba"):
        core.overview(project, None)


def test_permissions():
    assert permissions.cli_permission(["dlq", "list"]) == ("resources", "r")
    assert permissions.cli_permission(["dlq", "inspect"]) == ("resources", "r")
    assert permissions.cli_permission(["dlq", "replay"]) == ("resources", "u")
