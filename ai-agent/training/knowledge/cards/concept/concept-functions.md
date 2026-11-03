# Concept: functions in pskit.yml

Each entry under `functions` needs a `handler`. The schema requires `package.module.function` or `module:function`. The doc also writes it as `package.module.function` or `package.module:function`, relative to `package.source`.

Optional fields and their defaults: `description` is an empty string. `enabled` defaults to true. False keeps the function in the file and skips it on deploy. Workflows take `enabled` too. `runtime`, `memory`, `timeout`, and `architecture` inherit from `provider` when omitted. Function `memory` is 64–32768 and `timeout` is 1–3600 when set. `environment` and `tags` default to empty maps and are merged over the provider-level maps. `events` defaults to an empty list, which means an invoke-only function. `concurrency` is an int of at least 0 when set. The doc describes it as reserved concurrency or max instances where the provider supports it. `iam` is added to the provider-level statements. `options` defaults to an empty mapping and is merged into the provider's function resource.

Two functions cannot declare the same `METHOD /path`. The schema labels a function for the dashboard from its event types: no events is invoke-only, only http is http, only schedule is scheduled, http plus anything else is http+event, and any other mix is event-driven.

Sources: `docs/configuration.md#functions`, `src/py_serverless_kit/config/schema.py`

```text
functions:
  create-order:
    handler: app.orders.create      # package.module.function  (or package.module:function)
    description: Creates an order
    runtime: python3.12             # override provider.runtime
    memory: 512                     # MB, 64-32768
    timeout: 20                     # s, 1-3600
    architecture: arm64
    concurrency: 10                 # reserved concurrency / max instances where supported
    environment: {TABLE: orders}
    tags: {team: checkout}
    iam:
      statements:
        - {actions: ["dynamodb:PutItem"], resources: ["${tf:aws_dynamodb_table.orders.arn}"]}
    events:
      - http: POST /orders
    options: {}                     # merged into the provider's function resource (escape hatch)
```
