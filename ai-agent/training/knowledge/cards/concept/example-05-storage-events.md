# Example: 05-storage-events

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, pskit.yml, requirements.txt.

Comments in pskit.yml: Bucket names are global on AWS/GCP: make them unique per account and stage. Azure blob triggers fire on created/updated blobs only. Deletions need an Event Grid subscription, so on Azure the function is deployed without a trigger (invoke-only) - wire Event Grid separately if you need it. A blob trigger on a container outside the Function App's storage account needs a connection string - here we listen to an app-owned container instead. The shared audit bucket is not on this machine. Create a local directory bucket with the host so the function has somewhere to listen.

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

Expected for the first command:
