# Example: 01-hello-http

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: Minimal service: one function, one HTTP route. Per-cloud overrides. A block is applied only when that provider is selected (e.g. `pskit deploy --provider gcp`); the handler code never changes.

# 01 · Hello HTTP

The minimum: one handler, one HTTP route, deployable to any cloud.

## Files

| File | Purpose |
| --- | --- |
| `app/handlers.py` | the handler - plain Python, no cloud SDK |
| `pskit.yml` | service name, target cloud, function + trigger |

## The YAML

`providers:` holds per-cloud overrides (region, project id, ...). They only apply when
that cloud is selected, so one file serves every target.

## Run locally

Expected output:

## Deploy

`pskit deploy` prints the URL, e.g. `GET https://abc123.execute-api.us-east-1.amazonaws.com/hello`.

The handler stays the same when provider.name changes. Provider-specific values belong in providers: or in provider.options. pskit validate checks the example against the selected provider. pskit invoke runs a function from the example on this machine.

```
pskit validate
```
