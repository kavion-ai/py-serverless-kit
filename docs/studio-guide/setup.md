# Setup & credentials page in studio

Search terms: setup, credentials, doctor, prerequisites, terraform missing, aws configure, AWS profile, az login, gcloud login, aws sso, environment variables, virtual environment, venv, npm install, export settings, import settings, move to another machine

The **Setup & credentials** page checks what this machine needs to deploy: tools, credentials and provider settings.
Everything runs where pskit studio runs. Sidebar: **Setup & credentials** (⚙). It is the studio side of
`pskit doctor`.

## Check tools and credentials in studio

The Setup page runs the same checks as `pskit doctor` for one provider.

1. Open **Setup & credentials**. The **Provider** list starts on the top bar's provider; pick another to check it.
2. Pick your **Operating system** (**Windows**, **macOS**, **Linux**). Studio guesses it; the fix steps follow it.
3. The badge says **N missing**, **N to check** or **ready to deploy to <Provider>**.
4. The **Checks** section lists each check with an icon: ✓ ready, ✗ missing, ! check, i optional.
5. Click **How to fix** (or **Details** on a passed check) to see a summary, download links, numbered steps for your
   OS and commands with **Copy** buttons.
6. Some checks have a fix button that runs on this machine:

   | Button | What it runs |
   |---|---|
   | **Test connection** | The SSH test of the on-prem deploy |
   | **Add credentials** | Scrolls to the AWS profile form |
   | **Set variables** | Scrolls to the environment variables form |
   | **Sign in (az login)** | `az login` |
   | **Sign in (gcloud)** / **Sign in (gcloud ADC)** | `gcloud auth login` / `gcloud auth application-default login` |
   | **Sign in (aws sso)** | `aws sso login` |

7. The command's output shows under **Running: <command>** (with cancel). When it succeeds the checks run again.
8. **Check again** (top right) re-runs every check.

From the terminal:

```bash
pskit doctor              # provider from pskit.yml
pskit doctor -p azure     # another provider, works without pskit.yml
pskit doctor -p onprem --json
```

## Save an AWS access key as a profile in studio

The **AWS credentials (aws configure)** section appears when the Setup provider is AWS. It writes the same files as
`aws configure` (`~/.aws/credentials` and `~/.aws/config`) on this machine; other profiles are kept.

1. **Profile** (required): `default`, `pskit`, `dev`, `prod` or your own name.
2. **Access key ID** (required, starts with `AKIA…`) and **Secret access key** (required).
3. **Default region** (optional) and **Session token** (only for temporary STS / SSO credentials).
4. Click **Save profile**. The toast says "Saved AWS profile <name> in ~/.aws".

Use the profile with `AWS_PROFILE=<name>` (next section), or name it `default`.

## Set provider environment variables for the studio session

The **Environment variables** section ("read by Terraform and the provider") lists the variables the provider reads,
for example `ARM_SUBSCRIPTION_ID`, `CLOUDFLARE_API_TOKEN` or `AWS_PROFILE`. Each row shows ✓ when set.

1. Type the value and click **Set for this session**. **Clear** removes it.
2. The value applies to deploys started from this studio until it stops. Nothing is written to disk, and secret values
   are never sent back to the browser.
3. To keep a value, set it in your shell profile before starting studio: `export NAME=value` (Linux, macOS) or
   `setx NAME value` (Windows).

## Create the project's .venv or run npm install in studio

The **Project environment** section prepares the project's own environment on this machine.

For a Python service:

1. **Virtual environment** shows `Python X.Y` when `.venv` exists, or **not created**.
2. **Requirements** shows whether `requirements.txt` (or `package.requirements`) exists.
3. **Python**: pick one of the interpreters found on this machine (including the Windows `py` launcher's).
4. **Recreate**: off = reuse `.venv` if it exists; on = delete and recreate it.
5. Click **Create .venv and install** (or **Install requirements** when `.venv` exists). The output streams below.
6. Point your editor at `.venv` as the interpreter.

For a Node.js service (or when `package.json` exists), **Node.js** shows the version on `PATH`, **Dependencies**
shows whether `node_modules` exists, and **npm install** runs `npm ci` when `package-lock.json` exists, else
`npm install`.

The same from the terminal:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip install -r requirements.txt
npm install
```

## Edit the on-prem SSH connection on the Setup page

The **On-premises connection** section appears when the Setup provider is `onprem`. It edits the same
`provider.options.deploy` as [Overview](overview.md#choose-where-the-on-prem-host-runs-in-studio), with fewer fields:
**Where the host runs** (**This machine**, **SSH server**, **Docker**), then SSH host, SSH user, SSH port, Private
key, Known hosts, Use sudo and Docker host. Remote path, install mode and image are on Overview. Save `pskit.yml`
after changing them.

## Move studio settings to another machine

The **Move settings to another machine** section (also the **⇅ Settings** button in the top bar) exports the
settings `.pskit/` keeps out of git: saved servers, clusters, load balancers, on-prem services and SSH logins. The
file also holds secrets (SSH passwords and keys, also those in `~/.ssh`, service passwords and tokens, admin tokens,
env files named in `pskit.yml`). It is always encrypted with your passphrase. Terraform state is not included.

Export:

1. Type a **Passphrase** (at least 8 characters) and type it **Again**.
2. **Include pskit.yml (functions, resources, providers)** is on by default.
3. Click **Export settings**. The browser downloads `<service>.pskit-settings`, and a box lists what is in it.
4. Send the passphrase another way than the file.

Import on the other machine:

1. Pick the file under **Settings file** and type the **Passphrase**.
2. Click **Preview**. A table lists per group what is **Added**, **Replaced** and **Kept** (or **Removed**), the files
   written and SSH keys copied.
3. **Replace** (off by default) removes saved servers, clusters and services that are not in the file. Off = merge,
   the file's entries win.
4. Click **Import into this project** and confirm **Import these settings?**. The current settings are backed up to
   `.pskit/backups` first. If `pskit.yml` was in the file, the page reloads.

From the terminal:

```bash
pskit settings export -o prod.pskit-settings --with-config
pskit settings import prod.pskit-settings --dry-run
pskit settings import prod.pskit-settings --replace --yes
```

## See also

- [Studio guide](README.md)
- [Providers: credentials per cloud](../providers/README.md)
- [On-prem servers](../onprem/servers.md)
- [Install runtimes and Docker on servers](../onprem/terminal-and-software.md)
