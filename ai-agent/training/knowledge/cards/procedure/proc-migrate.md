## In studio
1. Change the provider in the top bar and read the problems list.

## In the terminal
1. Run:

```
pskit validate -p gcp
```

2. Run:

```
pskit providers
```

## In code

Keep the handler. Put cloud differences under providers.gcp or the selected provider block. pskit validate reports triggers that provider cannot run.

## Step 5: move to another cloud

Typical changes, all in YAML: - add provider options (`gcp: options.project`, `azure: options.subscription_id`, …), see providers.md; - replace `auth: jwt` (AWS only) with `auth: iam` / `key`, or validate tokens in the handler; - drop `existing: true` for resources that should be created on the new cloud; - remove AWS-only `functions.<fn>.options` and `terraform.extra` (or add the equivalent for the new cloud).

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
