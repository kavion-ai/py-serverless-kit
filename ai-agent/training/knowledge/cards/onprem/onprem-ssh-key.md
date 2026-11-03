## SSH login: key, agent or password

The *SSH server* target (and `provider.options.deploy` for the functions) logs in one of three ways:

| *Log in with* | Studio | CLI | `pskit.yml` (`provider.options.deploy`) |
|---|---|---|---|
| **Key file** | path of the `.pem` / private key | `--pem ~/.ssh/server.pem` | `pem: ~/.ssh/server.pem` |
| **SSH agent / default key** | nothing to fill in | leave `--pem` out | leave `pem` out, or `auth: agent` |
| **Password** | the password (saved in `.pskit/ssh/`, owner-only, out of git) | `--ssh-password-env VAR` or `--ssh-password-file FILE` | `password_file: ~/.ssh/server.pass`, or `auth: password` with `SSHPASS` set |

*SSH agent / default key* is what `ssh user@host` does in a terminal: the agent, `~/.ssh/id_ed25519` /
`id_rsa`, and `~/.ssh/config` (`Host` aliases, `IdentityFile`, jump hosts).

Password logins go through **sshpass**, so the password never appears on a command line or in the state. Install it
on the machine that runs pskit: `sudo apt install sshpass`, `sudo dnf install sshpass`, or
`brew install hudochenkov/sshpass/sshpass`. The server must allow `PasswordAuthentication` (many cloud images allow
keys only).

**On Windows** (no sshpass), or to stop typing passwords: install a key once. pskit creates
`~/.ssh/pskit_ed25519`, logs in with the password one time (ssh asks for it in the terminal), adds the key to
`authorized_keys`, and checks that the key works:

```bash
pskit resources onprem ssh-key deploy@192.0.2.10          # [:2222] for another port
pskit resources onprem create jobs --service elasticmq --ssh deploy@192.0.2.10 --pem ~/.ssh/pskit_ed25519
```
