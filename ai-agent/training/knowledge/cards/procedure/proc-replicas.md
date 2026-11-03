## In studio
1. In the create service drawer, choose Primary + read replicas for a database.

## In the terminal
1. Run:

```
pskit resources onprem replicas list orders-db
```

## In code

A replicated database has a primary for writes and replicas for reads. The services guide describes the primary and the replica servers.

## Databases: one server, or a primary with read replicas

A database (PostgreSQL, MySQL, MariaDB, MongoDB) is created in one of two shapes. The create form asks under **Scaling**: - **Single server**: one container on this machine or a server. To scale it up, give that server more CPU and memory (vertical scaling). Nothing else changes.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
