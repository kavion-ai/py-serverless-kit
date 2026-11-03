## In studio
1. Open the service and choose Backup.

## In the terminal
1. Run:

```
pskit resources onprem backup orders-db
```

## In code

The backup command writes a file under .pskit/backups. The services guide lists which catalog entries support backup.

## Backups `Backup` streams a dump out of the container into `.pskit/backups/` on this

machine, or a folder you choose (**Backup → Save to folder → Browse…**, remembered; CLI `--dir` / `-o`), also from an SSH server: | Service | File | Restore | |---|---|---| | Redis / Valkey | `.rdb` | stop the container, copy it to `/data/dump.rdb` in the volume, start it | | PostgreSQL | `.sql` |

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
