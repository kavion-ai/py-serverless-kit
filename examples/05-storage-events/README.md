# 05 · Storage events

Shows functions triggered by objects being created or deleted, prefix/suffix filters, and
listening to a bucket that some other system owns.

## Record fields (same on every cloud)

| Field | Example |
| --- | --- |
| `record.bucket` | `storage-events-data-demo-1234-dev` |
| `record.key` | `incoming/sales 2026.csv` (already URL-decoded) |
| `record.size` | `1048576` |
| `record.action` | `created` or `deleted` |
| `record.raw` | the provider's native record, if you need more |

## The YAML

```yaml
- storage:
    bucket: "${self:custom.bucket}"   # pskit creates it (private, public access blocked on AWS)
    events: [created]                 # created | deleted
    prefix: incoming/
    suffix: .csv
```

- `existing: true` looks the bucket up instead of creating it. `pskit remove` never deletes it.
- Bucket names are global on AWS and GCP. `custom.bucket` therefore adds the stage
  (`${opt:stage}`), and you can set your own prefix with `DATA_BUCKET`.

| Cloud | created | deleted | prefix/suffix filter |
| --- | --- | --- | --- |
| AWS S3 | yes | yes | native |
| GCP Cloud Storage | yes | yes | applied by the runtime (Eventarc can't filter keys) |
| Azure Blob | yes | **no** (needs Event Grid) | blob path pattern |

On GCP a function with several storage triggers is deployed as one Cloud Function per
trigger. You still see a single logical function in `pskit info` and the dashboard.

## Run locally

```bash
pskit invoke -f import-csv -d '{"bucket": "data", "key": "incoming/sales.csv", "size": 2048}'
pskit invoke -f purge-index -t storage -d '{"key": "incoming/old.csv", "action": "deleted"}'
```

Expected for the first command:

```json
{"accepted": [{"bucket": "data", "key": "incoming/sales.csv", "dataset": "sales"}], "skipped": []}
```

## Deploy

```bash
DATA_BUCKET=acme-data pskit deploy
pskit deploy --provider gcp
pskit deploy --provider azure
```
