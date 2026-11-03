# Concept: HTTP events

The shorthand `- http: GET /users/{id}` sets the method and path. `- http: /health` is GET. The long form uses `path`, `method`, `cors`, `auth`, and `authorizer`. Methods in the schema are GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, and ANY. A star is stored as ANY. The default path is `/` and the default method is GET.

`{name}` matches one segment and lands in `event.http.path_params["name"]`. `{name+}` matches the rest of the path and is only allowed as the last segment. Parameter names are identifiers, so `{user_id}` is valid and `{user-id}` is not. The runtime matches routes itself, so path params and 405 Method Not Allowed work on clouds with no API gateway (GCP, IBM, DigitalOcean, Cloudflare), including when the platform adds or strips a path prefix. Two functions may not declare the same `METHOD /path`.

`cors: true` uses the defaults. A mapping may set `origins` (default `["*"]`), `methods` (default GET POST PUT PATCH DELETE OPTIONS), `headers` (default Content-Type, Authorization, X-Requested-With), `expose_headers`, `allow_credentials` (default false), and `max_age` (default 600). The runtime answers OPTIONS preflights with 204 and adds Access-Control-* headers on every cloud. AWS also configures CORS on the HTTP API.

`auth` is none, iam, jwt, or key. none is public on all providers. iam is aws, gcp, and huawei. jwt is aws only and needs `authorizer.issuer` and `authorizer.audience`. key is azure and huawei. Tencent's API Gateway has no PATCH. On Tencent and Huawei, `{path+}` becomes a prefix route. On Oracle it becomes `{path*}`.

Sources: `docs/events.md#http`, `src/py_serverless_kit/config/schema.py`

```text
- http: GET /users/{id}                # shorthand "METHOD /path"
- http: /health                        # shorthand, method GET
- http:
    path: /users
    method: POST                       # GET POST PUT PATCH DELETE HEAD OPTIONS ANY (or "*")
    cors: true                         # or a mapping, see below
    auth: none                         # none | iam | jwt | key
    authorizer: {}                     # used by auth: jwt on AWS
```
