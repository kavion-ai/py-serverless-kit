# Example: 18-resources

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: Services the functions use. Managed ones are created by pskit; `external: true` ones already exist and pskit only hands their details to the handlers. On-premises the same resources can live in services you already run: resources: jobs: external: true options: {driver: redis, url: "redis://127.0.0.1:6379/0"} uploads: external: true options: driver: s3 endpoint: http://127.0.0.1:9000 access_key: ${env:MINIO_ACCESS_KEY} secret_key: ${env:MINIO_SECRET_KEY}

# 18 · Resources: buckets, queues, topics and external services

`resources:` declares the services your functions use, once, for every cloud.

| Resource | Kind | What pskit does |
| --- | --- | --- |
| `uploads` | managed storage | creates the bucket (no trigger needed) and grants access |
| `jobs` | managed queue | creates the queue; `worker` consumes it with `queue: {resource: jobs}` |
| `notifications` | managed topic | creates the topic and grants publish |
| `orders-db` | external database | creates nothing; passes host/port/database to `api` and `worker` |

Each bound function gets environment variables such as `PSKIT_RESOURCE_UPLOADS_NAME`
(plus `_ARN` / `_URL` / `_ID` where the provider knows them). Handlers read them with: Try it: Secrets: keep them out of `connection`. Store the *name* of a secret variable there
(`password_env`) and set the secret itself through your platform's secret store.
