import pytest
from pydantic import ValidationError

from py_serverless_kit.config.schema import EventSpec, FunctionConfig, ScheduleEvent, ServiceConfig, WorkflowConfig


@pytest.mark.parametrize(
    "raw,kind,check",
    [
        ({"http": "POST /a/{id}"}, "http", lambda c: (c.method, c.path) == ("POST", "/a/{id}")),
        ({"http": "/plain"}, "http", lambda c: (c.method, c.path) == ("GET", "/plain")),
        ({"http": {"path": "x", "method": "*"}}, "http", lambda c: (c.method, c.path) == ("ANY", "/x")),
        ({"schedule": "10 minutes"}, "schedule", lambda c: c.rate == "10 minutes"),
        ({"schedule": "0 1 * * *"}, "schedule", lambda c: c.cron == "0 1 * * *"),
        ({"queue": "jobs"}, "queue", lambda c: c.name == "jobs" and c.batch_size == 10),
        ({"storage": "bkt"}, "storage", lambda c: c.bucket == "bkt" and c.events == ["created"]),
        ({"topic": "t"}, "topic", lambda c: c.name == "t"),
    ],
)
def test_event_shorthands(raw, kind, check):
    spec = EventSpec.model_validate(raw)
    assert spec.type == kind and check(spec.config)


@pytest.mark.parametrize("path", ["/a/{bad-name}", "/a/{x}{y}", "/a/{x+}/b"])
def test_invalid_http_paths(path):
    with pytest.raises(ValidationError):
        EventSpec.model_validate({"http": {"path": path}})


def test_schedule_requires_one():
    with pytest.raises(ValidationError):
        ScheduleEvent(rate="5 minutes", cron="* * * * *")
    with pytest.raises(ValidationError):
        ScheduleEvent()
    with pytest.raises(ValidationError):
        ScheduleEvent(cron="* * * *")


def test_function_kind():
    assert FunctionConfig(handler="a.b").kind == "invoke-only"
    assert FunctionConfig(handler="a.b", events=[{"http": "/x"}]).kind == "http"
    assert FunctionConfig(handler="a.b", events=[{"schedule": "1 day"}]).kind == "scheduled"
    assert FunctionConfig(handler="a.b", events=[{"http": "/x"}, {"queue": "q"}]).kind == "http+event"
    assert FunctionConfig(handler="a.b", events=[{"queue": "q"}]).kind == "event-driven"


def test_environment_coerced_to_strings():
    fn = FunctionConfig(handler="a.b", environment={"N": 1, "B": True, "E": None})
    assert fn.environment == {"N": "1", "B": "True", "E": ""}


def test_workflow_graph_validation():
    ok = WorkflowConfig.model_validate(
        {"start_at": "A", "states": {"A": {"type": "task", "function": "f", "next": "B"}, "B": {"type": "succeed"}}}
    )
    assert ok.states["A"].end is False and ok.task_functions() == ["f"]
    with pytest.raises(ValidationError, match="unknown state"):
        WorkflowConfig.model_validate(
            {"start_at": "A", "states": {"A": {"type": "task", "function": "f", "next": "Z"}}}
        )
    with pytest.raises(ValidationError, match="start_at"):
        WorkflowConfig.model_validate({"start_at": "Q", "states": {"A": {"type": "succeed"}}})
    with pytest.raises(ValidationError, match="needs `function`"):
        WorkflowConfig.model_validate({"start_at": "A", "states": {"A": {"type": "task"}}})
    implicit_end = WorkflowConfig.model_validate({"start_at": "A", "states": {"A": {"type": "pass"}}})
    assert implicit_end.states["A"].end is True


def test_workflow_references_unknown_function():
    with pytest.raises(ValidationError, match="unknown function"):
        ServiceConfig.model_validate(
            {
                "service": "svc",
                "provider": {"name": "aws"},
                "functions": {"a": {"handler": "m.a"}},
                "workflows": {"w": {"start_at": "A", "states": {"A": {"type": "task", "function": "zzz"}}}},
            }
        )


# --------------------------------------------------------------------------- resources


def _service(resources, events=None, functions=None):
    return ServiceConfig.model_validate(
        {
            "service": "svc",
            "provider": {"name": "aws"},
            "resources": resources,
            "functions": {"w": {"handler": "app.h.w", "events": events or []}, **(functions or {})},
            "workflows": {},
        }
    )


def test_resource_defaults_and_binding():
    cfg = _service(
        {"jobs": {"type": "queue"}, "db": {"type": "database", "external": True, "connection": {"port": 5432}}},
        events=[{"queue": {"resource": "jobs"}}],
    )
    assert cfg.functions["w"].events_of("queue")[0].name == "jobs"
    assert cfg.resources["db"].connection == {"port": "5432"}
    env = cfg.binding_environment("w")
    assert env["PSKIT_RESOURCES"] == "db,jobs"
    assert env["PSKIT_RESOURCE_DB_PORT"] == "5432" and env["PSKIT_RESOURCE_JOBS_NAME"] == "jobs"


def test_resource_native_name_from_arn_and_revalidation():
    cfg = _service(
        {"t": {"type": "topic", "external": True, "connection": {"arn": "arn:aws:sns:us-east-1:1:shared"}}},
        events=[{"topic": {"resource": "t"}}],
    )
    ev = cfg.functions["w"].events_of("topic")[0]
    assert (ev.name, ev.existing) == ("shared", True)
    # A dumped config (name and resource both set) validates again.
    again = ServiceConfig.model_validate(cfg.model_dump())
    assert again.functions["w"].events_of("topic")[0].name == "shared"


def test_generated_functions_get_only_listed_resources():
    cfg = _service(
        {"a": {"type": "cache", "external": True}},
        functions={"flow-orchestrator": {"handler": "py_serverless_kit.runtime.workflow.orchestrate"}},
    )
    assert cfg.resources_for("w") and not cfg.resources_for("flow-orchestrator")


def test_managed_database_rejected():
    with pytest.raises(ValidationError, match="external: true"):
        _service({"db": {"type": "database"}})


def _with_disabled(**extra):
    base = {
        "service": "svc",
        "provider": {"name": "aws"},
        "functions": {"a": {"handler": "app.a"}, "b": {"handler": "app.b", "enabled": False}},
    }
    base.update(extra)
    return ServiceConfig.model_validate(base)


def test_disabled_functions_and_workflows_are_left_out():
    cfg = _with_disabled(
        resources={"q": {"type": "queue", "functions": ["a", "b"]}},
        workflows={
            "on": {"start_at": "s", "states": {"s": {"type": "task", "function": "a"}}},
            "off": {"enabled": False, "start_at": "s", "states": {"s": {"type": "task", "function": "b"}}},
        },
    )
    assert list(cfg.functions) == ["a"] and list(cfg.workflows) == ["on"]
    assert cfg.resources["q"].functions == ["a"]
    assert cfg.disabled == {"functions": ["b"], "workflows": ["off"]}
    # Survives the copies Project.from_loaded makes.
    assert cfg.model_copy(update={"functions": dict(cfg.functions)}).disabled == cfg.disabled


def test_workflow_calling_a_disabled_function_is_an_error():
    with pytest.raises(ValidationError, match="disabled; disable the workflow too"):
        _with_disabled(workflows={"w": {"start_at": "s", "states": {"s": {"type": "task", "function": "b"}}}})


def test_enabled_is_not_part_of_the_workflow_definition():
    from py_serverless_kit.workflows import definition_dict

    wf = WorkflowConfig.model_validate({"enabled": True, "start_at": "s", "states": {"s": {"type": "pass"}}})
    assert "enabled" not in definition_dict(wf)
