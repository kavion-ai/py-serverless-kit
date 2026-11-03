## In studio
1. Open this path:
Resources > + Add resource

2. Open this path:
Resources > How to use

## In the terminal
1. Run:

```
pskit resources usage orders-db -p aws -s dev
```

2. Run:

```
pskit resources send --list
```

## In code

type database requires external true. Put the password in a variable named by password_env. Read it with resource("orders-db") and ctx.env.

## Fields | Key | Default | Notes | |---|---|---| | `type` | — | required

`storage`, `queue`, `topic`, `database`, `cache` or `custom` | | `external` | `false` | `true`: the service already exists or runs outside pskit. pskit never creates, changes or destroys it | | `name` | resource key | native name of the bucket / queue / topic.

### Databases, caches and other services

| Service | Python | Node.js |
|---|---|---|
| PostgreSQL | `psycopg[binary]` | `pg` |
| MySQL / MariaDB | `pymysql` | `mysql2` |
| MongoDB | `pymongo` | `mongodb` |
| Redis / Valkey | `redis` | `ioredis` |
| Memcached | `pymemcache` | `memjs` |
| SMTP | standard library `smtplib` | `nodemailer` |
