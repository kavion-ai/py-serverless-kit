# Accounts, encrypted project data and the audit log

`.pskit/` and `.env.*` stay out of git because they hold passwords. The vault lets a team share them anyway: their
encrypted form lives in `.pskit-vault/`, which **is** committed. Accounts control who can decrypt what and who can do
what, and everything is logged.

## First start

`pskit studio` on a new project asks who will use it:

* **Just me, on this computer:** no login, no master key, nothing encrypted and nothing added to git. Everything works
  as it did before accounts existed. See [Using pskit without accounts](#using-pskit-without-accounts).
* **A team, sharing through git:** you create the admin account (`pskit vault init` does the same in a terminal).

As the admin of a team project you then get two secrets, **shown only once**:

| Secret | Who has it | What it does |
| --- | --- | --- |
| **Master key** (`pskm-...`) | Every developer of the project | Needed at every login, together with a username and password. pskit never saves it, so keep it in a password manager |
| **Recovery code** (`pskr-...`) | The admin, offline | Together with the master key, sets a new admin password if every admin password is lost |

pskit also encrypts the secrets the project already has and adds `.pskit/`, `.env` and `.env.*` to `.gitignore`. If git
already tracks one of those files you get a warning: run `git rm --cached <file>` and change that secret, because it is
in your history.

```bash
git add .pskit-vault .gitignore
git commit -m "chore: add encrypted project data"
git push
```

## Using pskit without accounts

Choose **Just me** at the first start, or run:

```bash
pskit studio --no-auth
```

The choice is remembered in `.pskit/`, so it stays on this computer. No `.pskit-vault/` is created, your `.gitignore` is
not changed, and CLI commands need no login. The studio still needs the link it prints at start, as it always has.
`.env` and `.pskit` files stay as plaintext on this computer, and there are no permissions or audit log.

To change your mind, use **Users & audit > Turn on accounts**, or run `pskit vault init`.

A project with a `.pskit-vault/` always needs a login: neither the choice nor `--no-auth` applies to it.

## Another developer

The admin adds the account and sends the master key and first password over a safe channel, not over git or chat
history.

```bash
git clone <repo> && cd <repo>
pskit studio --open     # or: pskit login
# 1. master key   2. username   3. password
```

The first login asks them to choose their own password. Only what the account may read is decrypted, to the normal
paths. So `pskit deploy`, Terraform and SSH work as usual.

After a `git pull`, run `pskit vault sync` (or **Sync from vault** in the studio). Commit `.pskit-vault/` along with your
code. If you and a teammate changed the same protected file, the vault's version is used and yours is kept as
`<file>.vault-conflict`.

## What gets encrypted

| Area | Files | Key held by accounts with |
| --- | --- | --- |
| `env` | `.env`, `.env.*` (not `.env.example`), files named by `env_file` in `pskit.yml` | read on Env files |
| `servers` | `.pskit/onprem-servers.json`, `.pskit/ssh/`, `.pskit/terminal/known_hosts` | read on Servers |
| `services` | `.pskit/onprem-services.json` | read on On-prem services |
| `clusters` | `.pskit/onprem-clusters.json`, `.pskit/onprem-balancers.json` | read on Clusters or Load balancers |
| `deployments` | `deployment.json`, `onprem_deployed.json`, `admin-token`, `peer-token`, `terraform.tfstate` per stage | read on Deployments |
| `studio` | Saved test events, Hana settings | read on Test or Hana |

Any account with create, update or delete on **Deployments** holds every key, because a deploy needs them.

Each save in the studio is encrypted before the request returns. A background check every 3 seconds catches what other
processes write, and each CLI command encrypts its changes when it ends. Logging out, stopping the studio or a session
expiring (12 hours) encrypts and removes the plaintext. After a crash, the next start does this.

## How it is encrypted

* AES-256-GCM for all data, with scrypt (N=2^17) for passwords and X25519 to wrap keys. It uses the `cryptography`
  library, nothing home-made.
* Each area has its own random key. It is wrapped to the public key of each account allowed to read it, and to the
  recovery key.
* An account's private key is encrypted with its password, and the accounts file is encrypted with the master key.
  Decrypting data takes **the master key and the password of an account that holds that area**.
* Taking access away gives that area a new key and re-encrypts it.
* The master key is not saved between logins, so a copy of the repository and of your home folder is not enough to open
  the accounts file. It is on disk only inside a login session (see below).
* Earlier versions saved it as plaintext in `~/.pskit/vault-keys/<vault id>`. That copy is no longer read, and is deleted
  the next time you log in to that project. A project you stop using keeps its file until you delete it.

## Permissions

Admins can do everything. For a user, the admin ticks create, read, update and delete per feature in **Users & audit**,
or runs:

```bash
pskit vault users add priya --preset developer
pskit vault users set priya --allow code=crud --allow env=r --allow deploy=r
```

Changes apply to live sessions immediately. A new user starts with nothing ticked. Presets: `viewer`, `developer`,
`operator`. Everyone can read `pskit.yml`.

Saving `pskit.yml` is judged by what the save changes: a new function needs create on **Functions**, a removed one
delete, a changed one update. **Workflows** and **Resources** work the same, and the rest of the file needs update on
**Project settings**. Editing `pskit.yml` as a file under **Code** counts the same way. Files named by `extends` are not
judged like this, so treat update on **Code** as able to change them.
A studio route or CLI command with no entry in `vault/permissions.py` is admin-only.

For scripts and CI, set `PSKIT_MASTER_KEY`, `PSKIT_USER` and `PSKIT_PASSWORD`: the command logs in, runs and logs out.
Use a dedicated account with only the permissions it needs.

## Audit log

Every change, refused action, login (also failed ones), deploy, job result, CLI command and account change is recorded
with the user, time, machine and target. Secret values never are. See it in **Users & audit** or with:

```bash
pskit vault audit --user priya --action deploy
```

The log is encrypted and committed, one file per clone and month, so it does not cause merge conflicts. Each line is
chained to the one before, so a changed or removed line is reported. Cutting the newest lines off a file is not detected,
but git history shows it.

## What this protects against, and what it does not

**Protected:**

* Anyone who can read the repository but has no master key sees only ciphertext.
* A developer with the master key and an account cannot decrypt areas their account does not hold, even outside pskit.

**Not protected. Plan for these:**

* **Permissions other than decryption are enforced by pskit, on that person's own machine.** A developer can edit
  pskit's code, or delete `.pskit-vault/`, and bypass create, update and delete rules locally. What actually stops them
  reaching production is your cloud credentials and git branch protection. Audit entries can also be forged by someone
  with the master key.
* **Code is not encrypted.** Handler source stays readable and reviewable in git, on purpose. Edits made in an outside
  editor are not in the audit log, only in git history.
* **Plaintext is on disk while logged in**, including key material in `.pskit/.vault/sessions/`. File permissions are
  owner-only on Linux and macOS, but are not enforced this way on Windows.
* **Generated build output is not encrypted.** `.pskit/<provider>-<stage>/` (`host.env`, `pskit_host.json`,
  `main.tf.json`, artifacts) and `.pskit/backups/` stay as plaintext, because a running local host reads them. They
  are gitignored.
* **SSH keys outside the project** (`~/.ssh/...`) are not carried. Copy them with `pskit settings export`, or keep them
  in `.pskit/ssh/`.
* **Terminals, VS Code and Hana are marked full access:** they reach all that the process can, whatever the grid says.
* **Deploy permission means access to secrets.** Whoever can deploy could also ship code that prints them.
* **All accounts are one encrypted file.** `.pskit-vault/vault.json` cannot be merged. Commit and push right after changing
  a password or an account. If two people changed it, git reports a conflict: keep the newer side with
  `git checkout --theirs .pskit-vault/vault.json` and make the other change again.
* **The audit log reaches others only when it is committed.** A developer who never pushes `.pskit-vault/audit/` keeps
  their entries local.
* **Revoking does not erase history.** Old commits stay readable with the old keys, and the person may have copies.
  After someone leaves: remove the account, run `pskit vault rotate-master-key`, and **change the real secrets**.
* **Local `terraform.tfstate` in git:** two people deploying the same stage from different clones can conflict. For
  shared cloud stages, a remote backend with locking is still the better choice.
* **`--host 0.0.0.0` is plain HTTP.** Use TLS or an SSH tunnel: otherwise passwords and the master key cross the network
  unencrypted.

## Losing a key

| Lost | What to do |
| --- | --- |
| Your password | An admin runs `pskit vault users reset-password` |
| Every admin password | `pskit vault recover`, with the recovery code **and** the master key |
| The master key | An admin who is still logged in runs `pskit vault rotate-master-key` to get a new one. The recovery code cannot replace it |
| The master key, with no admin logged in | The data cannot be recovered. That is by design |

## Commands

| Command | Does |
| --- | --- |
| `pskit login` / `logout` / `whoami` | Unlock, lock, show who you are |
| `pskit vault init` | Create the vault and first admin |
| `pskit vault status` / `sync` | Show sessions and tracked plaintext / apply a pull |
| `pskit vault password` | Change your password |
| `pskit vault users list\|add\|set\|reset-password\|remove` | Manage accounts |
| `pskit vault audit` | Read the log |
| `pskit vault rotate-master-key` | Replace the master key |
| `pskit vault recover` | Use the recovery code and the master key to set a new admin password |
