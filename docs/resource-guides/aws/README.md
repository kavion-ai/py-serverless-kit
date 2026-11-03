# AWS resources

How to attach AWS services you created in the [AWS Management Console](https://console.aws.amazon.com) to a Lambda
deployment made with pskit.

| `type` | AWS service | Guide |
|---|---|---|
| `queue` | Amazon SQS queue | [queue.md](queue.md) |
| `storage` | Amazon S3 bucket | [storage.md](storage.md) |
| `topic` | Amazon SNS topic | [topic.md](topic.md) |
| `database` | Amazon RDS / Aurora (PostgreSQL, MySQL) | [database.md](database.md) |
| `cache` | Amazon ElastiCache / MemoryDB (Redis OSS, Valkey) | [cache.md](cache.md) |
| `custom` | DynamoDB, Secrets Manager, anything else | [custom.md](custom.md) |

## Values you need for every AWS resource

| Value | Where |
|---|---|
| Region | top-right region selector (for example *Europe (Ireland) eu-west-1*); must match `provider.region` |
| Account ID | top-right account menu → *Account ID* (12 digits) |
| ARN | the resource's detail page (usually *Details* or *General information*) → *ARN* |

## How pskit runs on AWS (why some steps matter)

- Every function is its own **Lambda function**. They share **one IAM role** unless a function sets its own
  `functions.<fn>.iam.statements` or `iam.role`, which gives it a separate role. The `functions:` list on a resource
  limits the environment variables per function; permissions are granted per role, so functions sharing the role share
  the grants.
- For `storage`, `queue` and `topic` resources, pskit adds a **`pskit-resources` IAM policy** to each role it creates:
  S3 get/put/delete/list, SQS send/receive/delete/change-visibility/get-attributes/get-url, SNS publish. Nothing else is
  granted automatically: DynamoDB, Secrets Manager, KMS keys and so on need `provider.iam.statements`.
- An external bucket, queue or topic is **looked up by name** with a Terraform data source, in the account and region
  you deploy to. The function then also gets `PSKIT_RESOURCE_<KEY>_ARN` (and `_URL` for queues). If you set
  `connection.arn`, pskit uses that ARN as-is and does no lookup, which is how you bind a resource from another
  account or region (no `_URL` then: add `url:` to `connection` yourself).
- Triggers (`queue`, `storage`, `topic` events) on an external resource always use the name lookup, so the resource
  must be **in the same account and region** as the functions.
- With your own role (`iam.role`) pskit adds no policies; grant access yourself.
- Functions run outside any VPC unless you set `functions.<fn>.options.vpc_config`. See [database.md](database.md) and
  [cache.md](cache.md) for services that only live inside a VPC.

## Credentials for deploying

```bash
aws configure            # or aws sso login / AWS_PROFILE / provider.options.profile
aws sts get-caller-identity
```
