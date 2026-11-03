# Security Policy

## Supported versions

Security fixes go into the latest minor release line. Because the function runtime is bundled into each deployment, users must **redeploy** (`pskit deploy`) after upgrading to get a runtime fix.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

Report them privately through GitHub's **Security → Report a vulnerability** (private advisory) at <https://github.com/kavion-ai/py-serverless-kit/security/advisories/new>. Include:

- affected version (`pskit --version`) and provider;
- a description of the issue and its impact;
- steps to reproduce or a proof of concept, if you have one.

We aim to acknowledge reports within 3 business days and to ship a fix or mitigation within 30 days for high-severity issues. We'll credit you in the advisory unless you'd rather stay anonymous.

## Security-relevant defaults

- HTTP 500 responses never include exception details unless `PSKIT_DEBUG=1` is set.
- `.env`, Terraform state files and `pskit*.yml` are excluded from deployment bundles by default.
- `.pskit/` (which holds local Terraform state) gets its own `.gitignore`. Use a remote, encrypted state backend (`provider.state`) for team work.
- Created storage buckets block public access (AWS) and use uniform access (GCP).
- `auth: none` HTTP routes are public. Use `auth: iam` or `auth: jwt` where the provider supports them.
- Embedded workflow orchestrators get an HTTP trigger by default. Set `workflows.<name>.options.http: false` to make them invoke-only.
