# 18 · Resources: buckets, queues, topics and external services

`resources:` declares the services your functions use, once, for every cloud.

| Resource | Kind | What pskit does |
| --- | --- | --- |
| `uploads` | managed storage | creates the bucket (no trigger needed) and grants access |
| `jobs` | managed queue | creates the queue; `worker` consumes it with `queue: {resource: jobs}` |
| `notifications` | managed topic | creates the topic and grants publish |
| `orders-db` | external database | creates nothing; passes host/port/database to `api` and `worker` |

Each bound function gets environment variables such as `PSKIT_RESOURCE_UPLOADS_NAME`
(plus `_ARN` / `_URL` / `_ID` where the provider knows them). Handlers read them with:

```python
from py_serverless_kit import resource

bucket = resource("uploads").native_name
db = resource("orders-db")
host, port = db["host"], db["port"]
```

Try it:

```bash
pskit invoke -f api -t http --path /bindings
pskit deploy                     # AWS
pskit deploy --provider onprem   # local host; see pskit.yml for Redis / S3-compatible drivers
```

Secrets: keep them out of `connection`. Store the *name* of a secret variable there
(`password_env`) and set the secret itself through your platform's secret store.
