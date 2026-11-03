import json

from py_serverless_kit.providers.oracle import oci_path
from tests.conftest import full_config

OPTIONS = "{compartment_id: ocid1.compartment.oc1..c, subnet_ids: [ocid1.subnet.oc1..s], %s}"
CONFIG = """
service: demo
provider:
  name: oracle
  runtime: python3.11
  options: %s
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: "GET /hello/{name}"
      - http: {path: "/files/{path+}", method: POST, cors: true}
  worker:
    handler: app.handlers.worker
    events:
      - storage: {bucket: uploads, events: [created, deleted]}
"""


def _errors(project):
    return [str(i) for i in project.validate() if i.level == "error"]


def test_required_options_and_unsupported_events(make_project):
    joined = "\n".join(_errors(make_project(full_config("oracle"))))
    assert "options.compartment_id is required" in joined
    assert "options.subnet_ids" in joined
    assert "docker build -t <image>" in joined
    for kind in ("schedule", "queue", "topic"):
        assert f"`{kind}` events" in joined
    assert "`storage` events" not in joined


def test_render_with_image_build(make_project, render):
    project = make_project(CONFIG % (OPTIONS % "image_repository: iad.ocir.io/ns/demo"))
    assert _errors(project) == []
    tf = render(project)
    res = tf["resource"]
    assert tf["terraform"]["required_providers"]["oci"]["source"] == "oracle/oci"
    image_build = res["terraform_data"]["image"]
    image = image_build["triggers_replace"][0]
    assert image.startswith("iad.ocir.io/ns/demo:")
    assert "docker push" in image_build["provisioner"][0]["local-exec"]["command"]
    fn = res["oci_functions_function"]["hello"]
    assert fn["image"] == image and fn["memory_in_mbs"] == "256"
    assert fn["depends_on"] == ["terraform_data.image"]
    assert fn["config"]["PSKIT_HANDLER"] == "app.handlers.hello"
    assert res["oci_functions_application"]["app"]["shape"] == "GENERIC_X86"

    routes = res["oci_apigateway_deployment"]["http"]["specification"]["routes"]
    expected = {"/hello/{name}": ["GET"], "/files/{path*}": ["POST", "OPTIONS"]}
    assert {r["path"]: r["methods"] for r in routes} == expected
    assert routes[0]["backend"]["type"] == "ORACLE_FUNCTIONS_BACKEND"

    bucket = res["oci_objectstorage_bucket"]["b-uploads".replace("-", "_")]
    assert bucket["object_events_enabled"] is True
    rule = res["oci_events_rule"]["worker-uploads".replace("-", "_")]
    cond = json.loads(rule["condition"])
    assert cond["data"]["additionalDetails"]["bucketName"] == "uploads"
    assert "com.oraclecloud.objectstorage.deleteobject" in cond["eventType"]
    assert rule["actions"]["actions"][0]["action_type"] == "FAAS"

    build = project.work_dir / "build"
    assert "fnproject/python:3.11" in (build / "Dockerfile").read_text()
    assert "fdk" in (build / "requirements.txt").read_text()
    assert (build / "func.py").is_file() and (build / "func.yaml").is_file()

    out = tf["output"]["pskit"]["value"]
    assert out["endpoint"] == "${oci_apigateway_deployment.http.endpoint}"
    assert "base_url" not in out["functions"]["worker"]


def test_prebuilt_image(make_project, render):
    tf = render(make_project(CONFIG % (OPTIONS % "image: iad.ocir.io/ns/demo:v1")))
    assert "terraform_data" not in tf["resource"]
    assert tf["resource"]["oci_functions_function"]["worker"]["image"] == "iad.ocir.io/ns/demo:v1"


def test_oci_path():
    assert oci_path("/files/{path+}") == "/files/{path*}"
    assert oci_path("/users/{id}") == "/users/{id}"
