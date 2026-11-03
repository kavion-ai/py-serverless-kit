# 01 · Hello HTTP

The minimum: one handler, one HTTP route, deployable to any cloud.

## Files

| File | Purpose |
| --- | --- |
| `app/handlers.py` | the handler - plain Python, no cloud SDK |
| `pskit.yml` | service name, target cloud, function + trigger |

## The YAML

```yaml
functions:
  hello:
    handler: app.handlers.hello   # module path + function name
    events:
      - http: GET /hello          # method + path
```

`providers:` holds per-cloud overrides (region, project id, ...). They only apply when
that cloud is selected, so one file serves every target.

## Run locally

```bash
pskit dev                                   # http://127.0.0.1:3000/hello?name=Ada
pskit invoke -f hello --path "/hello?name=Ada"
```

Expected output:

```json
{
  "status": 200,
  "headers": {"content-type": "application/json"},
  "body": {"message": "Hello, Ada!", "provider": "local", "stage": "dev"}
}
```

## Deploy

```bash
pskit deploy                      # AWS Lambda + API Gateway HTTP API
pskit deploy --provider gcp       # Cloud Functions gen2 (needs GOOGLE_CLOUD_PROJECT)
pskit deploy --provider azure     # Azure Functions (needs ARM_SUBSCRIPTION_ID)
pskit info                        # URLs and resource ids
pskit dashboard --open            # HTML overview of every deployment
pskit remove                      # tear it down again
```

`pskit deploy` prints the URL, e.g. `GET https://abc123.execute-api.us-east-1.amazonaws.com/hello`.
