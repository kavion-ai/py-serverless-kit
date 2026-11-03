# HTTP trigger

Search terms: http, api, rest api, route, endpoint, url, path parameters, query string, method, GET POST, cors, auth, jwt, iam, api key, API Gateway, function URL

The pskit `http` trigger calls a function for an HTTP request on a route such as `GET /users/{id}`. pskit creates the
cloud's gateway or function URL, and its own router matches paths, fills path parameters, answers CORS preflights and
returns 405 for wrong methods the same way on every cloud.

## Write an HTTP trigger in pskit.yml

The pskit `http` trigger has a shorthand string and a full form.

```yaml
events:
  - http: GET /users/{id}            # "METHOD /path"
  - http: /health                    # path only: method GET
  - http:
      path: /users
      method: POST                   # GET POST PUT PATCH DELETE HEAD OPTIONS ANY ("*" = ANY)
      cors: true                     # or a mapping (below)
      auth: none                     # none | iam | jwt | key
      authorizer: {}                 # jwt settings (AWS)
```

| Key | Default | Meaning |
|---|---|---|
| `path` | `/` | route template; a leading `/` is added |
| `method` | `GET` | upper-cased; `*` becomes `ANY` |
| `cors` | `false` | `true` for defaults, or a CORS mapping |
| `auth` | `none` | who may call it (support differs per cloud) |
| `authorizer` | `{}` | `issuer`, `audience`, optional `identity_source`, `scopes` for `auth: jwt` |

Path templates: `{name}` matches one segment, `{name+}` matches the rest of the path and is allowed only as the last
segment (`/files/{path+}`). Names are identifiers (`{user_id}`, not `{user-id}`). The same `METHOD /path` may not be
used by two functions: `route GET /users is used by both 'a' and 'b'`. Static routes win over parameterised ones.

## Read the request in the handler

For an `http` trigger `event.type == "http"` and `event.http` is an `HttpRequest`.

```python
from py_serverless_kit import BadRequest, Context, Event, Response


def update_user(event: Event, ctx: Context):
    req = event.http
    user_id = req.path_params["id"]                  # from /users/{id}
    verbose = req.query.get("verbose") == "1"        # ?verbose=1 (last value wins)
    tags = req.multi_query.get("tag", [])            # ?tag=a&tag=b
    token = req.headers.get("authorization")         # case-insensitive
    body = req.json()                                # invalid JSON -> 400
    if "email" not in body:
        raise BadRequest("email is required")
    ctx.logger.info("update", extra={"user": user_id, "ip": req.source_ip})
    return Response.json({"id": user_id, **body}, status=200, headers={"x-verbose": str(verbose)})
```

| Field | Notes |
|---|---|
| `method`, `path`, `route` | `route` is the matched template, e.g. `/users/{id}` |
| `headers` | case-insensitive; repeated headers joined with `", "` |
| `query`, `multi_query` | `dict[str, str]` and `dict[str, list[str]]` |
| `path_params` | from `{name}` / `{name+}` |
| `body`, `text()`, `json(default=...)`, `form()` | raw bytes (base64 already decoded), text, JSON, url-encoded form |
| `content_type`, `cookies`, `source_ip` | parsed helpers |

What you return becomes the response: see [../functions/invoke-and-test.md](../functions/invoke-and-test.md).
Node.js: `event.http.pathParams`, `event.http.json()`.

## Add an HTTP trigger in studio

1. Sidebar **Functions** → open the function → **2 Triggers** → card **HTTP endpoint**.
2. **Route**: pick the method and type the path (default `/<function-name>`). Path parameters appear in a hint with
   the `event.http.path_params[...]` expression.
3. **Auth**: `none` = public. Values the provider cannot enforce are disabled; hover for the reason.
4. **Authorizer** (only with `jwt`): JSON such as `{"issuer": "https://...", "audience": ["api"]}`.
5. **CORS**: toggle on for defaults; **Allowed origins** (**Add origin**) limits origins (empty = `*`).
   Other CORS keys (`methods`, `headers`, `expose_headers`, `allow_credentials`, `max_age`) are set on the **YAML** page.
6. **Apply changes**, then **Save**.

## Configure CORS

