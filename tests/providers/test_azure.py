from __future__ import annotations

import json
import shutil

import pytest

from py_serverless_kit.core.deployer import Deployer
from tests.conftest import full_config


def _errors(project):
    return [i for i in project.validate() if i.level == "error"]


def test_render_full_config(make_project, render):
    project = make_project(full_config("azure", options={"subscription_id": "sub"}))
    assert _errors(project) == []
    tf = render(project)
    res = tf["resource"]
    for rtype in (
        "azurerm_resource_group",
        "azurerm_storage_account",
        "azurerm_service_plan",
        "azurerm_linux_function_app",
        "azurerm_storage_queue",
        "azurerm_storage_container",
        "azurerm_servicebus_namespace",
        "azurerm_servicebus_topic",
        "azurerm_servicebus_subscription",
        "azurerm_application_insights",
    ):
        assert rtype in res, rtype
    app = res["azurerm_linux_function_app"]["app"]
    assert app["zip_deploy_file"] == "${path.module}/artifact.zip"
    assert app["site_config"]["application_stack"]["python_version"] == "3.12"
    settings = app["app_settings"]
    assert settings["SCM_DO_BUILD_DURING_DEPLOYMENT"] == "true"
    assert settings["PSKIT_SERVICE"] == "demo"
    assert "PSKIT_FUNCTION" not in settings and "PSKIT_HANDLER" not in settings
    assert "PSKIT_SERVICEBUS" in settings
    assert len(res["azurerm_storage_account"]["app"]["name"]) <= 24
    assert tf["provider"]["azurerm"][0] == {"features": {}, "subscription_id": "sub"}

    out = tf["output"]["pskit"]["value"]
    assert out["endpoint"].startswith("https://${azurerm_linux_function_app.app.default_hostname}")
    assert out["functions"]["hello"]["url"].endswith("/hello/{name}")
    assert "pipeline" in out["workflows"]  # embedded engine


def test_function_app_shim(make_project):
    project = make_project(full_config("azure"))
    Deployer(project, echo=lambda _m: None).package(skip_deps=True)
    build = project.work_dir / "build"
    src = (build / "function_app.py").read_text()
    compile(src, "function_app.py", "exec")
    assert "@app.route(route='hello/{name}', methods=['GET']" in src
    assert "@app.timer_trigger(schedule='0 */5 * * * *'" in src
    assert "_pskit.timer(timer, 'tick', {'report': 'weekly'})" in src
    assert "queue_name='jobs'" in src
    assert "path='demo-uploads-1234/{name}.csv'" in src
    assert "topic_name='events', subscription_name='worker'" in src
    assert "route='workflows/pipeline'" in src  # orchestrator of the embedded workflow
    host = json.loads((build / "host.json").read_text())
    assert host["extensions"]["http"]["routePrefix"] == ""
    assert (build / "requirements.txt").read_text().strip() == "azure-functions"


def test_greedy_route_and_key_auth(make_project):
    project = make_project("""
    service: demo
    provider: {name: azure}
    functions:
      files:
        handler: app.handlers.hello
        events: [{http: {path: "/files/{path+}", method: ANY, auth: key}}]
    """)
    src = project.provider.shim_files(project.config)["function_app.py"]
    assert "@app.route(route='files/{*path}', auth_level=func.AuthLevel.FUNCTION)" in src


def test_unsupported_combinations(make_project):
    project = make_project("""
    service: demo
    provider: {name: azure}
    functions:
      a:
        handler: app.handlers.hello
        events:
          - http: {path: /a, auth: jwt}
          - storage: {bucket: up, events: [deleted]}
          - topic: {name: t, existing: true}
    """)
    msgs = " ".join(i.message for i in _errors(project))
    assert "auth 'jwt'" in msgs
    assert "created/updated" in msgs
    assert "servicebus_namespace_id" in msgs


