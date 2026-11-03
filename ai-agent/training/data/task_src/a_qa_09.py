"""Category A (docs Q&A and how-to), batch 9: on-premises one-click services (credentials, web UIs, consoles, what is
written, addresses, data browser, removal, monitoring, import, backups, troubleshooting). Hand-written; assembled by
tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


SV = "docs/resource-guides/onprem/services.md"

CONVERSATIONS = [
    A(161, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SV}#credentials-and-network"],
      user="I want pskit to create a PostgreSQL for our functions, but with our own user orders_app and a password we choose, not a generated one. And it should only accept connections from that machine.",
      steps=[S("search_docs", query="one-click service user password listen on",
               docs=[D(SV, "credentials-and-network", end="Keep them on `127.0.0.1` or a private network.")])],
      final="""Yes. The create form's **Security** box sets the user, the password and where it listens [docs/resource-guides/onprem/services.md#credentials-and-network].

**In the terminal**
1. Put the password in a variable (8-128 characters of letters, digits and `!#%*+,.:=?@^_~-`):
```bash
export ORDERS_DB_PASSWORD='<your password>'
```
2. Create it:
```bash
pskit resources onprem create orders-db --service postgres --user orders_app --password-env ORDERS_DB_PASSWORD --bind 127.0.0.1 --save
```

**In studio**
1. Open **Resources > On-prem services > + Create service** and pick PostgreSQL.
2. In **Security**, enter the user and password, and choose to listen on 127.0.0.1.
3. Click **Create**, review the draft and **Save**.

