## HTTP

**CORS errors in the browser**
: Add `cors: true` (or a `cors:` mapping) to the route. With `allow_credentials: true` the runtime echoes the request's `Origin` instead of `*`, so list explicit `origins` to restrict who may call. Preflights are answered by the runtime (and by API Gateway on AWS).

**405 Method Not Allowed**
: The path matched a route but not the method. The `allow` header lists the valid methods. Use `method: ANY` to accept everything.

**404 locally but works in the cloud (or the other way round)**
: `pskit dev` matches routes exactly. Check the printed route list. Path templates use `{id}` and `{path+}` (last segment only).

**500 with only a request id**
: Look in the provider's logs for that `request_id`. Locally, or temporarily, set `PSKIT_DEBUG=1` to include the exception text.

**Cold starts**
: Keep bundles small (exclude data files, avoid heavy imports at module level), increase memory (more CPU on most clouds), or use provider options such as provisioned concurrency through `functions.<fn>.options`.
