# Concept: resources

`resources` maps a name to a service the functions use. pskit creates a managed resource. `external: true` means it already exists, or runs outside pskit, and pskit does not create or destroy it. Every bound function gets `PSKIT_RESOURCE_<KEY>_*` variables. Handlers read them with `resource("key")`.

`RESOURCE_TYPES` in `config/schema.py` is storage, queue, topic, database, cache, custom, and smtp. The type list in `docs/configuration.md#resources` omits smtp. The code wins, and the same gap is recorded for `docs/resources.md`. database, cache, and custom must be `external: true`. The schema rejects a non-event resource type that is not external, with the message that pskit does not create that type.

`name` defaults to the key, or the tail of `connection.arn`. `connection` is a map of scalar values exposed to handlers. Keys start with a letter and use letters, digits, or `_`. Nested maps and lists are rejected. `functions` defaults to every user function. `options` is provider-specific.

queue, storage, and topic events can name a resource: `- queue: {resource: jobs}`. The event then uses the resource's native name and `existing` follows `external`.

Sources: `docs/configuration.md#resources`, `src/py_serverless_kit/config/schema.py`, `ai-agent/training/knowledge/conflicts.md`

```text
resources:
  jobs: {type: queue}                       # managed
  uploads:
    type: storage
    external: true
    name: legacy-uploads-bucket             # existing bucket
  orders-db:
    type: database                          # database / cache / custom: always external
    external: true
    connection: {host: db.internal, port: 5432, password_env: ORDERS_DB_PASSWORD}
    functions: [api]                        # default: every user function
```
