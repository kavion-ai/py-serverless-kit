import json
import time
import urllib.error
import urllib.request

import pytest

from py_serverless_kit.local.runner import LocalRunner, build_event, http_event, load_dotenv
from py_serverless_kit.local.server import start_background

CONFIG = """
service: dev
provider:
  name: aws
  environment: {GREETING: hi}
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello/{name}
      - http: GET /hello
  create:
    handler: app.handlers.create
    events: [{http: {path: /items, method: POST, cors: true}}]
  step:
    handler: app.handlers.step
workflows:
  twice:
    start_at: A
    states:
      A: {type: task, function: step, next: B}
      B: {type: task, function: step, end: true}
"""


def request(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"content-type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


@pytest.fixture
def server(make_project):
    project = make_project(CONFIG)
    runner = LocalRunner(project)
    httpd, base = start_background(runner)
    yield base, project
    httpd.shutdown()
    httpd.server_close()


def test_routes(server):
    base, _ = server
    status, _, body = request(f"{base}/hello/Grace")
    assert status == 200 and json.loads(body)["message"] == "hello Grace"
    status, _, body = request(f"{base}/hello?name=Q")
    assert json.loads(body)["message"] == "hello Q"
    status, headers, body = request(f"{base}/items", "POST", {"id": 1}, {"Origin": "https://x"})
    assert status == 201 and headers.get("access-control-allow-origin") == "*"
    status, _, _ = request(f"{base}/items", "POST", {"no": "id"})
    assert status == 404
    status, _, body = request(f"{base}/nope")
    assert status == 404 and "routes" in json.loads(body)


def test_internal_endpoints(server):
    base, _ = server
    status, _, body = request(f"{base}/__pskit/invoke/step", "POST", {"steps": 1})
    assert status == 200 and json.loads(body)["result"] == {"steps": 2}
    status, _, body = request(f"{base}/__pskit/workflows/twice", "POST", {})
    assert status == 200 and json.loads(body)["output"] == {"steps": 2}
    status, _, body = request(f"{base}/__pskit/")
    assert status == 200 and b"<html" in body
    status, _, _ = request(f"{base}/__pskit/invoke/missing", "POST", {})
    assert status == 404


def test_hot_reload(server):
    base, project = server
    handlers = project.root / "app" / "handlers.py"
    src = handlers.read_text().replace('f"hello {name}"', 'f"howdy {name}"')
    time.sleep(0.05)
    handlers.write_text(src)
    import os

    st = os.stat(handlers)
    os.utime(handlers, (st.st_atime, st.st_mtime + 5))
    _, _, body = request(f"{base}/hello/Bo")
    assert json.loads(body)["message"] == "howdy Bo"


def test_runner_env_and_events(make_project, tmp_path):
    project = make_project(CONFIG, files={".env": "export SECRET='abc'\n# c\nPLAIN=1\n"})
    assert load_dotenv(project.root / ".env") == {"SECRET": "abc", "PLAIN": "1"}
    runner = LocalRunner(project)
    resp = runner.invoke("hello", http_event("GET", "/hello/x"))
    assert resp.status == 200
    import os

    assert "PSKIT_FUNCTION" not in os.environ  # restored after the call
    ev = build_event("storage", {"bucket": "b", "key": "k"})
    assert ev.records[0].bucket == "b"
    with pytest.raises(ValueError):
        build_event("nonsense")
