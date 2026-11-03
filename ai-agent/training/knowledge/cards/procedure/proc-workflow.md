## In studio
1. Open Workflows and add a workflow with start_at and states.

## In the terminal
1. Run:

```
pskit workflow show order-pipeline
```

2. Run:

```
pskit workflow run order-pipeline
```

## In code

A task state names a function. retry and catch sit on that state. pskit workflow run uses the embedded engine on this machine.

### Retry and catch

Error names are the **Python exception class names** your handler raises (e.g. `ValueError`). The first matching retrier is used. When retries are exhausted, the first matching catcher routes to its `next` state. Without a match the run fails.

## Commands

`workflow run` exits with code 2 when the run fails.

Deployed workflows:

These work against the on-premises host, AWS Step Functions and Google Cloud Workflows. See Workflow executions.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
