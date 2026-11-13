# AWS-compatible services

Self-hosted servers that speak an AWS API, so code written for AWS (boto3, the AWS SDKs, the AWS CLI) runs on
premises with only an `endpoint_url` change. pskit starts them as one-click on-prem services; each one can also run
on its own with its Dockerfile.

| Folder | API | Implementations | pskit service |
|---|---|---|---|
| [`secretsmanager/`](secretsmanager/README.md) | AWS Secrets Manager (SigV4 authentication, web console) | Python, Node.js | `secretsmanager`, `secretsmanager-node` |
| [`s3/`](s3/README.md) | Amazon S3 (SigV4 / SigV2, versioning, multipart, policies, lifecycle, web console) | Python, Node.js | `s3`, `s3-node` |
| [`ses/`](ses/README.md) | Amazon SES v1 + v2 and an SES SMTP endpoint (identities, DKIM, templates, relay / direct / capture delivery, web console) | Python, C++ | `ses`, `ses-cpp` |

The wheel ships this folder as `py_serverless_kit/aws`, so `pskit resources onprem create` can copy the servers into
a stock `python` / `node` / `alpine` image without building or pushing anything.
