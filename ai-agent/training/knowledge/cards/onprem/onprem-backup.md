## Backups

`Backup` streams a dump out of the container into `.pskit/backups/` on this machine, or a folder you choose
(**Backup → Save to folder → Browse…**, remembered; CLI `--dir` / `-o`), also from an SSH server:

| Service | File | Restore |
|---|---|---|
| Redis / Valkey | `.rdb` | stop the container, copy it to `/data/dump.rdb` in the volume, start it |
| PostgreSQL | `.sql` | `psql -U pskit -f file.sql postgres` |
| MySQL / MariaDB | `.sql` | `mysql -uroot -p < file.sql` |
| MongoDB | `.archive` | `mongorestore --archive=file.archive -u pskit -p ... --authenticationDatabase admin` |
| RabbitMQ | `.definitions.json` | `rabbitmqctl import_definitions file.json` (messages are not included) |
| Kafka, NATS, MinIO | `.tar.gz` of the data directory | stop the container, extract into the volume, start it |

Data directories are copied while the service runs. For Kafka and NATS, stop producers first for a consistent copy.

These steps run on the on-premises provider. Saved servers are named once and then reused by deploy, services, and clusters. Open the matching studio page from the left navigation. Scaling cluster, Load balancers, Network map, and Resources are the pages for this work.

```
pskit validate
pskit resources onprem catalog
```

pskit resources onprem catalog lists the services and runtimes the create command can start. Passwords generated for a service are stored in the env file and under .pskit/, and they are left out of pskit.yml.
