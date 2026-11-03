## Security notes

- 500 responses never include exception details unless `PSKIT_DEBUG` is set.
- `.env`, Terraform state and `pskit*.yml` are excluded from bundles. `.pskit/` is git-ignored.
- `auth: none` routes are public. Embedded workflow orchestrators get a public `POST /workflows/<name>` route unless you set `options.http: false`.
- `resources:` connection values are function environment variables: they land in Terraform state and, on premises, in `pskit_host.json`. Pass the *name* of a secret variable instead of the secret (resources.md).
- On premises, set `admin_token` when the host binds beyond loopback: it guards `/__pskit/*` (queues, invoke, workflows, executions, logs, stats). `pskit dashboard --serve` binds loopback and never sends that token to the browser.
- Created AWS buckets block public access. Prefer a least-privilege `iam.statements` over `"*"` resources.
- Keep secrets out of YAML: use `${env:...}` in CI or a secret manager via `${tf:...}`.
- Report vulnerabilities privately (see `SECURITY.md` in the repository root).

Add -v to the command when you need the traceback. Start with pskit validate and pskit doctor. The studio Problems list and Setup & credentials show the same class of setup errors.

Setup & credentials > Check again

```
pskit doctor
pskit validate
```
