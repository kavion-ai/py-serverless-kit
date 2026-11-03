# Procedure: Send a real test event

pskit trigger sends a real test event to a deployed function: an HTTP request, a queue message, an object upload, a topic message, or a direct invocation. pskit trigger --list also works before a deploy. Test without deploying with pskit invoke.

## In studio
1. Open Test and choose Send to the selected provider and stage.

## In the terminal
1. Run:

```
pskit trigger --list
```

2. Run:

```
pskit trigger -f worker -e 0 -d '{"order_id": 1}'
```

## In code

pskit trigger sends a real event to a deployed function. pskit invoke is the local equivalent.

## `pskit invoke` and `pskit workflow run`

Details are in the CLI reference.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
