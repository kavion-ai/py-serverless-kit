## Deploy and state

**State conflicts / "resource already exists" after deploying from another machine**
: The default state lives in `.pskit/` on one machine. Configure `provider.state` with a remote backend (S3 + DynamoDB lock, GCS, `azurerm`, …), then `terraform init -migrate-state` via `pskit tf -- init -migrate-state`.

**Changed nothing but Terraform wants to update the function**
: The artifact is deterministic, so a real diff means a source file, dependency or `pskit_manifest.json` changed. Inspect `.pskit/<provider>-<stage>/build/`.

**Provider plugin downloads are slow in CI**
: Set `TF_PLUGIN_CACHE_DIR` and cache that directory.

Add -v to the command when you need the traceback. Start with pskit validate and pskit doctor. The studio Problems list and Setup & credentials show the same class of setup errors.

Setup & credentials > Check again

```
pskit doctor
pskit validate
```

Setup & credentials > Check again

```
pskit doctor
pskit validate
```

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
