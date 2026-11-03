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

```bash
pskit dev
curl "localhost:3000/books?author=gibson"
curl -i -X POST localhost:3000/books -d '{"title":"Snow Crash","author":"Neal Stephenson","year":1992,"isbn":"9780553380958"}'
curl -i -X POST localhost:3000/books -d '{"title":1}'          # 400 with field details
curl -s localhost:3000/books/b1/cover -o cover.png
curl -i -X POST localhost:3000/session -d '{"user":"ada"}'    # Set-Cookie header
```

Or without a server:

```bash
pskit invoke -f get-book --path /books/b1
pskit invoke -f create-book -d '{"title": 1}'
```

Expected output of the second command:

```json
{
  "status": 400,
  "headers": {"content-type": "application/json"},
  "body": {
    "error": "validation failed",
    "status": 400,
    "details": {"title": "must be str", "author": "required", "year": "required", "isbn": "required"}
  }
}
```

## Deploy

```bash
pskit deploy                     # AWS: one HTTP API with 9 routes and a JWT authorizer
pskit deploy --provider gcp      # 9 Cloud Functions, each with its own URL
pskit deploy --provider azure    # one Function App serving all 9 routes
```

On GCP every function gets its own URL, because there is no shared gateway. The runtime
still matches `/books/{id}` against the request path, so `event.http.path_params` works
the same way.
