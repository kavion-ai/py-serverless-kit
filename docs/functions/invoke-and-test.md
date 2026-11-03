# Invoke and test functions

Search terms: test function, run locally, pskit invoke, pskit dev, local server, hot reload, pskit trigger, send test event, invoke(), call another function, LocalRunner, pytest, response, errors, status code, BatchResult

How a pskit function returns results and errors, how one function calls another with `invoke()`, and every way to run
a function: in studio's **Test** page, with `pskit invoke` and `pskit dev` on your machine, with `pskit trigger`
against a deployment, and from pytest.

## Return a result from a handler

What a pskit handler returns depends on how it was called. For an `http` event the value becomes an HTTP response:

| Return value | Response |
|---|---|
| `Response(...)` | as is |
| `None` | `204 No Content` |
| `dict`, `list`, numbers, dataclasses, pydantic models | JSON, status 200 |
| `str` | `text/plain`, 200 |
| `bytes` | `application/octet-stream`, 200 |
| `(body, status)` or `(body, status, headers)` | that body with that status |

```python
from py_serverless_kit import Response


def download(event, ctx):
    return Response.binary(b"%PDF...", "application/pdf")   # base64 for gateways automatically


def login(event, ctx):
    return Response.json({"ok": True}).set_cookie("sid", "abc", max_age=3600, http_only=True, secure=True)


def created(event, ctx):
    return {"id": 7}, 201, {"location": "/items/7"}
```

