# 14 · Testing handlers and workflows

Handlers are plain Python functions, and the kit ships helpers that run them through the
**same dispatcher** the clouds use. Tests therefore cover routing, error mapping (400/404/500),
CORS and batch results without deploying anything.

| Tool | Use for |
| --- | --- |
| `LocalRunner(project).invoke(name, event)` | full dispatcher: env vars from `pskit.yml`, routing, error → status mapping |
| `http_event(method, path, body, headers, query)` | synthetic HTTP request (query string in `path` works) |
| `build_event("queue" / "topic" / "storage" / "schedule" / "invoke", data)` | synthetic event; a list of items becomes several records |
| `Event(...)` / `Record(...)` | full control, e.g. message attributes |
| `runner.run_workflow(name, input)` | whole workflow with the real task handlers (`output` + `history`) |
| `WorkflowEngine(definition, task_runner)` | state-machine logic with stubbed tasks |

```python
def test_price(runner):
    resp = runner.invoke("price", http_event("POST", "/price", {"amount": 100, "code": "VIP25"}))
    assert resp.status == 200
```

HTTP functions return a `Response` (`resp.status`, `resp.render()` → `(status, headers, bytes)`).
Other functions return whatever the handler returned.

## Run

```bash
python -m pytest -q          # from this directory
```

```
...........                                                  [100%]
13 passed
```

## CI

`ci.github-workflow.yml` is a ready-made GitHub Actions workflow with two jobs:

1. **test:** unit tests on several Python versions;
2. **validate:** `pskit validate` + `pskit package` for AWS, GCP and Azure on every pull
   request. A change that would break deployment to any target cloud fails the build,
   and the generated Terraform is uploaded for review.

Copy it to `.github/workflows/ci.yml`. Deployment itself is covered in example 15.