The pskit CORS settings are applied by the runtime on every cloud: it answers `OPTIONS` preflights with 204 and adds
`Access-Control-*` headers. AWS also configures CORS on the HTTP API.

```yaml
cors:
  origins: ["https://app.example.com"]   # default ["*"]
  methods: [GET, POST]                    # default GET POST PUT PATCH DELETE OPTIONS
  headers: [Content-Type, Authorization]  # default Content-Type Authorization X-Requested-With
  expose_headers: []
  allow_credentials: false               # true + origins "*": the request's Origin is echoed, not "*"
  max_age: 600
```

## HTTP auth per provider

The pskit `auth` value is enforced by the cloud's gateway, so support differs. Unsupported values fail validation.

| Provider | `none` | `iam` | `jwt` | `key` |
|---|---|---|---|---|
| aws (API Gateway HTTP API) | yes | `AWS_IAM` | JWT authorizer; needs `authorizer.issuer` and `authorizer.audience` | no ("use jwt or iam") |
| azure | yes | no | no | function key |
| gcp | yes (public invoker) | yes (no public invoker binding) | no | no |
| huawei | yes | `IAM` | no | `APP` |
| alibaba, tencent, oracle, ibm, digitalocean, cloudflare, onprem | yes | no | no | no |

Where only `none` exists, check tokens in the handler. AWS JWT example:
`auth: jwt` with `authorizer: {issuer: https://example.auth0.com/, audience: [api], scopes: [read]}`.

## HTTP differences per provider

The pskit runtime routes the same way everywhere; the native gateway differs.

| Provider | Native | Notes |
|---|---|---|
| aws | API Gateway HTTP API | |
| azure | HTTP trigger in one Function App | `{name+}` becomes `{*name}` |
| gcp | Cloud Function URL | runtime routing; a function with HTTP and events is split into several Cloud Functions |
| alibaba | HTTP trigger | `ANY` expands to every method |
| tencent | API Gateway | no `PATCH` (use `ANY`); `{path+}` becomes a prefix route |
| huawei | API Gateway (needs `provider.options.apig_instance_id`) | `{path+}` becomes a prefix route |
| oracle | API Gateway | `{path+}` becomes `{path*}`; needs an IAM policy for the gateway (validation warning shows it) |
| ibm, digitalocean | function URL | public; runtime routing |
| cloudflare | Worker (`workers.dev` or a `route` with `zone_id`) | runtime routing |
| onprem | the pskit host's HTTP server | runtime routing; optional load balancer |

`pskit info` shows each function's URL after deploy.

## Test an HTTP trigger

- Locally: `pskit invoke -f get-user --path "/users/7?verbose=1" -H "Authorization: Bearer x"`, or `pskit dev`
  then `curl localhost:3000/users/7`.
- Studio: **Test** → the function → the `GET /users/{id}` card → edit **Request** → **▶ Run locally** or
  **☁ Send to <provider> / <stage>**.
- Deployed: `pskit trigger -f get-user -e 0 --path /users/7`, or `curl` the URL from `pskit info`.

## Common HTTP trigger errors

| Message or symptom | Fix |
|---|---|
| `invalid path template '/x/{a-b}'` | use identifier names, `{path+}` only last |
| `method must be one of GET, POST, ...` | use a listed method or `ANY` |
| `route POST /items is used by both ...` | give each route one function |
| `jwt auth needs authorizer.issuer and authorizer.audience` (AWS) | fill `authorizer` |
| `http auth 'iam' is not supported on Azure; use none or key ...` | pick a value from the auth table |
| `Tencent API Gateway does not support PATCH; use ANY` | change the method |
| `HTTP events need a dedicated API Gateway instance: set provider.options.apig_instance_id` (Huawei) | set the option |
| 405 with an `allow` header | the path exists but not for this method |
| 400 on `event.http.json()` | the body is empty or not JSON; pass `default=` |

## See also

- [README.md](README.md)
- [../functions/invoke-and-test.md](../functions/invoke-and-test.md)
- [../handlers.md](../handlers.md)
- [../onprem/load-balancers.md](../onprem/load-balancers.md)
- [../providers/README.md](../providers/README.md)