For every other event (schedule, queue, storage, topic, smtp, invoke, workflow) the value goes back as it is: to the
caller of `invoke()`, to the next workflow state, or to the platform. Queue, topic and storage handlers may return a
`BatchResult` ([../triggers/queue.md](../triggers/queue.md#retry-only-the-failed-messages-with-batchresult)).

## Raise errors from a handler

A pskit HTTP handler raises an `HttpError` subclass to answer with a JSON error:

```python
from py_serverless_kit import HttpError, NotFound, UnprocessableEntity


def get_order(event, ctx):
    raise NotFound("no such order")                     # 404 {"error": "no such order", "status": 404}


def update_order(event, ctx):
    raise UnprocessableEntity("invalid order", details={"field": "amount"})   # 422, with "details"


def teapot(event, ctx):
    raise HttpError("short and stout", status=418, headers={"retry-after": "5"})
```

| Situation | Result |
|---|---|
| `HttpError` in an HTTP handler | its status and `{"error", "status", "details"?}` |
| `event.http.json()` on invalid or empty JSON | `400` (pass `default=` to avoid it) |
| path matched, method not allowed | `405` with an `allow` header |
| any other exception in an HTTP handler | `500 {"error": "Internal Server Error", "status": 500, "request_id"}`; the traceback goes to the logs |
| `PSKIT_DEBUG=1` | the 500 body also has `"detail": "<ExceptionClass>: <message>"` (never in production) |
| exception in a non-HTTP handler | re-raised, so the platform retries and dead-letters |
| non-HTTP failure on GCP, IBM, DigitalOcean, Cloudflare, Oracle | `500 {"errorType": "<ExceptionClass>", "cause": "<message>"}` |

Workflow `retry` and `catch` rules match on the exception class name. See
[../deployment/workflows.md](../deployment/workflows.md).

## Call another function with invoke()

`invoke()` calls another pskit function of the same service and returns its result. The handler code is the same on
every cloud; only the transport changes.

```python
from py_serverless_kit import invoke


def checkout(event, ctx):
    order = event.http.json()
    receipt = invoke("billing", {"order_id": order["id"]})            # waits for the result
    invoke("audit", {"order_id": order["id"]}, asynchronous=True)     # fire and forget on AWS
    return receipt
```

Signature: `invoke(function, payload=None, *, asynchronous=False, timeout=30.0)`. `function` may be the pskit name,
the deployed name (`<service>-<stage>-<name>`) or a Lambda ARN. The target receives `event.type == "invoke"` and
`event.data == payload`.

| Where the caller runs | How the call is made |
|---|---|
| `PSKIT_ENDPOINT_<NAME>` is set (any provider) | HTTP POST to that URL (`billing` -> `PSKIT_ENDPOINT_BILLING`) |
| local (`pskit invoke`, `pskit dev`, tests) | in-process |
| onprem | in-process; on another server when placement puts the target there |
| aws | `lambda:InvokeFunction` via boto3: add `boto3` to requirements and allow `lambda:InvokeFunction` in `iam` |
| gcp | authenticated HTTPS call to the target's Cloud Function URL |
| every other cloud | `InvokeError` unless `PSKIT_ENDPOINT_<NAME>` is set: give the target an `http` event and put its URL (`pskit info`) in the caller's `environment` |

Locally and on premises `asynchronous=True` still waits. On Azure, invoke-only functions also get a key-protected
`POST /_pskit/invoke/<name>` route. Node.js: `await invoke("billing", data, { async: true, timeout: 30 })`.
Example project: `examples/09-function-invoke`.

## Test a function in studio

The pskit studio **Test** page runs a function locally or sends a real event to the deployment.

1. In the sidebar click **Test** (or click **Test** on a row of the **Functions** page).
2. Pick the function in the left list (it shows its trigger types, or "invoke only").
3. **1. Choose the event**: click one of its triggers, or **Direct invoke** (no trigger).
4. **2. Edit the event**: for HTTP, edit **Request** (path with query string; `{id}` needs a real value). For
   others edit **Payload (JSON)**. The hint above explains the payload for that trigger type.
   **Saved events**: click **sample** for the default, type a name and click **Save event** to keep a payload
   (stored in `.pskit/studio/test-events.json`), click a saved chip to load it.
5. **3. Run it**:
   - **▶ Run locally** runs the handler on this machine, like `pskit invoke`. Unsaved changes ask **Save and run**
     or **Run without saving**.
   - **☁ Send to <provider> / <stage>** fires the real trigger on the deployment (a queue message, an upload, an
     HTTP call), like `pskit trigger`, after you confirm with **Send**. It is greyed out with the reason when not
     deployed or not available.
   - **Show the function's logs** streams the deployed logs below.
   On premises a **Server** picker chooses which deployed server receives the event.
6. Open **How to test this** for the same steps **In the studio**, in a **Terminal** (pskit and the cloud's CLI) and
   in the cloud console.

## Run a function locally with pskit invoke

`pskit invoke` runs one pskit function on your machine with a synthetic event. No cloud, credentials or Terraform.

```bash
pskit invoke -f hello                                   # the function's first trigger, or invoke
pskit invoke -f hello --path "/hello?name=Ada" -H "Authorization: Bearer x"
pskit invoke -f create-item -t http --method POST --path /items -d '{"name": "lamp"}'
pskit invoke -f process-jobs -t queue -d '[{"job": 1}, {"job": 2}]'   # list -> one record each
pskit invoke -f on-upload -t storage -d '{"bucket": "b", "key": "in/a.csv", "size": 10}'
pskit invoke -f nightly-report                          # schedule: uses the configured input
pskit invoke -f worker -d @event.json                   # payload from a file
```

| Flag | Meaning |
|---|---|
| `-f, --function` | function name (required) |
| `-t, --type` | `http`, `schedule`, `queue`, `storage`, `topic`, `invoke`, `workflow`, `smtp` |
| `-d, --data` | JSON or `@file.json` (plain text when it is not JSON) |
| `--method`, `--path`, `-H/--header` | HTTP request parts (default: the function's first route) |
| `--env-file` | default `.env` |

The output is the result as JSON; an HTTP result shows `{"status", "headers", "body"}` and a `BatchResult` shows
`{"batchItemFailures": [...]}`. A handler exception prints the traceback and exits 1. Local runs set
`PSKIT_PROVIDER=local`. `pskit trigger --list` prints a ready `pskit invoke` command for every trigger.

## Run a local server with pskit dev

`pskit dev` serves every HTTP route of the project and reloads changed code before each request.

```bash
pskit dev                                   # http://127.0.0.1:3000
pskit dev --port 8080 --host 0.0.0.0 --env-file .env.local
curl localhost:3000/items/1
curl -X POST "localhost:3000/__pskit/invoke/process-jobs?type=queue" -d '[{"job": 1}]'
curl -X POST localhost:3000/__pskit/workflows/order-pipeline -d '{"amount": 50}'
```

| Endpoint | Does |
|---|---|
| your routes | `{id}` and `{path+}` templates; unknown paths answer 404 with the route list |
| `POST /__pskit/invoke/<function>?type=...` | runs any function; the body becomes `event.data` (or the records). Answer `{"result": ...}` or 500 `{"errorType", "cause"}` |
| `POST /__pskit/workflows/<workflow>` | runs a workflow on the embedded engine |
| `GET /__pskit/` | a local dashboard |

Python reloads on `.py` changes; Node.js rebuilds on `.js`, `.mjs`, `.cjs`, `.ts`, `.mts`, `.cts`, `.json` changes.
More: [../local-development.md](../local-development.md).

## Send a real event to a deployed function with pskit trigger

`pskit trigger` fires a deployed pskit function through its real trigger: it sends a queue message, uploads an object,
publishes to a topic or calls the URL.

```bash
pskit trigger --list                                  # every function and trigger, with payloads and commands
pskit trigger -f worker -e 0 -d '{"order_id": 1}'     # trigger #0 of worker
pskit trigger -f thumbnails -e 0 -d '{"key": "in/a.png", "content": "x"}'
pskit trigger -f api -e 0 --path '/items/1'
pskit trigger -f nightly --direct                     # invoke without the trigger
pskit logs -f --function worker                       # watch it run
```

Sending works for: HTTP (any cloud with a URL); every trigger on AWS and on premises; queue, topic and storage on
GCP and Azure; schedule and direct invoke over the function URL on GCP, IBM, DigitalOcean, Cloudflare and Oracle.
Elsewhere `--list` prints the cloud CLI command and console steps instead. AWS needs `boto3`; GCP needs
`google-cloud-pubsub` / `google-cloud-storage`; Azure needs `azure-storage-queue`, `azure-storage-blob`,
`azure-servicebus`.

## Test handlers with pytest and LocalRunner

`LocalRunner` runs pskit functions in-process with the same dispatcher as the cloud, so routing, CORS, errors and
`BatchResult` behave as deployed.

```python
from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, build_event, http_event

runner = LocalRunner(Project.load())          # ./pskit.yml


def test_get_item():
    assert runner.invoke("get-item", http_event("GET", "/items/1")).status == 200


def test_queue_partial_failure():
    result = runner.invoke("process-jobs", build_event("queue", [{"ok": 1}, "not-json"]))
    assert result.failed == ["local-1"]


def test_workflow():
    assert runner.run_workflow("order-pipeline", {"amount": 5})["output"]["charged"] is True
```

`http_event(method, path, body=None, headers=None, query=None)` and `build_event(kind, data)` build events;
queue/topic records get ids `local-0`, `local-1`, ... `pskit init` writes `tests/test_handlers.py` with this setup.
Example: `examples/14-testing`.

## See also

- [README.md](README.md)
- [create.md](create.md)
- [../triggers/README.md](../triggers/README.md)
- [../handlers.md](../handlers.md)
- [../local-development.md](../local-development.md)
- [../deployment/logs.md](../deployment/logs.md)
- [../studio-guide/test.md](../studio-guide/test.md)
