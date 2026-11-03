# Example: 02-rest-api

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: Allowed browser origins for CORS - defined once, reused below. Gateway-level JWT validation is an AWS feature. On other clouds the route is public and the handler checks the Authorization header itself. Overrides replace lists instead of merging them, so the whole `events` list is restated.

# 02 · REST API

A CRUD API for books that uses every HTTP feature of the portable runtime.

| Feature | How |
| --- | --- |
| Path params `{id}` | `event.http.path_params["id"]` |
| Query string | `event.http.query.get("author")` |
| JSON body, automatic 400 on malformed JSON | `event.http.json()` |
| Validation errors with details | `raise BadRequest("...", details={...})` |
| 404 / 409 | `raise NotFound(...)`, `raise Conflict(...)` |
| Status code + headers | `Response.json(obj, status=201, headers={...})` |
| 204 | `Response.no_content()` |
| Binary responses | `Response.binary(png_bytes, "image/png")` |
| Redirects | `Response.redirect(url)` |
| Cookies | `resp.set_cookie(...)`, `event.http.cookies` |
| CORS (incl. preflight) | `cors:` on the http event |
| JWT auth | `auth: jwt` + `authorizer:` (AWS API Gateway) |

Unhandled exceptions become `500 {"error": "Internal Server Error", "request_id": ...}`.
The real message stays in the logs unless you set `PSKIT_DEBUG=1`.

> **Storage:** `app/store.py` keeps data in memory so the example is self-contained.
> Serverless instances don't share memory and are recycled at any time, so use a real
> database (DynamoDB, Firestore, Cosmos DB, PostgreSQL, ...) in production.

## The YAML

- `custom.cors` is defined once and reused with `${self:custom.cors}`.
- `admin-stats` uses `auth: jwt`. **Portability note:** gateway-level JWT validation is
  AWS-only. The `providers.gcp` / `providers.azure` blocks swap that route for a public one,
  and the handler then requires the `Authorization` header. Running `pskit validate --provider <cloud>`
  reports any setting a cloud does not support, before you deploy.

## Run locally

Or without a server:

Expected output of the second command:

## Deploy

On GCP every function gets its own URL, because there is no shared gateway. The runtime
still matches `/books/{id}` against the request path, so `event.http.path_params` works
the same way.