def test_unsupported_runtime(make_project):
    project = make_project("""
    service: demo
    provider: {name: azure, runtime: python3.13}
    functions:
      a: {handler: app.handlers.hello}
    """)
    assert any("does not support python3.13" in i.message for i in _errors(project))


NATIVE = """
service: demo
provider: {name: azure, options: {subscription_id: sub}}
functions:
  api:
    handler: app.handlers.hello
    events: [{http: GET /hello}]
  step:
    handler: app.handlers.step
    timeout: 300
workflows:
  orders:
    engine: native
    timeout: 900
    start_at: Check
    states:
      Check: {type: task, function: api, next: Done}
      Done: {type: task, function: step, end: true}
  embedded:
    start_at: Only
    states:
      Only: {type: task, function: step, end: true}
"""


def test_auto_engine_stays_embedded(make_project):
    project = make_project(NATIVE)
    assert project.engines == {"orders": "native", "embedded": "embedded"}
    assert "embedded-orchestrator" in project.config.functions
    assert "orders-orchestrator" not in project.config.functions
    assert "workflow_native" in project.provider.capabilities


def test_native_workflow_renders_logic_app(make_project, render):
    project = make_project(NATIVE)
    issues = project.validate()
    assert [i for i in issues if i.level == "error"] == []
    assert any("time out after 120s" in i.message and "'step'" in i.message for i in issues)
    tf = render(project)
    res = tf["resource"]
    wf = res["azurerm_logic_app_workflow"]["wf_orders"]
    assert wf["name"] == "demo-dev-orders"
    trigger = res["azurerm_logic_app_trigger_http_request"]["wf_orders_trigger"]
    assert trigger == {
        "name": "manual",
        "logic_app_id": "${azurerm_logic_app_workflow.wf_orders.id}",
        "method": "POST",
        "schema": "{}",
    }
    actions = res["azurerm_logic_app_action_custom"]
    labels = sorted(actions)
    # Created one after another, starting after the trigger.
    assert actions[labels[0]]["depends_on"] == ["azurerm_logic_app_trigger_http_request.wf_orders_trigger"]
    for prev, label in zip(labels, labels[1:]):
        assert actions[label]["depends_on"] == [f"azurerm_logic_app_action_custom.{prev}"]
    run = next(a for a in actions.values() if a["name"] == "run")
    assert "https://${azurerm_linux_function_app.app.default_hostname}/_pskit/invoke/api" in run["body"]
    assert "${data.azurerm_function_app_host_keys.keys.default_function_key}" in run["body"]
    json.loads(run["body"].replace("${", "{"))  # a JSON document once Terraform interpolates it
    keys = tf["data"]["azurerm_function_app_host_keys"]["keys"]
    assert keys["name"] == "${azurerm_linux_function_app.app.name}"
    out = tf["output"]["pskit"]["value"]["workflows"]
    assert out["orders"]["url"] == "${azurerm_logic_app_trigger_http_request.wf_orders_trigger.callback_url}"
    assert out["embedded"]["url"].endswith("/workflows/embedded")


def test_native_task_functions_get_invoke_route(make_project):
    project = make_project(NATIVE)
    src = project.provider.shim_files(project.config)["function_app.py"]
    compile(src, "function_app.py", "exec")
    assert "route='_pskit/invoke/api', methods=['POST'], auth_level=func.AuthLevel.FUNCTION" in src
    assert "route='_pskit/invoke/step'" in src
    assert "@app.route(route='hello', methods=['GET']" in src


def test_native_workflow_user_strings_are_escaped(make_project, render):
    project = make_project("""
    service: demo
    provider: {name: azure, options: {subscription_id: sub}}
    functions:
      step: {handler: app.handlers.step}
    workflows:
      flow:
        engine: native
        start_at: P
        states:
          P: {type: pass, result: {text: "${not_terraform}"}, next: F}
          F: {type: fail, error: Boom, cause: "100%{x}"}
    """)
    tf = render(project)
    bodies = " ".join(a["body"] for a in tf["resource"]["azurerm_logic_app_action_custom"].values())
    assert "$${not_terraform}" in bodies
    assert "%%{x}" in bodies


