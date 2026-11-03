# Other Cloudflare services and APIs (`type: custom`)

`custom` covers anything else a Worker talks to: a secret, Workers AI, Vectorize, another Worker, or any HTTP API.
pskit only passes `connection` values to handlers (`external: true` is required). Either bind the service through
`functions.<fn>.options.bindings` or call its HTTP API.

Python Workers can't install packages, so use bindings or `from js import fetch` rather than SDKs.

## Binding types

Every binding type that `cloudflare_workers_script` (provider 5.x) accepts can go into `options.bindings`. Common ones:

| Service | Create / find it in the dashboard | Binding |
|---|---|---|
| Secret | value you already have | `{type: secret_text, name: API_KEY, text: "${env:API_KEY}"}` |
| Plain setting | | `{type: plain_text, name: MODE, text: live}` |
| Workers AI | **AI → Workers AI** (no setup) | `{type: ai, name: AI}` |
| Vectorize index | **AI → Vectorize → Create index** → name | `{type: vectorize, name: INDEX, index_name: products}` |
| Another Worker | **Workers & Pages** → the Worker's name | `{type: service, name: BILLING, service: billing-worker}` |

Check the exact argument names of any other type in the
[`cloudflare_workers_script` docs](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_script)
before using it, and run `pskit plan` to have Terraform validate them.

## Example: an external HTTP API with a secret

```yaml
resources:
  payments:
    type: custom
    external: true
    connection:
      base_url: https://api.payments.example.com/v1
      secret_binding: PAYMENTS_KEY

functions:
  checkout:
    handler: app.handlers.checkout
    events: [{http: POST /checkout}]
    options:
      bindings:
        - {type: secret_text, name: PAYMENTS_KEY, text: "${env:PAYMENTS_KEY}"}
```

```python
import json

from js import Object, fetch
from pyodide.ffi import to_js
from py_serverless_kit import resource


async def checkout(event, ctx):
    api = resource("payments")
    key = getattr(ctx.raw, api["secret_binding"])
    init = {"method": "POST", "body": json.dumps(event.http.json()),
            "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}}
    resp = await fetch(api["base_url"] + "/charges", to_js(init, dict_converter=Object.fromEntries))
    return json.loads(await resp.text())
```

## Example: Workers AI

```yaml
resources:
  ai:
    type: custom
    external: true
    connection: {binding: AI, model: "@cf/meta/llama-3.1-8b-instruct"}

functions:
  ask:
    handler: app.handlers.ask
    events: [{http: POST /ask}]
    options:
      bindings: [{type: ai, name: AI}]
```

```python
from js import Object
from pyodide.ffi import to_js
from py_serverless_kit import resource


async def ask(event, ctx):
    ai = resource("ai")
    payload = to_js({"prompt": event.http.json()["question"]}, dict_converter=Object.fromEntries)
    answer = await getattr(ctx.raw, ai["binding"]).run(ai["model"], payload)
    return answer.to_py()
```

## Test

```bash
pskit validate
pskit plan        # Terraform checks the binding arguments
pskit deploy
```
