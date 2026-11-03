## In studio
1. Open this path:
Setup & credentials > Export settings

2. Open this path:
Setup & credentials > Import into this project

## In the terminal
1. Run:

```
pskit settings export -o project.pskit-settings
```

2. Run:

```
pskit settings import project.pskit-settings --dry-run
```

## In code

Export writes an encrypted file. The passphrase is at least 8 characters in the studio. Import asks for confirmation unless --yes is set. --dry-run previews the change.

## Saving: what changes in pskit.yml - Values keep their written form

`${env:API_KEY}`, `${self:custom.x}` and `${opt:...}` are saved as written, never resolved. - Comments are **not** kept, and key order follows the studio's layout. Before every save the previous file is copied to `.pskit/studio/backups/pskit.<timestamp>.yml` (the last 20 are kept).

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
