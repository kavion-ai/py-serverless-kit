## In studio
1. Open this path:
Resources > + Add resource

2. Open this path:
Functions > + Create function

## In the terminal
1. Run:

```
pskit invoke -f on-upload -t storage -d '{"bucket": "uploads", "key": "in/a.txt"}'
```

2. Run:

```
pskit resources send uploads -d '{"key": "in/a.txt", "content": "test"}'
```

## In code

A storage event can set prefix, suffix, and events. Each record has bucket, key, size, and action.

## `storage` Each record has `bucket`, `key`, `size` and `action` (`"created"` /

`"deleted"`). | Provider | Service | Filters | Notes | |---|---|---|---| | aws | S3 notification | native | created buckets block public access | | gcp | Cloud Storage via Eventarc | applied by the runtime | `created` and `deleted` become separate deployments | | azure | Blob trigger in the app's storage account | path pattern

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
