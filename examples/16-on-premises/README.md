# 16 · On-premises

Same handlers as a cloud deploy, running as one Python process on this machine.
`pskit deploy` starts that process. HTTP is served directly. Schedules, queues,
storage and topics run inside the process when you do not already have those
services.

## What gets created

| Service | This example | Where it lives |
| --- | --- | --- |
| schedule | `builtin` | in the host process |
| queue | `builtin` | `.pskit/onprem-data/on-prem-demo-dev/queues` |
| topic | `builtin` | `.pskit/onprem-data/on-prem-demo-dev/topics` |
| storage | `directory` | `.onprem/buckets` (a folder you can point at an existing tree) |
| workflow | `embedded` | the host calls the task functions in-process |

`pskit remove` stops the process and leaves those directories in place.

To use a directory you already have:

```yaml
provider:
  options:
    services:
      queue: {use: directory, path: /var/pskit/queues}
```

`existing: true` on one queue, bucket or topic means "do not create it; wait until
that directory appears".

## Run

```bash
pskit dev                                      # HTTP only, no durable queues
pskit deploy                                   # start the host on http://127.0.0.1:8080
curl http://127.0.0.1:8080/hello?name=Ada
curl http://127.0.0.1:8080/__pskit/health
```

Publish into the services the host is running:

```bash
curl -X POST http://127.0.0.1:8080/__pskit/queues/jobs -d '{"kind":"email"}'
curl -X POST http://127.0.0.1:8080/__pskit/topics/orders \
  -d '{"message":{"id":1},"attributes":{"event_type":"order.shipped"}}'
curl -X PUT http://127.0.0.1:8080/__pskit/storage/uploads/in/a.csv --data-binary @rows.csv
curl -X POST http://127.0.0.1:8080/__pskit/workflows/ping -d '{}'
```

From a handler in the same process, `submit_queue`, `submit_topic`, `put_object`
and `delete_object` in `py_serverless_kit.runtime.onprem_host` write to the same
directories. They are available when `PSKIT_ONPREM_ROOT` is set. Example 04 uses
that for its HTTP producer.

Set `options.admin_token` and send `x-pskit-token` on `/__pskit/*` except
`/__pskit/health`. Each example uses its own port so several hosts can run at once.

`pskit dev` is still the hot-reloading HTTP server. This example is the durable
deploy: it keeps running after `pskit deploy` returns.

To copy the same host onto another machine (SSH, Docker, or a bundled CPython
when that machine has no Python), see [17-on-premises-remote](../17-on-premises-remote).
