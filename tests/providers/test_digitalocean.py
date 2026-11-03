import yaml

from tests.conftest import full_config

CONFIG = """
service: demo
provider:
  name: digitalocean
  runtime: python3.11
  options: {namespace: fn-1234, api_host: "https://faas-nyc1-abc.doserverless.co/"}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: "GET /hello/{name}"
  tick:
    handler: app.handlers.tick
    events:
      - schedule: 5 minutes
      - schedule: {cron: "0 12 * * 1", input: {r: 1}}
"""


def _errors(project):
    return [str(i) for i in project.validate() if i.level == "error"]


def test_full_config_flags_unsupported(make_project):
    joined = "\n".join(_errors(make_project(full_config("digitalocean"))))
    assert "options.namespace is required" in joined
    assert "python3.12" not in joined  # unpinned runtime falls back to a supported one
    for kind in ("queue", "storage", "topic"):
        assert f"`{kind}` events" in joined
    assert "`schedule` events" not in joined


def test_render(make_project, render):
    project = make_project(CONFIG)
    assert _errors(project) == []
    tf = render(project)
    assert "provider" not in tf
    assert tf["terraform"]["required_providers"] == {}
    deploy = tf["resource"]["terraform_data"]["deploy"]
    assert len(deploy["triggers_replace"]) == 2
    create, destroy = deploy["provisioner"]
    assert "doctl serverless deploy do_project" in create["local-exec"]["command"]
    assert destroy["local-exec"]["when"] == "destroy"
    assert "${self.input.package}" in destroy["local-exec"]["command"]

    root = project.work_dir / "do_project"
    spec = yaml.safe_load((root / "project.yml").read_text())
    pkg = spec["packages"][0]
    assert pkg["name"] == "demo-dev"
    fns = {f["name"]: f for f in pkg["functions"]}
    assert fns["hello"]["web"] == "raw" and fns["hello"]["runtime"] == "python:3.11"
    assert fns["hello"]["limits"] == {"timeout": 30000, "memory": 256}
    assert fns["tick"]["web"] is False
    crons = [t["sourceDetails"]["cron"] for t in fns["tick"]["triggers"]]
    assert crons == ["*/5 * * * *", "0 12 * * 1"]
    assert fns["tick"]["triggers"][1]["sourceDetails"]["withBody"]["data"] == {"r": 1}
    assert (root / "packages/demo-dev/hello/__main__.py").is_file()
    assert (root / "packages/demo-dev/hello/pskit_manifest.json").is_file()

    out = tf["output"]["pskit"]["value"]
    assert out["functions"]["hello"]["url"] == (
        "https://faas-nyc1-abc.doserverless.co/api/v1/web/fn-1234/demo-dev/hello"
    )
    assert out["functions"]["tick"]["url"] is None


def test_memory_range(make_project):
    project = make_project(CONFIG.replace("runtime: python3.11", "runtime: python3.11\n  memory: 2048"))
    assert any("128-1024 MB" in e for e in _errors(project))
