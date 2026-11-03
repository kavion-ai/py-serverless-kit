# Local development

All of this works without cloud credentials or Terraform. Locally, handlers run through the **same dispatcher** as in the cloud (routing, CORS, error mapping, `BatchResult`). Only the cloud-specific adapter is skipped.

## `pskit dev`: local server

```bash
pskit dev                    # http://127.0.0.1:3000
pskit dev --port 8080 --host 0.0.0.0 --env-file .env.local
```

On startup it prints every route:

```
pskit dev server for 'orders' on http://127.0.0.1:3000
  GET     http://127.0.0.1:3000/hello  -> hello
  GET     http://127.0.0.1:3000/items/{id}  -> get-item
  POST    http://127.0.0.1:3000/__pskit/invoke/<function>?type=invoke|queue|topic|storage|schedule
  POST    http://127.0.0.1:3000/__pskit/workflows/<workflow>
  GET     http://127.0.0.1:3000/__pskit/  (dashboard)
```

| Endpoint | What it does |
|---|---|
| your `http` routes | `{id}` and `{path+}` templates; static routes win over parameterised ones; unknown paths return 404 with the route list |
| `POST /__pskit/invoke/<function>?type=...` | invoke any function; the JSON body becomes `event.data` (or the records, for `queue`/`topic`/`storage`). Response `{"result": ...}`, or 500 `{"errorType", "cause"}` |
| `POST /__pskit/workflows/<workflow>` | run a workflow on the embedded engine; the body is the input. Response `{"status": "SUCCEEDED", "output", "history"}` or 500 `FAILED` |
| `GET /__pskit/` | the dashboard for this project (local view) |

**Hot reload:** before each request the server checks the `.py` files under `package.source`. If any changed, your modules are re-imported, so there's no restart needed.

```bash
curl -X POST localhost:3000/__pskit/invoke/process-jobs?type=queue -d '[{"job": 1}, {"job": 2}]'
curl -X POST localhost:3000/__pskit/workflows/order-pipeline -d '{"amount": 50}'
```

## `pskit invoke` and `pskit workflow run`

```bash
pskit invoke -f hello --path "/hello?name=Ada" -H "Authorization: Bearer x"
pskit invoke -f nightly-report             # schedule event with the configured input
pskit workflow run order-pipeline -i @events/big-order.json --history
```

Details are in the [CLI reference](cli.md#pskit-invoke).

## Environment

Local runs set `PSKIT_PROVIDER=local`, `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_REGION=local`, `PSKIT_FUNCTION` and `PSKIT_HANDLER`. They also add `provider.environment` and the function's `environment`, and finally load `.env` (or `--env-file`):

```bash
# .env  (git-ignored; also excluded from deployment bundles)
DATABASE_URL=postgres://localhost/orders
export API_KEY='dev-key'
```

`invoke()` calls between functions run in-process locally. Logs use the readable `text` format (`PSKIT_LOG_FORMAT=json` switches back).

## Testing with pytest

```python
# tests/test_handlers.py
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, build_event, http_event

runner = LocalRunner(Project.load())          # loads ./pskit.yml


def test_get_item():
    resp = runner.invoke("get-item", http_event("GET", "/items/1"))
    assert resp.status == 200


def test_create_item_validation():
    resp = runner.invoke("create-item", http_event("POST", "/items", body={"name": "lamp"}))
    assert resp.status == 201


def test_queue_partial_failure():
    result = runner.invoke("process-jobs", build_event("queue", [{"ok": 1}, "not-json"]))
    assert result.failed == ["local-1"]


def test_workflow():
    out = runner.run_workflow("order-pipeline", {"amount": 5})
    assert out["output"]["charged"] is True
```

| Helper | Purpose |
|---|---|
| `Project.load(config_path=None, provider=..., stage=..., cwd=...)` | load and validate a project |
| `LocalRunner(project, env_file=".env")` | in-process runner |
| `runner.invoke(function, event)` | run a handler; HTTP returns a `Response` |
| `runner.run_workflow(name, data, sleep=False)` | returns `{"output", "history"}`; raises `WorkflowFailed` |

## On-premises is a deploy, not `pskit dev`

`pskit dev` reloads HTTP handlers and drops the process when you stop it. `provider.name: onprem` is the durable run: `pskit deploy` starts a process that keeps schedules, file queues, directory storage, topics and embedded workflows after the command returns. `options.deploy.method` is `local` (this machine), `ssh`, or `docker`. See [providers.md](providers.md#onprem-on-premises), [`examples/16-on-premises`](../examples/16-on-premises) and [`examples/17-on-premises-remote`](../examples/17-on-premises-remote).
| `http_event(method, path, body=None, headers=None, query=None)` | dict/list bodies are JSON-encoded; `?query` in `path` is parsed |
| `build_event(type, data, **http)` | `queue`/`topic` (list → records), `storage` (`{"bucket", "key", "size", "action"}`), `schedule`, `invoke`, `workflow`, `http` |

To unit-test a workflow with stubbed tasks, use `py_serverless_kit.runtime.workflow.WorkflowEngine(definition, task_runner)` directly. See [`examples/14-testing`](../examples/14-testing) (includes a CI workflow that also runs `pskit validate` against several providers).
