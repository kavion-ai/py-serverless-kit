## FAQ

**Do I add `py-serverless-kit` to my function's `requirements.txt`?**
: No. The runtime is vendored into every bundle automatically, and such lines are stripped.

**Can I keep using cloud SDKs (boto3, google-cloud-*)?**
: Yes, but that code becomes cloud-specific. Isolate it behind your own functions.

**How do I run something pskit doesn't model?**
: Use `functions.<fn>.options`, `provider.options`, and `provider.terraform.extra` with `${tf:...}` references. See configuration.md.

**Can I use OpenTofu?**
: Yes: `PSKIT_TERRAFORM_BIN=tofu` or `provider.terraform.binary: tofu`.

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