`127.0.0.1` lets only programs on that same machine connect. The default is `127.0.0.1` on this machine and `0.0.0.0` on an SSH server."""),

    A(162, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{SV}#credentials-and-network"],
      user="one-click kafka (redpanda) with --password, possible?",
      steps=[S("search_docs", query="kafka redpanda password authentication one-click",
               docs=[D(SV, "credentials-and-network", start="Kafka (Redpanda), ElasticMQ", end="Keep them on `127.0.0.1` or a private network.")])],
      final="""No. Kafka (Redpanda), ElasticMQ, Memcached and Mailpit run **without authentication** in this setup, and the CLI refuses a password for them [docs/resource-guides/onprem/services.md#credentials-and-network].

Instead:
- keep it on `127.0.0.1` (`--bind 127.0.0.1`) or a private network, and limit the port in the firewall;
- or, if you need a password-protected queue, use Redis / Valkey or RabbitMQ:
```bash
pskit resources onprem create events --service redis --role stream --attach worker --save
```"""),

    A(163, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#credentials-and-network"],
      user="password of redis service made by pskit is leaked, how i change it without lose data?",
      steps=[S("search_docs", query="change password one-click service keep data",
               docs=[D(SV, "credentials-and-network", start="To change a password later", end="then redeploy.")])],
      final="""Stop the service but keep its data, create it again with the same key and a new password, then redeploy [docs/resource-guides/onprem/services.md#credentials-and-network].

**In studio**
1. Open **Resources > On-prem services**, and on the Redis row click **Remove**, then *Stop service, keep data*.
2. Click **+ Create service**, pick Redis, use the **same key**, and enter the new password in **Security**.
3. **Save**, then **Deploy**.

**In the terminal**
```bash
pskit resources onprem remove jobs
export JOBS_REDIS_PASSWORD='<new password>'
pskit resources onprem create jobs --service redis --password-env JOBS_REDIS_PASSWORD --save
pskit deploy -s prod
```
`remove` without `--delete-data` keeps the volume, and creating it again with the same key reuses it. Redeploying ships the new password to the host in the env file."""),

    A(164, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SV}#web-uis"],
      user="is there a web page where i can look at the tables of my pskit postgres?",
      steps=[S("search_docs", query="web ui postgres adminer one-click",
               docs=[D(SV, "web-uis", end="pskit resources onprem tunnel orders-db --remote-port 8089")])],
      final="""Yes. pskit can start **Adminer** next to the database, on port 8089. You log in with the database user and password, and the server is filled in [docs/resource-guides/onprem/services.md#web-uis].

**In studio**
1. Open **Resources > On-prem services** and click **Details** on the database.
2. Click *Add web UI*. Its URL and login appear in *Details* and *How to use*.

**In the terminal**
```bash
pskit resources onprem gui orders-db
```
If the server's firewall blocks 8089, forward it and open `http://127.0.0.1:8089`:
```bash
pskit resources onprem tunnel orders-db --remote-port 8089
```"""),

    A(165, provider="onprem", stage="dev", mode="auto", page="Resources", persona="terse_expert",
      sources=[f"{SV}#web-uis"],
      user="azurite one-click: gui option?",
      steps=[S("search_docs", query="azurite web ui",
               docs=[D(SV, "web-uis", start="Azurite has no web UI")])],
      final="""No web UI for Azurite. Attach **Azure Storage Explorer** (desktop app) with the connection string from the env file [docs/resource-guides/onprem/services.md#web-uis].

```bash
pskit resources onprem usage <key> --reveal
```
That prints the connection values, with the secrets shown."""),

    A(166, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SV}#pskits-own-browsers-when-the-native-ui-is-missing"],
      user="The MinIO console pskit started doesn't have the admin pages anymore, so I can't set a bucket policy or turn on versioning there. Is there another way inside pskit?",
      steps=[S("search_docs", query="minio console missing admin pages browse buckets",
               docs=[D(SV, "pskits-own-browsers-when-the-native-ui-is-missing", end="reach the browser page.", words=420)])],
      final="""Yes. Use pskit's own **Buckets (S3)** browser. MinIO's community console no longer has the admin pages, so pskit ships this UI [docs/resource-guides/onprem/services.md#pskits-own-browsers-when-the-native-ui-is-missing].

**In studio**
1. Open **Resources > On-prem services**.
2. Click **Browse** on the MinIO row.
3. There you can turn bucket versioning on or off, and set the bucket policy (private, public read, or your own JSON). You can also upload, download, share links and work with old versions.

The studio talks to MinIO from your machine. If the port is closed, it goes over the server's SSH login. Credentials stay in `.pskit/onprem-services.json` and never reach the browser page."""),

    A(167, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{SV}#console-and-terminal"],
      user="terminal only: run one SELECT against the orders-db service and print the result",
      steps=[S("search_docs", query="console run sql command service",
               docs=[D(SV, "console-and-terminal", start="pskit resources onprem console cache", end="pskit resources onprem terminal --stop all")])],
      final="""**In the terminal**
```bash
pskit resources onprem console orders-db "SELECT count(*) FROM orders;"
```
It runs `psql` on the service's database with its login and prints the output. Without the quoted command you get an interactive `psql` [docs/resource-guides/onprem/services.md#console-and-terminal]."""),

    A(168, provider="onprem", stage="dev", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#console-and-terminal"],
      user="i want watch live redis-cli MONITOR from studio. console page only run one command. how?",
      steps=[S("search_docs", query="interactive terminal redis-cli monitor browser",
               docs=[D(SV, "console-and-terminal", start="For interactive work", end="through `docker exec`.")])],
      final="""Use a **Terminal** instead of the Console. It's a full terminal in the browser, embedded in the studio, for interactive work like `redis-cli MONITOR` [docs/resource-guides/onprem/services.md#console-and-terminal].

**In studio**
1. Open **Resources > On-prem services**.
2. Click **Terminal** on the Redis service. You get `redis-cli` through `docker exec`.
3. Type `MONITOR`.

**In the terminal**
```bash
pskit resources onprem terminal cache
```
The terminal is ttyd in Docker on your machine, on `127.0.0.1` only, behind a random secret URL. The first start builds a small image (`pskit-terminal:1`)."""),

    A(169, provider="onprem", stage="dev", mode="ask", page="YAML", persona="detailed_spec",
      sources=[f"{SV}#what-gets-written"],
      user="After `pskit resources onprem create jobs --service redis --attach worker --save`, what exactly changes in my project, and where does the Redis password go?",
      steps=[S("search_docs", query="what one-click create writes pskit.yml env file",
               docs=[D(SV, "what-gets-written", words=330)])],
      final="""[docs/resource-guides/onprem/services.md#what-gets-written]

**In code** (what `--save` writes)
```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem
resources:
  jobs:
    type: queue
    external: true
    options:
      driver: redis
      url_env: PSKIT_JOBS_URL
      key: jobs
functions:
  worker:
    events:
      - queue: {resource: jobs}
```
- The password is generated and goes into `.env.onprem` as `PSKIT_JOBS_URL` (and `PSKIT_<KEY>_PASSWORD` where there is one). The file is added to `.gitignore` when the project has one.
- `pskit deploy` copies that file next to the host as `host.env`. It never goes into Terraform state.
- What was created, with credentials, is kept in `.pskit/onprem-services.json`. Keep `.pskit/` out of git.
- `--save` rewrites pskit.yml and doesn't keep comments. Without `--save`, the command only prints the YAML to paste."""),

    A(170, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SV}#same-server-or-a-different-one"],
      user="Functions run on app-1. I want the Postgres on db-1, a different server. Does that work, and what address do the functions get?",
      steps=[S("search_docs", query="service on a different server than the functions address",
               docs=[D(SV, "same-server-or-a-different-one", end="| in a container (`method: docker`)")])],
      final="""Yes. The service is published on `0.0.0.0` of db-1, and the connection uses the SSH host of db-1. Open the database port from app-1 to db-1 in the firewall [docs/resource-guides/onprem/services.md#same-server-or-a-different-one].

**In the terminal**
```bash
pskit resources onprem create orders-db --service postgres --server db-1 --save
pskit firewall --server db-1
```
If app-1 reaches db-1 by another name or a private IP, set it with `--address`:
```bash
pskit resources onprem create orders-db --service postgres --server db-1 --address 198.51.100.21 --save
```

**In studio**
1. **Resources > On-prem services > + Create service**, PostgreSQL.
2. *Where*: pick db-1. Under *Advanced*, set *Address functions use* if needed.
3. **Create**, then **Save** and deploy."""),

    A(171, provider="onprem", stage="dev", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{SV}#same-server-or-a-different-one"],
      user="redis.exceptions.ConnectionError: Error 111 connecting to 127.0.0.1:6379. Connection refused.\n\nredis was made on this machine, functions use deploy method docker locally",
      steps=[S("search_docs", query="functions in docker container service on this machine address",
               docs=[D(SV, "same-server-or-a-different-one", start="| Functions run | Service created | Works because |", end="| in a container (`method: docker`)")])],
      final="""Inside the container, `127.0.0.1` is the container itself, not your machine. For functions in a container and a service on this machine, use *Address* `host.docker.internal` (Docker Desktop) or your machine's LAN IP [docs/resource-guides/onprem/services.md#same-server-or-a-different-one].

**In the terminal**
Create the service again with the same key and that address. Its data stays:
```bash
pskit resources onprem remove cache
pskit resources onprem create cache --service redis --role cache --address host.docker.internal --save
pskit deploy
```

**In studio**
1. **Resources > On-prem services**: **Remove** the service with *Stop service, keep data*.
2. **+ Create service** with the same key, and set *Advanced → Address functions use* to `host.docker.internal`.
3. **Save** and deploy again."""),

    A(172, provider="onprem", stage="prod", mode="auto", page="Resources", persona="terse_expert",
      sources=[f"{SV}#see-what-is-inside"],
      user="Resources > Data on my sqs-driver queue only shows a number. why no messages?",
      steps=[S("search_docs", query="data browser queue depth only sqs",
               docs=[D(SV, "see-what-is-inside", end="| custom class |")])],
      final="""That's expected. SQS / ElasticMQ, Azure queues, Pub/Sub, MNS and Cloudflare show **depth only**: they can't show a message without counting a delivery [docs/resource-guides/onprem/services.md#see-what-is-inside].

Built-in and directory queues, Redis lists and streams, and another pskit host's queues can be browsed message by message, oldest first."""),

    A(173, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SV}#removing"],
      user="in the studio, how do i delete the redis queue from my project but keep the redis container and its data running?",
      steps=[S("search_docs", query="delete resource one-click service keep container",
               docs=[D(SV, "removing")])],
      final="""**In studio**
1. Open **Resources**.
2. Click **Delete** on the `jobs` row.
3. Choose **pskit.yml only**. The resource leaves your project, and the Redis service keeps running with its data.
4. Click **Save**.

The other choices are **Stop service, keep data** and **Delete service and data** [docs/resource-guides/onprem/services.md#removing]."""),

    A(174, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SV}#monitoring-and-alerts"],
      user="For our replicated Postgres we want a Slack message when the disk passes 80 % or a replica falls more than 30 seconds behind. We don't keep the studio open. How?",
      steps=[S("search_docs", query="service alerts disk replica lag webhook cron",
               docs=[D(SV, "monitoring-and-alerts", start="**Alerts** (optional", end="pskit resources onprem monitor orders-db --watch 5")])],
      final="""Set alerts on the service and run the check from cron, since the studio only checks while it runs [docs/resource-guides/onprem/services.md#monitoring-and-alerts].

**In the terminal**
1. Configure the alert:
```bash
pskit resources onprem alerts orders-db --webhook https://hooks.slack.com/services/T000/B000/XXXX --disk 80 --lag 30
```
2. Send a test alert:
```bash
pskit resources onprem alerts orders-db --test
```
3. On an always-on machine with the project, run this every minute from cron:
```bash
pskit resources onprem alerts orders-db --check
```

**In studio**
Open **Resources > On-prem services**, click **Details** on `orders-db`, and set the alerts there.

An alert goes out at most once per cooldown (30 minutes by default). Keep the real webhook URL out of git."""),

    A(175, provider="onprem", stage="staging", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#start-a-database-with-data"],
      user="i have orders.sql dump from old server. can pskit load it when it make the new postgres?",
      steps=[S("search_docs", query="import dump create database one-click",
               docs=[D(SV, "start-a-database-with-data")])],
      final="""Yes. **Import data** loads a dump from your machine once the database is up. For PostgreSQL it takes `.sql`, `.sql.gz` or `.dump` (`pg_restore`) [docs/resource-guides/onprem/services.md#start-a-database-with-data].

**In the terminal**
```bash
pskit resources onprem create orders-db --service postgres --server db-1 --import ./backups/orders.sql --save
```

**In studio**
1. **Resources > On-prem services > + Create service**, PostgreSQL.
2. Choose the dump under *Import data* and click **Create**.

On a server the file is first copied there over SSH. For a replicated database it goes into the primary before the replicas start, so they copy it. A pskit backup works as is."""),

    A(176, provider="onprem", stage="prod", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{SV}#backups"],
      user="backup orders-db to /mnt/backup and how do I restore it later",
      steps=[S("search_docs", query="backup one-click postgres restore",
               docs=[D(SV, "backups", end="| MySQL / MariaDB |")])],
      final="""**In the terminal**
1. Back up into a folder of your choice:
```bash
pskit resources onprem backup orders-db --dir /mnt/backup
```
You get a `.sql` file (`pg_dumpall`).
2. Restore it [docs/resource-guides/onprem/services.md#backups]:
```bash
psql -U pskit -f file.sql postgres
```

**In studio**
1. **Resources > On-prem services**: click **Backup** on `orders-db`.
2. Choose *Save to folder*, then *Browse…*, and pick the folder. It's remembered.

The backup streams out of the container, also from an SSH server."""),

    A(177, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{SV}#troubleshooting"],
      user="service events did not become ready within 90 s\n(kafka, on a small vm with 1 cpu)",
      steps=[S("search_docs", query="did not become ready within 90 s kafka",
               docs=[D(SV, "troubleshooting", start="| `did not become ready within 90 s`", end="| `did not become ready within 90 s`")])],
      final="""On a small server Kafka needs about 1 GB of RAM. The message includes the container's last log lines, and this shows the rest [docs/resource-guides/onprem/services.md#troubleshooting]:
```bash
pskit resources onprem logs events
```
If memory is the problem, give the VM more RAM, or put Kafka on a bigger server:
```bash
pskit resources onprem create events --service kafka --server app-2 --attach worker --save
```
For a lighter queue, Redis or NATS JetStream also work as one-click queues."""),

    A(178, provider="onprem", stage="dev", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{SV}#troubleshooting"],
      user="minio container keeps restarting, docker logs says Permission denied on /data",
      steps=[S("search_docs", query="keeps restarting permission denied data directory",
               docs=[D(SV, "troubleshooting", start="| `keeps restarting`", end="| `keeps restarting`")])],
      final="""The data directory wasn't writable by the user the container runs as. Create the service again: pskit then chowns the directory (MinIO runs as 1001) [docs/resource-guides/onprem/services.md#troubleshooting].

```bash
pskit resources onprem remove files
pskit resources onprem create files --service minio --save
```
Use the same key, so the existing resource and triggers stay the same."""),

    A(179, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SV}#use-it-from-any-program"],
      user="a cron script on another machine needs to push jobs into the redis queue that pskit made. where do i get the code and the address?",
      steps=[S("search_docs", query="connect to service from any program script",
               docs=[D(SV, "use-it-from-any-program", words=330),
                     D(SV, "use-it-from-any-program", start="When the service's port is closed")])],
      final="""Use **How to use** on the service. It shows the address, the user, the variable names, and ready Python and Node.js code [docs/resource-guides/onprem/services.md#use-it-from-any-program]. For a Redis queue the Python code uses the `redis` library and `LPUSH`es the pskit envelope, so your worker's trigger receives it.

**In studio**
1. Open **Resources > On-prem services**.
2. Click **How to use** on the Redis service. Use *Show passwords* to see the values.

**In the terminal**
```bash
pskit resources onprem usage jobs --reveal
```

If the script can't reach the Redis port (a firewall), forward it with `pskit resources onprem tunnel jobs`, or use the pskit client, which goes through the host instead."""),

    A(180, provider="onprem", stage="dev", mode="auto", page="Resources", persona="informal_non_native",
      sources=[f"{SV}#one-click-services-for-on-premises-functions", "docs/resource-guides/onprem/custom.md#example-smtp-server"],
      user="i want test my notify function send email but not to real people. some fake mail server pskit have?",
      steps=[S("search_docs", query="fake smtp server test emails mailpit",
               docs=[D(SV, "one-click-services-for-on-premises-functions", start="| Mailpit (SMTP)", end="| Mailpit (SMTP)")]),
             S("search_docs", query="smtp custom resource connection",
               docs=[D("docs/resource-guides/onprem/custom.md", "example-smtp-server", end="functions: [notify]")])],
      final="""Yes, **Mailpit**. It's a one-click SMTP server on port 1025 with a mailbox web UI on 8025. It catches every mail, so nothing reaches real people [docs/resource-guides/onprem/services.md#one-click-services-for-on-premises-functions].

**In the terminal**
```bash
pskit resources onprem create mail --service mailpit --save
```

**In studio**
1. **Resources > On-prem services > + Create service**, pick Mailpit, click **Create** and **Save**.
2. Open its *Mailbox* from **Details** to read the mails.

It becomes a `custom` resource with connection values, so `notify` reads it with `resource("mail")` like any SMTP server [docs/resource-guides/onprem/custom.md#example-smtp-server]. Mailpit runs without authentication, so skip `smtp.login` for it and keep it on `127.0.0.1` or a private network."""),
]
