# Concept: storage events

`- storage: uploads-bucket` is shorthand. The long form sets `bucket`, `existing` (false means pskit creates the bucket), `events` (default `[created]`; `deleted` is the other value), `prefix`, and `suffix`. Each record has `bucket`, `key`, `size`, and `action` (`created` or `deleted`).

AWS uses S3 notifications and native filters. Created buckets block public access. GCP uses Cloud Storage via Eventarc. Filters are applied by the runtime. `created` and `deleted` become separate deployments. Azure is a blob trigger in the app's storage account, created or updated only, not deleted. The container name is 3–63 lowercase characters. An existing bucket in another account needs `options.storage_connection`. Alibaba OSS, Tencent COS, and Huawei OBS use native filters. A Tencent bucket name must be `<name>-<APPID>`. Oracle uses an Events rule and does not support the filters: the doc says to filter in the handler, and the bucket must have Emit Object Events enabled.

On premises the bucket is a directory. Prefix and suffix are applied in the host. `builtin` creates the directory. `{use: directory, path}` uses one you already have. The first start records current files and does not emit them.

`- storage: {resource: uploads, prefix: in/}` uses the resource's native name and sets `existing` from `external`. On premises a resource can move the bucket to an S3-compatible store. A storage event may set both `resource` and `bucket`: that bucket on the resource's storage service.

Sources: `docs/events.md#storage`, `docs/events.md#events-backed-by-a-resource`

```text
- storage: uploads-bucket              # shorthand
- storage:
    bucket: uploads-bucket
    existing: false                    # true = bucket already exists
    events: [created, deleted]         # default [created]
    prefix: incoming/
    suffix: .csv
```
