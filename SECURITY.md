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
- An on-prem host that listens on the network always has an admin token: `provider.options.admin_token`, or one generated into `.pskit/onprem-<stage>/admin-token`. It refuses to start without one. A loopback-only host needs no token from this machine and refuses requests driven by a web page on another site.
- On-prem files holding secrets (`pskit_host.json`, `host.env`, the deploy record, the token files) are mode `0600`, locally, in the release archive and on the server.
- Browser terminals remember and check SSH host keys, and refuse a server whose key changed. The first connection is trusted unless `known_hosts` names a file of pinned keys.

### Known limits

Accounts and the encrypted vault have limits of their own, listed in
[docs/security-vault.md](docs/security-vault.md#what-this-protects-against-and-what-it-does-not). In short, only reading
secrets is enforced by encryption; the other permissions are enforced by pskit on the developer's own machine.


- The on-prem host's AWS-compatible APIs treat the access key id as a bearer token and do not verify the SigV4 signature. The host serves plain HTTP: use TLS or a tunnel on an untrusted network.
- Service passwords are passed to `docker run` / `docker exec` as `-e NAME=value` arguments, so they are visible in the process list of the machine running them while the command runs.
