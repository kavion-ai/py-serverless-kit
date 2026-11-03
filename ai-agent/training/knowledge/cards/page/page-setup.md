# Studio: Setup & credentials

How to open: Left navigation label Setup & credentials. The top bar button ⇅ Settings opens the same transfer form in a drawer, not this whole page.

What it is for: docs/studio.md says this page runs the same checks as `pskit doctor` for the provider in the top bar: Terraform, the cloud CLI, credentials, required provider options and, for on premises, ssh, scp, Docker and the key file. Each problem shows the download link and the steps for Windows, macOS or Linux.

What you see: A Check again button (Checking… while it loads). Section Checks. Section "Move settings to another machine", hint "export / import .pskit, encrypted", with Export settings (Exporting… while busy). Section "AWS credentials (aws configure)", hint "~/.aws/credentials". Section Environment variables, hint "read by Terraform and the provider". Section On-premises connection, hint provider.options.deploy. Section Project environment. Its hint is "npm install" for a Node project and ".venv + requirements" otherwise.

What you can do: Check again re-runs the doctor-style checks. docs/studio.md says you can save an AWS access key as a profile in ~/.aws, set provider variables such as ARM_SUBSCRIPTION_ID or CLOUDFLARE_API_TOKEN for this studio session only (secret values are never sent back to the browser), start a browser login (`az login`, `gcloud auth application-default login`, `aws sso login`), and test the SSH connection of an on-prem deploy. Export settings matches `pskit settings export`. The import button label is "Import into this project", which matches `pskit settings import`. Under Project environment the button is "Create .venv and install", or "Install requirements" when a venv already exists and recreate is off. The Node row says "npm install", and the help says npm ci when package-lock.json exists, else npm install.

Tips and limits: Session environment values are for Terraform and the provider during this studio process. docs/studio.md says secret values are not sent back to the browser. The private-key Browse… control, described in that same section, lists names and sizes under the machine running studio and starts in ~/.ssh. File contents are not read.

Sources: `dashboard-ui/src/studio/views/Setup.tsx`, `docs/studio.md#setup-logs-and-provider-differences`, `docs/studio.md#project-environment-trigger-resources-and-remove`
