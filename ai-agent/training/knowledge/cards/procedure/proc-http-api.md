## In studio
1. Open this path:
Functions > + Create function

2. Add an HTTP trigger and set the path and method.

## In the terminal
1. Run:

```
pskit invoke -f hello -t http --method GET --path /hello
```

2. Run:

```
pskit dev
```

## In code

A path parameter uses {id} for one segment. CORS can be true or a mapping with origins, methods, and headers. The runtime answers OPTIONS.

## `http` **Path templates** - `{name}` matches one segment and lands in

`event.http.path_params["name"]`. - `{name+}` matches the rest of the path (greedy) and is only allowed as the last segment: `/files/{path+}`. - Parameter names are identifiers: `{user_id}` is fine, `{user-id}` is not. pskit's runtime also matches routes itself, so path params and `405 Method Not Allowed` work the same on clouds with no API gateway (GCP, IBM, DigitalOcean, Cloudflare), including Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
