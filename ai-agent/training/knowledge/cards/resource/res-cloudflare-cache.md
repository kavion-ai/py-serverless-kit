# Workers KV (`type: cache`)

Workers KV is Cloudflare's global key-value store: fast reads, eventually consistent writes (changes can take up to a
minute to show everywhere). Use it for caches, feature flags and configuration. pskit never creates it: declare it
with `external: true` and bind it.

Redis clients don't work in Python Workers (no TCP sockets, no third-party packages). For Redis use an HTTP-based Redis
service and call it with `from js import fetch`, or deploy that function elsewhere.

## 1. Create the namespace (dashboard)

1. Dashboard → **Storage & databases → Workers KV** (or **Workers & Pages → KV**) → **Create instance** /
   **Create namespace**.
2. Name (for example `shop-cache`) → **Create**.

## 2. Collect the values

| Value | Where | Example |
|---|---|---|
| Namespace ID | **KV** → the list → *ID* column (or the namespace's overview) | `0123456789abcdef0123456789abcdef` |

## 3. Declare it in `pskit.yml`

The deploy API token needs **Workers KV Storage Edit**.

## 4. Use it in a handler

`expirationTtl` must be at least 60 seconds.

## 5. Test

Dashboard: **KV** → namespace → **KV Pairs** shows the stored key.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Value not visible right after a write in another region | KV is eventually consistent; use D1 or Durable Objects for read-after-write needs |
| `AttributeError: CACHE` | add the `kv_namespace` binding to that function's `options.bindings` |

```text
resources:
  cache:
    type: cache
    external: true
    name: shop-cache
    connection:
      binding: CACHE
      ttl_seconds: 300

functions:
  api:
    handler: app.handlers.api
    events: [{http: "GET /prices/{sku}"}]
    options:
      bindings:
        - {type: kv_namespace, name: CACHE, namespace_id: 0123456789abcdef0123456789abcdef}
```
