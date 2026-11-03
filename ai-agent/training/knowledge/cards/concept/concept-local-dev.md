# Local development

All of this works without cloud credentials or Terraform. Locally, handlers run through the **same dispatcher** as in the cloud (routing, CORS, error mapping, `BatchResult`). Only the cloud-specific adapter is skipped.

## `pskit dev`: local server

On startup it prints every route:

| Endpoint | What it does |
|---|---|
| your `http` routes | `{id}` and `{path+}` templates; static routes win over parameterised ones; unknown paths return 404 with the route list |
| `POST /__pskit/invoke/<function>?type=...` | invoke any function; the JSON body becomes `event.data` (or the records, for `queue`/`topic`/`storage`). Response `{"result": ...}`, or 500 `{"errorType", "cause"}` |
| `POST /__pskit/workflows/<workflow>` | run a workflow on the embedded engine; the body is the input. Response `{"status": "SUCCEEDED", "output", "history"}` or 500 `FAILED` |
| `GET /__pskit/` | the dashboard for this project (local view) |

**Hot reload:** before each request the server checks the `.py` files under `package.source`. If any changed, your modules are re-imported, so there's no restart needed.

## `pskit invoke` and `pskit workflow run`

Details are in the CLI reference.

## Environment

Local runs set `PSKIT_PROVIDER=local`, `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_REGION=local`, `PSKIT_FUNCTION` and `PSKIT_HANDLER`. They also add `provider.environment` and the function's `environment`, and finally load `.env` (or `--env-file`):

`invoke()` calls between functions run in-process locally. Logs use the readable `text` format (`PSKIT_LOG_FORMAT=json` switches back).

## Testing with pytest

| Helper | Purpose |
|---|---|
| `Project.load(config_path=None, provider=..., stage=..., cwd=...)` | load and validate a project |
| `LocalRunner(project, env_file=".env")` | in-process runner |
| `runner.invoke(function, event)` | run a handler; HTTP returns a `Response` |
| `runner.run_workflow(name, data, sleep=False)` | returns `{"output", "history"}`; raises `WorkflowFailed` |

## On-premises is a deploy, not `pskit dev`

`pskit dev` reloads HTTP handlers and drops the process when you stop it. `provider.name: onprem` is the durable run: `pskit deploy` starts a process that keeps schedules, file queues, directory storage, topics and embedded workflows after the command returns. `options.deploy.method` is `local` (this machine), `ssh`, or `docker`. See providers.md, `examples/16-on-premises` and `examples/17-on-premises-remote`.
| `http_event(method, path, body=None, headers=None, query=None)` | dict/list bodies are JSON-encoded; `?query` in `path` is parsed |
| `build_event(type, data, **http)` | `queue`/`topic` (list → records), `storage` (`{"bucket", "key", "size", "action"}`), `schedule`, `invoke`, `workflow`, `http` |

To unit-test a workflow with stubbed tasks, use `py_serverless_kit.runtime.workflow.WorkflowEngine(definition, task_runner)` directly. See `examples/14-testing` (includes a CI workflow that also runs `pskit validate` against several providers).

```bash
pskit dev                    # http://127.0.0.1:3000
pskit dev --port 8080 --host 0.0.0.0 --env-file .env.local
```
