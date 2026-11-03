## In studio
1. Use the replica controls on the database service.

## In the terminal
1. Run:

```
pskit resources onprem replicas add orders-db db-1
```

2. Run:

```
pskit resources onprem replicas remove orders-db db-1
```

## In code

replicas add starts one more read replica on a saved server. replicas remove takes it off. Both are separate from deleting the primary.

## Databases: one server, or a primary with read replicas

A database (PostgreSQL, MySQL, MariaDB, MongoDB) is created in one of two shapes. The create form asks under **Scaling**: - **Single server**: one container on this machine or a server. To scale it up, give that server more CPU and memory (vertical scaling). Nothing else changes.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