def test_native_workflow_unsupported_glob_is_an_error(make_project):
    project = make_project("""
    service: demo
    provider: {name: azure, options: {subscription_id: sub}}
    functions:
      step: {handler: app.handlers.step}
    workflows:
      flow:
        engine: native
        start_at: C
        states:
          C:
            type: choice
            choices: [{variable: $.name, matches: "a?c", next: D}]
            default: D
          D: {type: succeed}
    """)
    errors = [i for i in project.validate() if i.level == "error"]
    assert errors and errors[0].where == "workflows.flow" and "can't be expressed" in errors[0].message


def test_log_analytics_workspace_output(make_project, render):
    tf = render(make_project(full_config("azure", options={"subscription_id": "sub"})))
    out = tf["output"]["log_analytics_workspace_id"]["value"]
    assert out == "${azurerm_log_analytics_workspace.logs.workspace_id}"
    tf = render(make_project(full_config("azure", options={"subscription_id": "sub", "app_insights": False})))
    assert "log_analytics_workspace_id" not in tf["output"]
    assert "azurerm_log_analytics_workspace" not in tf["resource"]


NODE_SKIP = pytest.mark.skipif(shutil.which("node") is None or shutil.which("npm") is None, reason="needs Node.js and npm")

JS_HANDLERS = {"app/handlers.js": "exports.hello = async () => ({ ok: true });\nexports.tick = async () => null;\n"}


def node_config(provider: str, options: str = "{}", extra: str = "") -> str:
    return f"""
service: demo
provider:
  name: {provider}
  runtime: nodejs20
  options: {options}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: "GET /hello/{{name}}"
  tick:
    handler: app.handlers.tick
{extra}
"""


AZ_OPTS = "{subscription_id: 00000000-0000-0000-0000-000000000000}"


def test_node_shim_registers_every_trigger(make_project):
    extra = """
    events:
      - schedule: {cron: "0 9 * * *", input: {report: daily}}
  worker:
    handler: app.handlers.tick
    events:
      - queue: jobs
      - storage: {bucket: demo-uploads, suffix: .csv}
      - topic: events
workflows:
  flow:
    engine: native
    start_at: s
    states:
      s: {type: task, function: tick}
"""
    project = make_project(node_config("azure", AZ_OPTS, extra), files=JS_HANDLERS)
    files = project.provider.shim_files(project.config)
    assert set(files) == {"pskit_entry.js", "host.json"}
    src = files["pskit_entry.js"]
    assert 'app.http("hello_http_0", { route: "hello/{name}", methods: ["GET"], authLevel: "anonymous"' in src
    assert 'app.timer("tick_schedule_0", { schedule: "0 0 9 * * *"' in src and '{"report": "daily"}' in src
    assert 'app.storageQueue("worker_queue_0", { queueName: "jobs"' in src
    assert 'path: "demo-uploads/{name}.csv"' in src
    assert 'app.serviceBusTopic("worker_topic_2", { topicName: "events", subscriptionName: "worker"' in src
    # The native workflow's task function gets the private invoke route.
    assert 'route: "_pskit/invoke/tick", methods: ["POST"], authLevel: "function"' in src
    package = project.provider.node_package(project.config)
    assert package["main"] == "pskit_entry.js" and "@azure/functions" in package["dependencies"]


def test_node_python_shim_is_unchanged_by_the_refactor(make_project):
    project = make_project(full_config("azure"))
    assert "function_app.py" in project.provider.shim_files(project.config)


@NODE_SKIP
def test_node_render_sets_node_version(make_project, render):
    tf = render(make_project(node_config("azure", AZ_OPTS), files=JS_HANDLERS))
    stack = tf["resource"]["azurerm_linux_function_app"]["app"]["site_config"]["application_stack"]
    assert stack == {"node_version": "20"}
