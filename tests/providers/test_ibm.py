from py_serverless_kit.providers.ibm import size_for
from tests.conftest import full_config

CONFIG = """
service: demo
provider:
  name: ibm
  runtime: python3.11
  memory: 1024
  environment: {GREETING: "${HOME_DIR}"}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: "GET /hello/{name}"
  step:
    handler: app.handlers.step
    memory: 300
"""


def _errors(project):
    return [str(i) for i in project.validate() if i.level == "error"]


def test_full_config_flags_unsupported(make_project):
    errors = _errors(make_project(full_config("ibm")))
    joined = "\n".join(errors)
    assert "python3.12" not in joined  # unpinned runtime falls back to a supported one
    for kind in ("schedule", "queue", "storage", "topic"):
        assert f"`{kind}` events" in joined


def test_render(make_project, render):
    tf = render(make_project(CONFIG))
    assert tf["terraform"]["required_providers"]["ibm"]["source"] == "IBM-Cloud/ibm"
    assert tf["provider"]["ibm"][0]["region"] == "us-south"
    res = tf["resource"]
    assert res["ibm_code_engine_project"]["project"]["name"] == "demo-dev"
    hello = res["ibm_code_engine_function"]["hello"]
    assert hello["runtime"] == "python-3.11"
    assert hello["code_binary"] is True
    assert hello["code_reference"].startswith("data:text/plain;base64,${filebase64(")
    assert (hello["scale_cpu_limit"], hello["scale_memory_limit"]) == ("0.25", "1G")
    assert res["ibm_code_engine_function"]["step"]["scale_memory_limit"] == "0.5G"
    env = {e["name"]: e["value"] for e in hello["run_env_variables"]}
    assert env["PSKIT_FUNCTION"] == "hello"
    assert env["GREETING"] == "$${HOME_DIR}"  # escaped for terraform
    out = tf["output"]["pskit"]["value"]
    assert out["functions"]["hello"]["base_url"] == "${ibm_code_engine_function.hello.endpoint}"
    assert "base_url" not in out["functions"]["step"]


def test_existing_project_and_auth(make_project, render):
    cfg = CONFIG.replace("memory: 1024", "memory: 1024\n  options: {project_id: proj-123}")
    tf = render(make_project(cfg))
    assert "ibm_code_engine_project" not in tf["resource"]
    assert tf["resource"]["ibm_code_engine_function"]["hello"]["project_id"] == "proj-123"
    bad = make_project(CONFIG.replace('"GET /hello/{name}"', "{path: /x, auth: jwt}"))
    assert any("auth `jwt`" in e for e in _errors(bad))


def test_size_mapping():
    assert size_for(128) == ("0.125", "0.5G")
    assert size_for(2048) == ("0.5", "2G")
    assert size_for(9999) == ("1", "4G")
