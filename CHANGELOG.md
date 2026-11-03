# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

> The function runtime is bundled into every deployment. After upgrading `py-serverless-kit`, run `pskit deploy` again to pick up runtime fixes.

## [Unreleased]

### Added
- **Structured end-to-end documentation** (about 125 new pages, every task both in studio and as terminal commands):
  `docs/guide/` (concepts and one full application built from the terminal, in studio, and on premises with a
  cluster, load balancer and replicated database), `docs/studio-guide/` (every studio page, button and dialog),
  `docs/functions/`, `docs/triggers/` (one page per trigger), `docs/deployment/` (deployment types, stages, deploy /
  remove, workflows, logs, monitoring, settings), `docs/onprem/` (servers, software, every catalog service, resources,
  cloud resources on premises, the AWS-compatible S3 and Secrets Manager servers in Python and Node.js, Swarm / k3s /
  Nomad scaling, load balancers, database replication, network map, firewall, placement) and `docs/providers/<cloud>/`.
- **Hana answers from the docs**: before the model answers, studio runs `search_docs` with the message and passes the
  3 best sections; a new system-message line (also in the training data) tells her to answer from them, cite them and
  say when the docs don't cover it. The search now covers every `docs/` section (`studio/hana/docs.jsonl.gz`, rebuilt
  with `python scripts/build_hana_docs_index.py`; a test fails when it is out of date).

### Changed
- The repository moved to https://github.com/kavion-ai/py-serverless-kit: project URLs, README links, the security
  advisory link, the `pskit.yml` header studio writes and the PyPI trusted-publisher settings now use it.
- The README and the docs index no longer link the PyPI release guides; they stay in `deploy_docs/`.

## [2.11.0] - 2026-11-02

### Added
- **Hana asks before she creates**: new functions can each be **their own app** (`functions/<name>/` with its own
  `requirements.txt`) or go into an existing module, and Hana asks which. A name that is already taken gets
  update / another name / skip (functions), replace / another name (resources), or a free name and a note
  (services, clusters, load balancers), instead of being skipped or renamed silently. "make step01 and step02
  separate apps" moves existing functions into their own apps and deletes the shared file once nothing uses it.
  Studio answers first when it has a card that changes the project, a short answer to studio's own question
  ("Which function should I remove?" → "step01, step02") is understood, and a model answer that claims a change
  with no file written is marked as such.
- **Hana runs terminal commands** (`run_command`): in the project folder or on a saved server over SSH, after you
  click **Run** on each command (also in Auto-approve); the output goes back to her and she answers from it.
  Commands that wipe or stop a machine are refused. The tool and a system-prompt rule are in the runtime prompt and
  the training data (`ai-agent/training/tools/task_common.py`); until the model is retrained, studio turns a
  command she writes in a code block into the same **Run** card when you asked for a result. Studio's answers from
  your real settings (servers, services, clusters, load balancers, functions) now come before the model's. The end
  of the system message tells her she has a terminal and names the saved servers. Studio proposes the command
  itself for "install docker on VM_01_2cpu" (any catalog runtime; part of a server's name is enough), "run
  `docker ps` on app-2", "execute pskit validate" and "can you execute it", and the model answers from the output.
- **Hana, the studio's AI assistant** (the avatar at the bottom right of every page, Ctrl+I): a floating chat.
  Hana answers pskit questions with how-to steps for studio, the terminal and code, and changes the project: she
  reads it, shows a plan to **Approve** / **Reject** (or runs it at once in *Auto-approve*), edits `pskit.yml`
  (backed up first) and handler files, and checks the result with `pskit validate` and a local invoke. She never
  deploys or removes. The model (1.5B, fine-tuned on pskit, by Asif Khan) runs locally: studio installs the
  `ak2311581/hana-pskit` Docker image on this machine or on a saved server (through an SSH tunnel), or connects to
  any OpenAI-compatible URL. Servers and on-prem services: from what you paste (IP, user, `.pem` path, `ssh`
  command) the chat fills in an **Add server** or **Create on-prem service** card, and studio runs it when you click.
  Chats are saved in `.pskit/studio/hana/`. See [docs/assistant.md](docs/assistant.md).
- `pskit studio --ailogs[=true]` (or `PSKIT_HANA_AILOGS=1`) prints every step of Hana's chats in the terminal:
  messages, model requests and answers, tool calls and results, plans and cards (passwords stay hidden).

## [2.10.0] - 2026-10-30

### Added
- On-prem **server usage**: the *Servers* list has a **Used in** column. For each saved server it lists every place
  that names it, with the functions behind each: the deploy target in `pskit.yml`, the stage last deployed there, a
  function group (`placement`), a cluster (master / joined server) and the cluster's load balancer, a named load
  balancer, a service or a replicated database member (primary, read replica, its load balancer), and installed
  software. Servers nothing names say *not used anywhere*. **Forget** shows the list before asking (and says when a
  cluster still holds the server). CLI: `pskit resources onprem servers usage [NAME] [--json]`.
- A **Network map** page in the studio sidebar: an SVG diagram of every server and the connections it accepts
  (inbound) and opens (outbound), with the port, why it is needed and whether it is required, needed for a feature
  or optional. Click a server for its inbound / outbound table and where it is used; filter by level and hide
  unused servers. Built from the same rules as `pskit firewall`, from local files only (no SSH).
- `GET /api/onprem-usage` and `GET /api/resource-bindings` in the studio API; new module `core/onprem_usage.py`.

### Fixed
- *Resources → Bound to* always said "all functions" for a resource without a `functions:` list. It now shows the
  functions that really use it: a trigger on it (⚡) or handler code that calls `resource("key")` / reads
  `PSKIT_RESOURCE_<KEY>_*`, plus how many functions get its variables. With `functions:` the listed ones show, the
  ones that use it highlighted.

## [2.9.0] - 2026-10-30

### Added
- On-prem **live monitoring**: a service's *Details* has a *Live monitoring* switch. While it is on, the studio shows
  every 5 seconds each container's CPU, memory and the disk holding its data (primary, replicas and load balancer of
  a replicated database), the open connections, the data size and each replica's lag. Nothing is measured while it
  is off. CLI: `pskit resources onprem monitor KEY [--watch N]`.
- **Alerts** for on-prem services (optional when creating a database, editable in *Details*): CPU, memory and disk
  percent, replica lag, a container down. They run a function of the project through the deployed host and / or
  POST a webhook (Slack, Teams, any URL), at most once per cooldown. *Create a new function* adds `<key>-alert` to
  `pskit.yml` with a handler stub. The studio checks every minute while it runs; `pskit resources onprem alerts KEY
  --check` does it from cron, `--test` sends a test alert, and the history is kept per service.
- **Import data** when creating a database: a `.sql`, `.sql.gz`, `.dump` (PostgreSQL) or `.archive` (MongoDB) file
  from this machine is loaded once it is up (into the primary before the replicas copy it). CLI `--import FILE`.
- **Servers**: a check mark per saved server (its SSH port is probed in parallel when the list opens, *Re-check*
  again) and a **Live** switch with CPU, RAM and disk use. CLI `pskit resources onprem servers check` and
  `servers top NAME [--watch N]`.
- **Backup** asks where to save: `.pskit/backups` or any folder picked on this machine (remembered). CLI `--dir`.
- A **⇅ Settings** button in the studio header imports and exports the project's `.pskit` settings, now optionally
  with `pskit.yml` (on by default there; CLI `pskit settings export --with-config`). An import that brings
  `pskit.yml` reloads the studio.

### Fixed
- `runtime_js/package.json` still said 2.7.0 in the 2.8.0 release; both version files now agree again.

## [2.8.0] - 2026-10-30

### Added
- On premises, a scaling cluster can be **removed together with what pskit installed**, master included:
  `pskit cluster remove NAME --uninstall` (studio: **Remove** on the master's row, which used to have no button)
  stops the deployments, removes the cluster's load balancer and its routes on named load balancers, uninstalls the
  agent from every joined server and then Docker Swarm / k3s / Nomad from the master, deletes the deployments'
  images and the `pskit-cluster` scripts folder, and forgets the cluster. Docker and the saved servers stay; the main
  replicas' data stays too unless `--delete-data` (*Uninstall and delete data*) is given. An unreachable server only
  warns. Plain `pskit cluster remove` still only forgets the cluster, and `pskit cluster leave` on the master now
  points to `--uninstall`.

## [2.7.0] - 2026-10-30

### Added
- On premises, a database is created on a **single server** or as a **primary with read replicas** (horizontal
  scaling): pick the server that takes the writes, the servers that serve reads, *asynchronous* or *synchronous*
  replication, and optionally a server for a load balancer that gives the functions one address. PostgreSQL uses
  streaming replication behind pgpool-II, MySQL and MariaDB use GTID replication (semi-synchronous for *sync*) behind
  ProxySQL, and MongoDB runs as a replica set (write concern `majority` for *sync*) that the driver routes itself.
  The studio's create form draws the topology (an SVG) as you pick, and **Details** shows each member's state and
  lag with **+ Add read replica** / **Remove**. CLI: `pskit resources onprem create KEY --service postgres
  --primary db1 --replica db2 --replica db3 --balancer lb1 --sync sync` and `pskit resources onprem replicas
  list | add | remove`. `.env.onprem` gets `PSKIT_<KEY>_WRITE_URL` and `PSKIT_<KEY>_READ_URLS` next to `URL`, and the
  job prints the firewall rules between the members. `--primary local --replica local` runs every member on this
  machine to try it out.

### Changed
- The studio no longer offers *Scaling cluster* as a place for a database; *Scaling → Primary + read replicas*
  replaces it (databases created on a cluster server before keep working).

## [2.6.1] - 2026-10-30

### Fixed
- On premises, a load balancer attached to one cluster also served the project's functions placed on other clusters
  and servers: attaching it turned the placement gateway on for every group, so the attached cluster's servers passed
  every other group's routes on. Now a group's servers pass on only the routes of groups behind the same load
  balancer (`options.balancer` and an explicit `placement.gateway` keep their behaviour). Run `pskit deploy` again.

## [2.6.0] - 2026-10-28

### Added
- Share links with a custom expiry: the S3 compatible server's console (`aws/s3/ui`) and the pskit studio's bucket
  browser take any time from 1 second to 7 days (seconds, minutes, hours or days) next to the presets, and show when
  the link expires. A time outside that range is refused with a clear message instead of being silently changed.
- The S3 console's *Block public access* card has a *Block all (make private)* button.

### Fixed
- Studio *Make private* left a bucket readable without keys: it only deleted the bucket policy, so objects uploaded
  with a `public-read` ACL (or a public bucket ACL) were still served, and the badge said "private". It now also
  resets the bucket ACL to `private` and turns on all four *block public access* settings, which ignore public
  object ACLs and policies; services without these APIs (MinIO) keep the policy-only behaviour. The badge reads
  "private (public access blocked)" once nothing is public. *Make public (read)* turns the block off first so the
  public policy is accepted.
- The S3 compatible server (Python) answered a non-numeric console share expiry with a server error; it is now a
  `400 InvalidArgument`.
- On premises, a load balancer sent every request of a Kubernetes (k3s) cluster to one server, while a Swarm cluster
  on the same load balancer was spread correctly. Two causes:
  - The load balancer reused its connections to the servers (`keepalive`), and a k3s node picks a pod once per
    connection (ServiceLB / kube-proxy), so every request stuck to the pod those few connections first reached.
    Routes to Kubernetes servers now open a new connection per request, so each one is balanced again. Swarm and
    Nomad routes keep reusing connections.
  - Kubernetes could put both web replicas on one server (its default lets up to 3 share one). Web pods now spread
    one per server first (`topologySpreadConstraints`, `maxSkew: 1`).

  Run `pskit deploy` again on the Kubernetes cluster (or `pskit lb sync <name>`) to rewrite its routes and spread
  its pods.

## [2.5.0] - 2026-10-28

### Fixed
- On premises, events stopped once the functions moved: after their server was removed, or they were deployed to
  another server or cluster, the services kept the address of the old place. Now every `pskit deploy` (CLI and
  studio) makes the services the functions use follow them:
  - **SMTP**: an `smtp` service sends each mail to the functions at the URL it was created with, so mail still
    arrived but no function ran (senders got `451` and kept retrying). After the deploy, every SMTP server the
    deployed functions have `smtp` triggers on is pointed at where they run now: its container starts again with
    the new URL (the installed packages stay in the volume), and mail the senders retry is delivered.
  - **Queues, streams, topics, buckets, databases, caches, secret stores**: a service on a cluster server was reached
    at its cluster address, which only works from that cluster. Before the deploy, pskit switches the address in the
    env file (and the services state) to the server's own address when the functions left the cluster, or back to
    the cluster address when they run on it, so the deploy ships the right one.
  - The deploy warns, naming the fix, when a service cannot be reached from the functions' new place: its server
    was removed, it runs on this machine or listens on `127.0.0.1` only, or its container has the address built in
    (Kafka, Redpanda, fake-gcs: create it again with the same key). It also prints the firewall rules the new
    function servers need to reach each service.
  - An address or `functions_url` typed in when creating a service is never changed. Services created before this
    release follow the functions when their address is one pskit picks. Run `pskit deploy` again to fix an existing
    project.

## [2.4.0] - 2026-10-28

### Added
- The AWS Secrets Manager compatible servers (`aws/secretsmanager`, Python and Node.js) encrypt secret values at
  rest with envelope encryption: each version gets its own data key, wrapped by a master key (`SM_MASTER_KEY`,
  more with `SM_MASTER_KEYS`, picked per secret by `KmsKeyId`). `SM_ENCRYPTION` chooses AES-256-GCM (default),
  ChaCha20-Poly1305 or AES-256-CBC + HMAC-SHA256. Clients (boto3, the AWS SDKs, the CLI, `get_secret()`) don't
  change. A plain data file is encrypted on the first start with a key; `SM_MASTER_KEY_ID` rotates the master key
  (rewraps the data keys on start, or with `--rewrap`). The Python server stays standard-library only.
- On premises, the `secretsmanager` / `secretsmanager-node` services generate a master key when created, keep it in
  the env file as `<PREFIX>_MASTER_KEY` and reuse it on re-create. Re-create an existing service to encrypt its data.

## [2.3.6] - 2026-10-28

### Fixed
- On premises, a project whose placement groups run on two scaling clusters (Swarm, Kubernetes / k3s or Nomad)
  attached to one load balancer got a route only to the first cluster: the second cluster's deployment
  (`pskit-<service>-<stage>-<group>`) was skipped as if the project had set its own route, and requests for its
  functions reached the first cluster's servers, which answered `404 ... runs on group X, not on this server`.
  Now the project gets one route, `/<service>/`, to the servers of every attached cluster that runs one of its
  groups (each on its own port), kept up to date on deploy, remove, join, leave, attach and detach. The same
  applies to a project's own `options.balancer` route.
- `placement.gateway` is now on by default when a group's cluster has a load balancer or is attached to one, and
  turns it on for **every** group (not only the default one): a server passes the routes of the other groups'
  functions on to them, so any server behind the load balancer answers every route. Run `pskit deploy` again.
- Studio, **Logs**: a stage on a scaling cluster, or split over placement groups, no longer shows a *Server* picker
  (it read as if the logs came from that one server). It shows the source instead, every replica of the cluster or
  every group and where it runs, and explains that a line's `group` / `node` fields say where it ran.
- Studio, **Deploy**: with placement whose default group has its own *Runs on*, the *Run on* picker at the top is
  replaced by a summary of each group and its target. Before, it showed a machine or cluster that could differ from
  the groups below, and deploying passed it as `--server` / `--cluster`, moving the default group there.
- Studio: the *One URL* (`placement.gateway`) checkbox says every group passes routes on and shows it on by default
  when a group's cluster is behind a load balancer.

## [2.3.5] - 2026-10-27

### Added
- On premises, scaling clusters have a **Master serves requests** switch (studio: *New cluster* form and the cluster
  page; CLI: `pskit cluster create ... --master-serves|--no-master-serves`, `pskit cluster set NAME
  --master-serves|--no-master-serves`). On, load balancers spread requests over every server, the master included.
  Off, the master is only a `backup` there, used while every other server is down, and Swarm / k3s keep web
  replicas off it while another server can run them. Before, a Nomad cluster's master stayed idle until every
  joined server was down. Defaults keep the old behaviour (off on Nomad, on on Swarm and k3s). Changing it updates
  the load balancers at once; Swarm / k3s web replicas follow at the next `pskit deploy`.
- On premises, a storage event can set both `resource` and `bucket`: the resource is the storage service (driver,
  endpoint, keys) and `bucket` is any bucket on it, e.g. `storage: {resource: minio, bucket: invoices}`. The studio's
  storage trigger form picks the *Storage service* and takes the bucket name. Cloud providers reject the combination.
- S3 presets `wasabi`, `b2` (Backblaze), `linode` (Akamai) and `scaleway`.

### Fixed
- S3-compatible storage: the driver follows a bucket that lives in another region (AWS's 301 / 400), falls back to
  ListObjects on stores without ListObjectsV2, uses path-style for dotted bucket names over HTTPS, and with
  `create_bucket` sends the region as `LocationConstraint` outside us-east-1 and accepts a bucket the keys may use
  but not create.

## [2.3.4] - 2026-10-27

### Fixed
- On premises, calling a workflow's first task function on its own did not run the workflow. A workflow such as
  `step01 -> step02 -> step3` now starts when `step01` runs from any trigger (its HTTP route, `invoke()`,
  `pskit trigger`, a schedule, a queue, ...). The run takes the call's input as the workflow input and `step01`'s
  result as the first state's result, so `step01` does not run twice. The run is tracked like any other execution,
  and an HTTP answer carries its id in `x-pskit-execution-id`. A failed call (an exception, or HTTP status >= 400)
  starts nothing. When placement puts the function on another group's server, the run still starts and runs on
  the default group. Set `options.start_on_entry: false` on a workflow to turn this off.

## [2.3.3] - 2026-10-27

### Fixed
- Workflows failed at a step whose function was created in the studio as an HTTP function: its stub read
  `event.http.query`, and a workflow step (or `invoke()`) has no HTTP request (`AttributeError: 'NoneType' object
  has no attribute 'query'`). New HTTP stubs also work as a workflow step or `invoke()` (`event.data` is the input).
- The studio's **Test** and `pskit trigger` sent the HTTP test of a function placed on another group to the
  default group's server, which answers only its own routes (404). It now goes to the server of the function's
  group.
- `pskit trigger --direct` and the studio's direct invoke on premises gave the function
  `{"__pskit": "invoke", "data": ...}` instead of the data.
- A function that raised during `pskit trigger --direct` was reported as `HostUnavailable ... answered HTTP 500`;
  it now says the function raised `<ErrorType>: <message>` and that the host is up.

## [2.3.2] - 2026-10-27

### Fixed
- Placement: a function's code was on every server. Functions whose handlers share a code file
  (`app/handlers.py`) each got the whole file on every group's server. Each group's copy now holds only its own
  functions' handlers (the others, and the imports only they used, are removed from that group's bundle; the
  source is not changed). `pskit_host.json` lists what was removed (`stripped`).
- Placement: every server answered every route by passing other groups' routes on, so
  `http://<any server>/items/1` worked. Each server now answers only the routes of the functions it runs, and a
  route of another group gets a `404` naming that group and its URL.

### Added
- `provider.options.placement.gateway: true`: the default group answers every route and passes other groups'
  routes on (one URL for the project). On by default with `options.balancer`, whose route now points at the
  default group only.
- The studio's "Where functions run": every function can be unticked (unticking in the default group moves it to a
  group you pick), All here / None buttons, and the default group is explained.

### Changed
- Requirements with placement are documented as global plus per function: each server installs the project's
  `requirements.txt` and those of its own functions' folders only.

## [2.3.1] - 2026-10-27

### Fixed
- Placement: a group other than the default one kept its data beside the server's `data_dir`
  (`/home/azureuser-test-02`), which the SSH user cannot create when `data_dir` is the home folder, so its host
  crashed at start-up ("on-prem host did not become healthy"). Groups now keep their data inside it
  (`<data_dir>/groups/<group>`).

### Added
- `pskit function split NAME... | --all [--dry-run]` (and the studio's **Own folder** action) moves a function
  out of a code file it shares with others into `functions/<name>/handler.py` with its own `requirements.txt`: the
  helpers and imports it uses are copied, relative imports made absolute, the project requirements its imports name
  copied, and its handler in `pskit.yml` updated (comments kept). Validation warns when functions of different
  placement groups share a code file.
- The studio's function editor picks the group a function runs on, or creates one (server, cluster or this
  machine, and port). On-prem deploys show their output as steps with one card per group host (its own lines, the
  error and the host's log), then the load balancer, firewall rules and endpoints. The raw log stays one tab away.
- dashboard-ui unit tests (`npm test`: deploy log parser, placement edits), run in CI.

### Changed
- A host that fails at start-up fails the deploy as soon as it exits (not after 30 s), and the deploy output shows
  the end of its `host.log`.

## [2.3.0] - 2026-10-27

### Added
- **Six load balancing algorithms** on premises: round robin, sticky round robin (cookie), weighted round robin,
  IP hash (static) and least connections, least time (dynamic). Load balancers now run OpenResty, which provides
  sticky sessions (a hashed first-request cookie) and least time (`balancer_by_lua` with a moving average of each
  server's response time) that open-source nginx lacks. `pskit lb algorithms` and the studio explain each one, with
  pros, cons and an animation. Upstreams share state across worker processes (`zone`), so round robin and least
  connections are exact.
- **Named load balancers shared by projects and clusters**: `pskit lb create edge --server lb1`, then
  `provider.options.balancer: edge` in any project (`http://lb1/<service>/`, or `{name, path, algorithm, weights}`)
  or `pskit lb attach edge --cluster prod`. Routes are kept on the load balancer server, so projects in other
  folders or on other machines share it without overwriting each other (`flock`, `nginx -t` before every reload).
  New studio page **Load balancers**. See `docs/load-balancers.md`.
- **Placement**: `provider.options.placement` runs groups of functions on different servers, clusters or this
  machine. Each group is its own host with only its functions; `invoke()`, HTTP routes, workflow steps, built-in
  queues, buckets, topics and SMTP triggers reach the group that owns them, workflows run on the default group and
  every group's logs reach it. See `docs/placement.md`.
- **Function sub-projects**: a function in its own folder with its own `requirements.txt` / `package.json`
  (`functions/<name>/`). Its requirements go into the bundle on every cloud; with placement each server installs
  only those of its functions. Node.js sub-projects get their own `node_modules`. The studio creates new functions
  this way.
- `pskit cluster balancer set` takes `--algorithm` and `--weight SERVER=N`.
- **Firewall rules, live**: every on-prem step (cluster create / join, deploy, `pskit lb create` / `attach`, a
  project's load balancer route, `pskit resources onprem create`) prints the inbound / outbound ports it needs on
  each server, by name and address, with `ufw` commands. `pskit firewall` (and the studio's Firewall panel) lists
  them for the whole project. Every role and port: `docs/onprem-network.md`.

### Changed
- A cluster's own load balancer runs `openresty/openresty:1.27.1.2-alpine` instead of `nginx:1.27-alpine`; it is
  replaced on its next update (deploy, join, leave or `pskit cluster balancer sync`).

### Fixed
- The generated `onprem_ctl.py` swaps `staging` into `app` with extended paths on Windows, so a redeploy no longer
  fails on deep vendored paths (260-character limit).

## [2.2.1] - 2026-10-26

### Fixed
- **TypeScript 7**: the generated `tsconfig.pskit.json`, the `pskit init` template and `examples/21-nodejs-typescript`
  no longer set `baseUrl` or `moduleResolution: "node"`, which TypeScript 7 removed (`TS5102`, `TS5108`, `TS5090`).
- **On-premises scripts** add `/usr/local/bin`, `/usr/bin` and the other system dirs *after* the server's `PATH`
  instead of before it, so a `docker` (or other tool) the server's `PATH` chooses is no longer overridden.
- **Workflow timeouts**: a `wait` cut short by the workflow's `timeout` could wake a moment before the deadline
  (timers fire early) and then finish the wait instead of failing with `States.Timeout`. The Node.js and Python
  engines now keep waiting until the end has really passed.
- **Swarm join** counts the other nodes and services without the padding BSD `wc` adds, so the "manages another
  swarm" message shows plain numbers.
- **CI**: `pytest-timeout` (dev dependency) fails a hung test after 5 minutes with its stack trace, and test jobs
  stop after 30 minutes.
- **CI**: the macOS tests run weekly and from the "Run workflow" button instead of on every push / PR (macOS
  runners are often queued), and a new push cancels the older run of the same branch.

## [2.2.0] - 2026-10-26

### Added
- **Amazon S3 compatible server** in `aws/s3`, in Python (standard library only) and Node.js (no npm packages), with
  a Dockerfile for each, a `docker-compose.yml` and one shared web console (`ui/index.html`, served at `/ui/`).
  boto3, the AWS SDKs, the AWS CLI (`aws s3` and `s3api`), rclone, s3cmd and pskit's `s3` driver work unchanged
  through the endpoint. Every request is checked with AWS Signature Version 4 (header, presigned URLs,
  `aws-chunked` streaming uploads with chunk and trailer signatures, browser POST policies) or Version 2.
- Buckets: create / delete / head / list (paging), location, versioning (Enabled / Suspended, `null` versions,
  delete markers), tags, bucket policies (statements for `Principal: "*"` decide what unsigned requests may do),
  canned and grant ACLs, block public access, ownership controls, policy status, CORS (applied to preflight and
  responses), lifecycle rules (applied every hour: expiration by days or date, noncurrent versions, expired delete
  markers, incomplete multipart uploads, transitions), static website hosting (`/-/website/<bucket>/` and
  `<bucket>.s3-website.<domain>`: index and error documents, redirects, routing rules), object lock (default
  retention, GOVERNANCE / COMPLIANCE, legal hold), default encryption; logging, notification, replication,
  accelerate, request payment, metrics, analytics, inventory and intelligent-tiering configurations are stored.
- Objects: put / get / head / delete / copy (metadata and tagging directives), ranges, part numbers, conditional
  reads and writes, user metadata and standard headers, `response-*` overrides, tags, ACLs, storage classes
  (archive classes need RestoreObject), checksums CRC32, CRC32C, CRC64NVME, SHA1, SHA256 and `Content-MD5`,
  DeleteObjects, GetObjectAttributes, ListObjects / ListObjectsV2 / ListObjectVersions (delimiters, markers,
  `encoding-type=url`), multipart uploads (UploadPartCopy, ListParts, ListMultipartUploads, composite and
  full-object checksums), path-style and virtual-hosted requests. Not supported: S3 Select, torrents, directory
  buckets; SSE headers are returned but objects are not encrypted at rest.
- Both servers keep the same data layout (one JSON record per key, one file per version, atomic writes, mode
  600), so they are interchangeable on one volume.
- Console: sign in with an access key and its secret key (or `S3_UI_PASSWORD`); buckets with every setting, folder
  browsing and search, drag-and-drop upload of files and folders with progress, downloads, previews, share links
  (presigned GET / PUT), copy / move / rename, delete, versions (download, delete, make current, show deleted),
  metadata, tags, ACLs, object lock, unfinished uploads, *Run lifecycle now*. HttpOnly SameSite=Strict session,
  per-session request token, lock-out after 10 failed sign-ins, strict CSP.
- **On-prem services `s3` (Python) and `s3-node` (Node.js)**, under *Object storage*: the stock
  `python:3.12-alpine` / `node:22-alpine` image gets the server and the console with `docker create` + `docker cp`
  (scp first on SSH servers) + `docker start`, so nothing is built or pushed. User = access key ID, password =
  secret key. The resource is a `storage` bucket on the `s3` driver (storage triggers work); the env file gets
  `PSKIT_<KEY>_URL`, `_ACCESS_KEY` and `_SECRET_KEY`. Port 9000, data volume and *Backup*, *Web UI → S3 console*,
  *Browse → Buckets (S3)*, an `aws s3` console and a *How to use* page (boto3, AWS SDK for JavaScript, AWS CLI).

## [2.1.0] - 2026-10-26

### Added
- **Move a project's local settings to another machine**: `pskit settings export [-o FILE]` and
  `pskit settings import FILE [--dry-run] [--replace] [--yes]`, and in the studio *Setup & credentials → Move
  settings to another machine* (export with a passphrase and download; pick a file, preview, import). `.pskit`
  stays out of git; the file carries what a fresh clone lacks: saved servers, scaling clusters with their load
  balancers, on-prem services with their passwords and tokens, SSH passwords, the SSH key files the servers use
  (also from `~/.ssh`, written to `.pskit/ssh/keys/` on import), where each on-prem stage was last deployed (so
  logs, test and info work at once), the studio's test events, and env files named by `env_file` in `pskit.yml`.
  Paths inside the project are stored relative to it, so the project can live in another folder or OS.
- The file is always encrypted with a passphrase (at least 8 characters): scrypt key derivation, HMAC-SHA256
  counter-mode encryption and an HMAC-SHA256 tag (encrypt-then-MAC), standard library only. A wrong passphrase,
  a changed file or a path that would leave the project is refused before anything is written.
- Import merges saved servers, clusters and services by name (the file's entries win, others stay); `--replace`
  drops local entries the file lacks. The current settings are backed up to `.pskit/backups/settings-<time>.json`
  first. Terraform state is not included. `PSKIT_SETTINGS_PASSPHRASE` skips the prompt in scripts.
- Studio API: `POST /api/settings-bundle/export`, `/preview` and `/import`.

## [2.0.0] - 2026-10-26

### Added
- **Load balancer for scaling clusters** (Swarm, k3s and Nomad): `pskit cluster balancer set NAME SERVER [--port 80]`
  runs nginx in Docker (`pskit-lb`) on a saved server outside the cluster and spreads each deployment's HTTP over
  the cluster's servers (fewest connections, failed servers rest 10 s, retries on another server). On Nomad the
  web replicas share the requests and the master's main replica is only a backup. `pskit deploy`, `pskit remove`,
  `cluster join` and `cluster leave` update it: a leaving server and a removed deployment come off it before they
  stop. Every change passes `nginx -t` first and reloads without dropping connections; an offline load balancer
  only warns (`pskit cluster balancer sync NAME` catches up). `cluster balancer logs` shows one line per request
  with the server that answered; `cluster status` and `cluster list` show it and each deployment's URL. Logs,
  tests and the admin API keep using the master. `options.cluster.balancer_port` gives a second deployment on the
  same cluster its own port. Studio API: `POST /api/onprem-clusters/NAME/balancer-set|balancer-sync|balancer-remove`
  and `GET .../balancer-logs`.
- **Studio: Load balancer card** on the *Scaling cluster* page: set it up (pick or add a server, port, address),
  move it to another server, *Sync now*, *Remove*, nginx state and the server's CPU / memory / disk, each
  deployment's public URL, and the access log. *Deployed functions* shows the public URL above the master's
  address, *Live requests* marks which servers share requests and which is the backup, and the project's cluster
  settings get *Port on the load balancer* (`options.cluster.balancer_port`). A load balancer server is no longer
  offered as a master or joined server.

## [1.11.0] - 2026-10-26

### Added
- **AWS Secrets Manager compatible server** in `aws/secretsmanager`, in Python (`python/server.py`, standard library
  only) and Node.js (`nodejs/server.js`, no npm packages), with a Dockerfile for each and a `docker-compose.yml`.
  boto3, the AWS SDKs, the AWS CLI and `get_secret()` / `getSecret()` work with it unchanged through
  `endpoint_url`. Every request is checked with AWS Signature Version 4 (wrong secret key, unknown access key and
  requests older than 15 minutes are refused). It supports CreateSecret, GetSecretValue, BatchGetSecretValue,
  PutSecretValue, UpdateSecret, DescribeSecret, ListSecrets (filters, paging), DeleteSecret (recovery window or
  force), RestoreSecret, ListSecretVersionIds, UpdateSecretVersionStage (AWSCURRENT / AWSPREVIOUS), tags,
  GetRandomPassword and resource policies (stored). Rotation and replica regions are not supported. Both servers
  keep the same JSON data file (mode 600, written atomically), so they are interchangeable.
- **Its own web console** at `/ui/` (`aws/secretsmanager/ui/index.html`), signed in with the access key ID and
  secret key (or `SM_UI_PASSWORD`): list and filter, create (key/value or plaintext, generate a password), show and
  copy values, new versions, make an old version current, description and tags, delete with a recovery window,
  restore. HttpOnly `SameSite=Strict` session cookie, a per-session request token, a lock-out after ten failed
  sign-ins and a strict Content-Security-Policy.
- **On-prem services `secretsmanager` (Python) and `secretsmanager-node` (Node.js)** under *Secret managers*
  (`pskit resources onprem create secrets --service secretsmanager --user AKIAPROD`). They run on the stock
  `python:3.12-alpine` / `node:22-alpine` image: pskit copies the server and the console into the container with
  `docker cp` (with scp first on an SSH server), so nothing is built or pushed. The user is the access key ID and
  the password the secret key; the env file gets `PSKIT_<KEY>_DRIVER=aws`, `_URL`, `_REGION`, `_ACCESS_KEY` and
  `_SECRET_KEY`. Port 4584, data volume and *Backup*, *Web UI → Secrets console*, pskit's *Browse secrets*, an AWS
  CLI console and a *How to use* page with boto3, AWS SDK for JavaScript v3, AWS CLI and `get_secret()` examples.
  The wheel ships the `aws/` folder as `py_serverless_kit/aws`.

## [1.10.5] - 2026-10-24

### Fixed
- **MinIO and RustFS did not become ready** (`did not become ready within 90 s`). The data directory on the server
  is created as the SSH user, and these images run as their own user (MinIO uid 1001, RustFS uid 10001), so the
  process cannot write it and exits with `Permission denied`. pskit now gives that directory to the container user
  before start (other images that do not run as root get the same, from the image's user). A container that keeps
  restarting fails at once and the error includes its last log lines. On an SSH server, an HTTP readiness check
  runs on the server (`127.0.0.1`), so a firewall in front of the service port is not reported as a failed start.

## [1.10.4] - 2026-10-24

### Added
- **Live balance for one deployment**: `pskit cluster requests NAME --follow` and the studio cluster page's
  *Live requests* card list every server, its URL, whether that URL is the main replica or a web replica, and
  its share of HTTP. Servers with no traffic yet are included. Swarm and k3s spread HTTP from any server's
  port. On Nomad the master's URL is the main replica and each other server's URL is one web replica.
- **Live logs for a cluster deployment**: `pskit logs -f`, the studio **Logs** view and the cluster page's
  *Live logs* card follow a cluster the same way they follow one machine. On Nomad each server is read
  directly, so a web replica's lines show together with the main replica.

### Fixed
- **Nomad cluster deploy failed after the job was accepted** (`pskit: no answer on
  http://127.0.0.1:8080/__pskit/health`). The job asked Nomad for host networking, but Docker stayed on its own
  bridge, so the functions' port never opened on the server's loopback. The task now uses Docker host networking
  and binds that port on the server. The previous job is stopped first so the port is free. While the deploy
  waits it prints each allocation and the main replica's logs every 10 seconds, and that output is shown as it
  happens. Nomad does not load-balance: the master's port is the main replica, and each other server answers on
  the same port. A load balancer is optional.

## [1.10.3] - 2026-10-24

### Fixed
- **Cluster deploys copied the image several times and could fail after it had loaded** (`copy interrupted
  (command failed (1): Loaded image: ...)`). When no older copy of the image was left on the server, the cleanup at
  the end of the load script exited 1, even though the image was already loaded. The script now exits 0 once
  the image is loaded. Before each retry pskit also checks whether the server already has the image, and stops
  copying if it does.
- **Creating an SMTP server when the functions are not set in pskit.yml** (`the functions run on this machine,
  which the SMTP server cannot reach`). The functions' address now comes from where the stage was last deployed
  (`pskit deploy --cluster` / `--server`, or the studio's machine picker) when pskit.yml names no target. If the
  functions are not deployed anywhere yet, an SMTP server on a node of a scaling cluster sends mail to that
  cluster. On Swarm it uses `127.0.0.1` (Swarm publishes the port on every node); on k3s and Nomad it uses the
  master's cluster address. In any other case the error now says that the functions need to be deployed first.

## [1.10.2] - 2026-10-24

### Fixed
- **Copying the function image to cluster servers**: a dropped connection (`scp: Couldn't send packet: Broken
  pipe`) no longer fails the whole deploy. The image is gzip-compressed, often to a third of its size or less,
  and sent in 16 MB parts with checksums. Each retry sends only the parts that are missing, up to 6 attempts with
  growing pauses, and parts already copied stay on the server, so the next `pskit deploy` resumes the copy. The
  joined image is checked against its checksum before it is loaded, and a damaged copy is sent again. Progress is
  shown per server. Only a failure on the master stops the deploy; a worker that fails gets a warning instead.
- **A saved server that was removed or renamed** (pskit.yml still saying `deploy.server: VM_01` after it became
  `VM_01_2cpu`):
  - The studio's *Create service* dialog no longer pre-selects a server that is not saved. Before, the picker
    showed *New connection…* but the request still sent the old name. The dialog now explains what is wrong.
  - Every *"no saved SSH server"* error says where the name came from (pskit.yml, the last deploy) and suggests
    close matches (*Did you mean VM_01_2cpu or VM_01_4cpu?*).
  - Creating an SMTP server with a stale functions server suggests `functions_url`.
  - `pskit resources onprem servers remove` (and the studio's *Forget*) refuses a server that is still in a
    cluster, and warns when pskit.yml or a created resource still names it.

## [1.10.1] - 2026-10-24

### Fixed
- **Re-adding a server to a cluster**: `pskit cluster join` no longer fails with *"This node is already part of a
  swarm"*. A server that a failed join left in `pending`/`error`, that was removed while it was off, or that belongs
  to a swarm that was set up again now leaves the old swarm and joins. It is skipped if it is already a member,
  checked by node id instead of by manager address, which used to break when the master had both public and
  private IPs. Pskit still refuses to take over a server that manages another swarm with nodes or services, or
  whose swarm is locked. Older *down* entries for the same host are removed from the master after the rejoin. The
  swarm master setup also recovers from a half-joined state. Kubernetes (k3s) agents are reinstalled when they
  point at a different master or token, and a server running its own k3s server is refused with a clear message.
## [1.10.0] - 2026-10-24

### Added
- **Live requests on a cluster**: the cluster page's *Live requests* card and `pskit cluster requests NAME --follow`
  show each request as it happens with the server and replica that handled it (plus requests per server). The
  studio polls every 2 s only while the card is on screen and the tab is visible. Replicas get `PSKIT_NODE` from
  the orchestrator (Swarm, k3s, Nomad); the host serves `GET /__pskit/requests?since=N`.
- **Saved servers: home path, bind address, data directory** (studio *Add a server*, `servers add --home --bind
  --data-dir`). Defaults for what runs there: functions deploy to `<home>/<service>-<stage>`, listen on the bind
  address and keep data in the data directory; services publish their port on the bind address and keep data in
  `<data>/<container>` (bind mount); a cluster keeps its files in `<home>/pskit-cluster`, uses a specific bind IP
  as the server's cluster address, and keeps the main replica's data in `<data>/<stack>` on the master.

### Changed
- The *New scaling cluster* dialog: the name field is labelled *Cluster name*, focused, always pre-filled with a
  free name (`prod`, `prod-2`, ...) and lower-cased as you type.

## [1.9.0] - 2026-10-24

### Added
- **One server or a scaling cluster, per deploy**: `pskit deploy | package | plan | remove | info --cluster NAME`, and
  in the studio *Deploy → Run on: One machine / Scaling cluster*. The stage remembers the cluster of its last deploy
  like a server (`deployed on: cluster prod (master edge1 (...))`); `--server NAME` moves it back to one machine.
- **Resources on a cluster**: `pskit resources onprem create KEY --service S --cluster NAME [--node SERVER]`, and
  *Where → Scaling cluster* in the studio's create form. Without `--node` the reachable server with the most free
  memory under every capacity limit runs it (a full cluster refuses, asking for another server); its env values use
  that server's cluster address. With `options.cluster` in pskit.yml new resources default to the cluster.
  `pskit cluster status` and the studio's cluster page list them per server; a server that leaves keeps them as
  one-server resources.

### Changed
- `--server NAME` now wins over `options.cluster` in pskit.yml (deploys to that one machine); before, the cluster
  always won.

## [1.8.0] - 2026-10-24

### Added
- **Scaling clusters for on-prem functions** ([docs/cluster.md](docs/cluster.md)): a master server plus joined servers
  run by **Docker Swarm**, **Kubernetes (k3s)** or **HashiCorp Nomad**, all installed and driven over SSH from saved
  servers. `pskit cluster create | join | leave | status | check | watch | alerts | scale | list | remove`, and a new
  studio page **Scaling cluster**: create a cluster, join servers (also while functions run, adding a new saved server
  in the same dialog), see every server's CPU / memory / disk against the limits, replicas running / desired and
  replicas that cannot be placed, scale, drain and remove servers.
- `provider.options.cluster` (`cluster: prod` or `{name, replicas, cpu, memory}`) deploys the functions to a cluster:
  the image is built on this machine, copied to every server (no registry), and deployed as one `main` replica on the
  master (schedules, built-in queues / topics / buckets, workflow executions, logs, the data volume) plus `replicas`
  `web` replicas behind the orchestrator's load balancer (HTTP routes and `invoke()`). Joining a server copies the
  deployed images to it and does not redeploy. Without `options.cluster` nothing changes: the host runs on one server.
- Capacity alerts: when every server is over a limit (default CPU 85 %, memory 85 %, disk 90 %), replicas cannot be
  placed, or no server is ready, pskit calls a function of yours (`event.data.type = "pskit.cluster.capacity"`, e.g. to
  mail DevOps) and / or POSTs a webhook (Slack / Teams `text` included), once per cooldown. Checks run in the studio
  (*Watch while the studio runs*) or with `pskit cluster watch` / `pskit cluster check` (exit 3 when full).
- Host roles for cluster replicas (`PSKIT_HOST_ROLE=main|web`, `PSKIT_MAIN_URL`): a web replica forwards built-in
  queue / topic / bucket calls, workflow starts and `/__pskit/*` admin calls to the main replica (retrying for a few
  seconds while it restarts), and ships its log entries (tagged `replica`) and invocation counts to it every second.
  `GET /__pskit/health` reports `role` and `replica`. A host without a role behaves as before.

## [1.7.0] - 2026-10-23

### Changed
- **E-mail triggers are now one on-prem service.** *Resources → **+ SMTP server*** (or *On-prem services → Mail*)
  starts a Node.js SMTP server (nodemailer's `smtp-server` + `mailparser`, `node:22-alpine`) on any server for the
  domains you list, and ticks the functions to run. Each mail is posted to the host (`POST /__pskit/smtp/<key>`),
  which runs every function with `- smtp: {resource: <key>}`. When one fails, or none is attached, the sender gets
  `451` and retries. Mail for other domains is refused (never a relay). On an SSH server it uses the host network, so
  a host bound to 127.0.0.1 works.
- `event.data` of an `smtp` event: `from`, `from_name`, `to`, `cc`, `bcc`, `reply_to`, `subject`, `date`, `text`,
  `html`, `headers`, `attachments` (base64 `content`), `envelope`, plus the Amazon SES receipt event (`Records[0].ses`)
  and the raw message (`content`, base64), so code written for SES reads it unchanged.
- **DNS guide** on the SMTP service (also *How to use* and `pskit resources onprem create --service smtp`): the A and
  MX records with your values, provider notes (Cloudflare grey cloud, keep the root domain's MX), port 25 and tests.
- `pskit resources onprem create`: `--domains`, `--functions-url`, `--max-size-mb`.

### Removed
- The host's built-in SMTP server and everything around it: `type: smtp` resource options (`domains`, `port`, `auth`,
  `users`, TLS, allow-lists, `verify_senders`, `block_spoofed`), the `recipients` / `subdomains` trigger filters,
  SPF / DKIM / DMARC checks, the Mailbox and `/__pskit/mail`, the *Mail domain* setup wizard (`/api/mail-setup`,
  `/api/mail-handler-stub`, `/api/resource-mail`, `/api/env-file`). Recreate an SMTP server as the on-prem service.

## [1.6.0] - 2026-10-23

### Added
- **Receive mail for your domain in a few steps.** Studio *Resources → **+ Mail domain (SMTP)*** looks up the
  domain's current mail (Microsoft 365, Google Workspace ...) and suggests a subdomain such as `inbound.kavion.ai`, with a
  warning before moving the domain's own MX. You pick the machine (its IP), the mail server name, the port and the
  security, tick the functions to run (or create `on-mail` with a ready handler file in Python or Node.js), and pskit
  adds the `smtp` resource and triggers. It then lists the **DNS records** to add at the domain provider: A for the
  mail server, MX, wildcard MX for subdomains, and SPF `-all` / DMARC `p=reject` for a receive-only domain. It
  explains why receiving needs no DKIM record. **Check DNS** shows each record live / missing / different / keep
  (DNS over HTTPS, plain DNS fallback), and an optional port 25 check. **DNS setup** on an smtp resource reopens it.
  Backend: `core/mail_setup.py`, `POST /api/mail-setup`, `/api/mail-handler-stub`.
- **SPF, DKIM and DMARC checks of received mail** (`runtime/mail_auth.py`, stdlib only: its own DNS client, RSA
  verification). Results are in `event.data["authentication"]`, the logs and the Mailbox. `block_spoofed: true`
  stops mail whose DMARC fails with `p=quarantine / reject`, or that claims to come from the server's own domain
  without passing SPF or DKIM (status *blocked*). The `verify_senders` option turns the checks off. DKIM
  verification is tested against signatures made by dkimpy (simple and relaxed, sha256 and sha1), and SPF against
  live records.

## [1.5.0] - 2026-10-23

### Added
- **E-mail (SMTP) triggers on premises.** A resource of `type: smtp` makes the host run an SMTP server for your domains (`options.domains`, subdomains on by default, port 2525, `max_size_mb`). Functions get `- smtp: {resource: inbound-mail, subdomains: [support], recipients: ["*@support.example.com"]}`. The handler receives `event.data` with `from`, `recipient` / `recipients` split into local part, **subdomain** and domain, `to` / `cc`, subject, text, html, headers and attachments (base64). Mail is stored before `250` is answered and delivered after a restart. Every message is logged with its sender, recipients, subdomain, subject, files and a body preview, plus structured fields. The server is never an open relay. Options: SMTP **AUTH on / off** with users whose passwords live in the env file (`password_env`), STARTTLS (`tls_cert` / `tls_key`, `require_tls`), `allowed_senders` and `allowed_ips`. Mail admin API `/__pskit/mail`; `pskit trigger` and `pskit invoke -t smtp` send test mail. Studio: an *E-mail (SMTP)* trigger form, an SMTP server form (domains, password on/off, users, generate and save passwords, TLS, allow-lists) and a **Mailbox** (paged list with subdomain and domain, details, attachments, `.eml`, run functions again, delete, send a test mail). Other providers reject `smtp` triggers when you validate. Guide with DNS (MX, A, wildcard MX for subdomains), port 25, cloud firewalls, TLS, testing and the architecture: `docs/smtp/README.md`.
- **pskit's own service browsers** where the native UI is missing or limited (*Browse* on a service row). **S3** (MinIO, RustFS, LocalStack, LocalEmu): buckets, folders, paginated listings, filter, multi-file upload, download, info and metadata, old versions, rename / copy, presigned share links, versioning and bucket policies (private / public read / JSON). **Cloud Storage** (fake-gcs-server). **Secrets** for OpenBao (folders, versions, add / edit / delete); its release images have no web UI, which the *"OpenBao UI is not available in this binary"* page meant. Also **Secrets Manager** for LocalStack and LocalEmu. A closed service port is reached over the server's SSH login.
- **More one-click services**: LocalEmu (AWS emulator), Infisical (secrets manager with its own PostgreSQL and Redis as sidecars; generated `ENCRYPTION_KEY` / `AUTH_SECRET` kept in the env file and reused when it is created again), Grafana, Prometheus, Uptime Kuma, Jaeger, Keycloak, Meilisearch, Typesense, Qdrant, ClickHouse, Neo4j, Eclipse Mosquitto, n8n, Portainer, Gitea and Nginx Proxy Manager. The catalog is grouped (queues, Redis-compatible, object storage, databases, secrets, AWS emulators, monitoring, identity and search, automation and tools). Services are described by data (`sidecars`, `generate`, `connect` templates) in the new `core/onprem_apps.py`.
- **`infisical` secrets driver** for `get_secret()` / `put_secret()` in Python and `getSecret()` / `putSecret()` in Node.js (machine identity with Universal Auth, or a token; project, environment, path).
- **Pick the Python version** when installing Python on a server: `system` (the distribution's) or 3.9 to 3.14 as a standalone CPython (through uv, any distribution) linked as `python3.X`. Node.js adds 24.

### Fixed
- Command logs mask every `*KEY*` value (`ENCRYPTION_KEY`, API keys), not only passwords, secrets and tokens.

## [1.4.0] - 2026-10-23

### Fixed
- **Studio: Overview edits no longer lose to a stale `providers.<cloud>` copy.** Switching providers parked the old provider's options under `providers.<cloud>:`; switching back copied them to `provider:` but kept the parked block. That block is merged over `provider:` when deploying, so for example *On-premises options → Bind address 0.0.0.0* kept deploying `127.0.0.1` and a picked server kept `deploy.method: local`. Switching back now moves the parked settings into `provider:`. Editing any `provider.*` setting also removes the same setting from the active provider's `providers.<cloud>` block.

### Added
- **Overview warns about provider settings overridden under `providers.<active cloud>`** and offers **Use the values shown here**. This moves them under `provider:`: the values shown in Overview win, and settings only the override has are kept. Function / workflow overrides and other clouds' blocks are left alone.
- **`pskit validate` / `deploy` warn** when `providers.<cloud>` overrides a different value set under `provider:` for that same cloud (`[providers.onprem.options.host] providers.onprem sets options.host to '127.0.0.1', which overrides '0.0.0.0' ...`).

## [1.3.10] - 2026-10-23

### Fixed
- **On premises: a chosen server really deploys there.** With `deploy: {method: local}` in `pskit.yml` (what a new project writes), `pskit deploy --server NAME` and studio *Deploy → Machine* kept `method: local`, so the host started on this machine and was labelled `VM_01 (this machine)`. A saved server now always deploys over SSH (`docker` stays `docker`). `method: local` on its own no longer overrides the server a stage was last deployed to; `--server local` still picks this machine.

### Added
- **Studio Overview → On-premises deployment: Saved server.** Pick one of the servers saved under *Resources → On-prem services → Servers* (writes `provider.options.deploy.server` and switches the method to SSH), or **+ Add server** to save a new one from there. Shows where the stage is deployed now.

## [1.3.9] - 2026-10-23

### Fixed
- **On premises: commands go to the host the stage was deployed to.** A deploy remembers its machine (`.pskit/onprem-<stage>/onprem_deployed.json`, plus `deployed_on` in `deployment.json`). `pskit trigger`, `pskit logs`, `resources send`, executions and the studio no longer fall back to `http://127.0.0.1:8080` after `package` / `plan` / `info` re-rendered the spec without `--server`, or after the studio's Machine picker reset. The next deploy without `--server` goes to the same saved server; `--server local` picks this machine. `pskit deploy` prints where it deployed instead of `On-premises local`.
- **On premises: hosts whose port is closed are reached over SSH.** Logs, triggers, bucket uploads, HTTP tests and the other control calls to a remote host whose port is not reachable from here (the default `127.0.0.1` bind, or a firewall) now run over the deploy's SSH login. Previously they failed with `WinError 10061 ... actively refused`. If nothing answers there either, the error says so and names the redeploy command.
- **Studio: server pickers start on the deployed server.** Deploy (Machine), Test (new **Server** picker for *Send to …*, also used by its logs) and Logs open on the server the stage was deployed to, mark it `· deployed here`, and offer *This machine (local)*. Deploy asks before moving a stage to another machine. Studio trigger, resource-send and workflow-run jobs now pass `--server`.

## [1.3.8] - 2026-10-22

### Added
- **On-prem services from the Resources list**: *Resources → + On-prem service* creates Redis, Kafka, PostgreSQL, MinIO, OpenBao, ... and adds it to the resource list with its triggers; *Add resource* offers *Create a <type> on premises* (catalog filtered to services that can back that type). Services created earlier but missing from `pskit.yml` are listed above the table with one-click **Add**, and rows backed by a service show `on-prem <service> · <server>`.
- **Logs per server**: the studio *Logs* view has a **Server** picker for on-prem projects, and `pskit logs --server NAME` reads the host on that saved server instead of the last deploy's endpoint. The same `--server` also points `pskit trigger`, `pskit resources send`, executions and the other host commands at that machine (one project deployed to several servers).

## [1.3.7] - 2026-10-22

### Added
- **Saved SSH servers**: `pskit resources onprem servers add|list|test|remove` and studio *On-prem services → Servers*. Name each machine once (key file, SSH agent / default key, or password through sshpass); the test reports OS, CPU, memory, disk, Docker access, sudo and installed runtimes. Services are created on one with `create --server NAME` or the create form's **Server** list. Stored in `.pskit/onprem-servers.json`; passwords only in `.pskit/ssh/`.
- **Deploy to a chosen machine**: `pskit deploy --server NAME` (also package / plan / remove / info), `provider.options.deploy.server` in `pskit.yml` (per stage), and studio **Deploy → Machine**. The saved server's host, user, port and login replace those in `options.deploy`.
- **Install software on a server**: Node.js (22 / 20 / 18 from NodeSource), Java (OpenJDK 21 / 17), Go (any 1.x.y), nginx (enabled and started), Caddy, Certbot, PM2, Git and basic tools, next to Python and Docker; apt, dnf, yum and apk. `create KEY --service nodejs --version 20 --server edge1`; the studio offers a version picker.
- **Console for every service**: `pskit resources onprem console KEY [COMMAND]` and studio *Console*: redis-cli, psql, mysql / mariadb, mongosh, rpk, kafka scripts, rabbitmqctl, lavinmqctl, nats (nats-box), mc, aws (s3 / sqs), awslocal, bao, the memcached text protocol and HTTP APIs, or `sh` in the container. Lines run on this machine or over SSH with the service's credentials (hidden in the output); images without a client get a helper container on the service's private network. Servers get `pskit resources onprem shell SERVER [COMMAND]` and the studio *Shell*.
- **Browser terminal**: `pskit resources onprem terminal (KEY | --server NAME)` and studio *Terminal*: ttyd in Docker on `127.0.0.1` behind a random secret path, embedded in the studio; SSH sessions with the saved login, or a service's interactive client / `sh`. `--list`, `--stop NAME|all`.
- **Secret managers**: one-click **OpenBao** (Vault API, KV v2 at `secret/`, file storage, unsealed automatically, web UI, the password is the token) and **LocalStack** as a secret manager (AWS Secrets Manager + SSM). `get_secret(name, field=None, store=None, default=None)`, `get_secrets(name)` and `put_secret(name, value)` in the Python runtime and `getSecret` / `getSecrets` / `putSecret` in Node.js, with `vault`, `aws` (SigV4, Lambda credentials) and `env` drivers chosen by `PSKIT_<STORE>_*` variables, so the same handler reads secrets on every provider. New guide *On premises → secrets*.

### Changed
- Command logs also mask `*TOKEN*=` values.
- `describe_target` names the saved server (`edge1 (ubuntu@10.0.0.5:22)`).

## [1.3.6] - 2026-10-22## [1.3.6] - 2026-10-22

### Added
- **Web UI check**: `pskit resources onprem gui KEY --check` and studio *Details > Check web UI* test every web UI of a service: the container, the published port, the HTTP answer on the server itself (over SSH) and from this machine. Each UI gets a verdict and the fix: not running, port not published, bound to `127.0.0.1`, app not answering, firewall dropping (timeout) or rejecting (refused). On Azure / AWS / GCP the cloud is read from the instance metadata, with the exact `az vm open-port` command (resource group and VM name filled in), the subnet + NIC NSG note, the security group / firewall-rule steps, ufw / firewalld status, and the tunnel that works without opening anything. Nothing is changed.
- **Web UI login choice**: companion UIs start *with password* (generated, or your own with `--gui-password-env` / the studio field) or *without password* (`--gui-login none`; Redis Commander, Kafka UI, Mongo Express). Adminer always asks for the database login. A UI without login on `0.0.0.0` prints a warning. `pskit resources onprem gui KEY --login none|password --password-env VAR` switches an existing UI.
- **SSH login without a key file**: service targets and on-prem deploys log in with a key file, with the SSH agent / default key (no `pem`; also `auth: agent`), or with a password through sshpass (`password_file`, or `auth: password` with `SSHPASS`; studio *Log in with: Password*, saved in `.pskit/ssh/`, owner-only). The password never appears on a command line, in state, `pskit_host.json` or Terraform state.
- `pskit resources onprem ssh-key user@host[:port]`: logs in with the password once (ssh asks in the terminal, so it works on Windows without sshpass), installs `~/.ssh/pskit_ed25519` and checks that the key logs in.
- Guides: *Web UIs > With or without a password*, *The UI does not open* (the usual reasons an inbound rule "does not work"), *Try the web UIs in local Docker first*, and *SSH login: key, agent or password*; every How to use guide's Web UI section names the UI's port to open and the check command.

### Changed
- Remote Docker deploys no longer require a `.pem`: without one, OpenSSH uses the agent / default key (`pskit deploy` still offers to enter a path in a terminal). A `pem` that points to a missing file is still an error.

### Fixed
- A second companion web UI of the same kind on one server reused the default port and failed (`port is already allocated`); it now takes the next free port.

## [1.3.5] - 2026-10-22

### Added
- **More one-click on-prem services**, each driven end to end through its pskit driver: Dragonfly and KeyDB (Redis-compatible: queue, stream, cache), Apache Kafka (KRaft), LavinMQ (AMQP, RabbitMQ driver class), Azurite (Azure Blob + Queue with your own account and key), LocalStack (SQS + S3), fake-gcs-server (Cloud Storage) and RustFS (S3-compatible with a console).
- **Web UIs**: built-in UIs (RabbitMQ, LavinMQ, MinIO, RustFS, ElasticMQ, NATS, Mailpit) are listed with URL and login, and pskit can start a companion UI on a private Docker network with the service: Adminer (PostgreSQL / MySQL / MariaDB, server filled in), Redis Commander (Redis family, login), Kafka UI (login), Mongo Express (login). `pskit resources onprem gui KEY [--port] [--remove]`, `create --gui`, studio *Also start the web UI* and *Details > Add / Remove web UI*; every How to use guide has a **Web UI** section with a tunnel command (`tunnel --remote-port`).
- **Existing cloud code on premises**: the host serves the Lambda Invoke API (`POST /2015-03-31/functions/<name|ARN>/invocations`, RequestResponse / Event / DryRun, `FunctionError` on handler errors) and the SQS API for its queues (send / batch / receive with long polling / delete / visibility / attributes / list / create / purge). boto3 and the AWS SDKs work by changing `endpoint_url`; the `admin_token` doubles as the access key id. On-prem queues expose their SQS-compatible URL as `resource(key).url`.
- `invoke()` accepts deployed names and Lambda ARNs (with or without an alias) as well as pskit names, on every provider.
- Drivers: `create_queue` (azure_queue) and `create_bucket` (s3 family, azure_blob, gcs) create the queue or bucket on first use and after an emulator restart.
- Guides: *General > Existing cloud code* (`docs/resource-guides/compatibility.md`), shown in the studio; on-prem queue guides add an *Existing AWS SDK code* section.

### Fixed
- Extra ports (consoles, Azurite's queue port) were fixed numbers, so a second instance of a service on one server failed to start; they now move with the main port.
- Services answering over HTTP are ready only once they answer (Docker's port proxy accepts TCP before the app listens).
- Built-in queue messages count deliveries (`ApproximateReceiveCount` semantics) for leases and the SQS API.

### Changed
- Studio: calling the host from code is part of each resource's **How to use** guide (section 7, *Call it from code*) instead of a separate *Call from code* panel. On premises it has complete Python and Node.js programs for that resource with the pskit client (add data, page through it with `peek`, consume with `receive` + `ack` / `nack`, upload / download / list / delete files, publish with attributes, error handling), the host URL, token note and a live reachability check, then HTTP (7.2), the service's own library (7.3) and a timeouts section (7.4). The consume step is commented out when a pskit trigger already consumes the queue or its driver has no leases. `pskit client info` stays for the terminal.

## [1.3.4] - 2026-10-22

### Added
- **pskit client** for any program: `py_serverless_kit.client.PskitClient` (Python, standard library only) and `PskitClient` in the `pskit` Node.js package (with TypeScript types). Queues (`send`, `send_batch`, `depth`, `peek`, `receive` + `ack` / `nack`), topics (`publish`, `peek`), buckets (`put`, `get`, `delete`, `list`, `keys`), `invoke`, workflows, `check`, `resources`; resource keys or native names; `PskitClient.from_project(".")`. Everything goes through the host's HTTP API, so only the host port must be reachable.
- `pskit client info` (endpoint, token, reachability check, Python / Node.js / curl code per resource), `pskit client install-node` (copies the `pskit` package into `node_modules`), `pskit client tunnel` and `pskit resources onprem tunnel KEY` (SSH port forwarding for firewalled ports, printing the variables to use).
- Host: `GET /__pskit/storage/<bucket>` lists objects and `GET /__pskit/storage/<bucket>/<key>` returns one.
- Studio: *Resources → Call from code* (client guide with a live reachability check); *On-prem services → Details* and *How to use* warn when this machine cannot reach a service's port and say how to fix it.
- `docs/client.md`: client APIs, the full host HTTP API, and what to do when connections time out.

### Fixed
- Scripts generated for on-prem services hung for a minute when the service's port was firewalled (e.g. ElasticMQ on an Azure VM). Every direct-client example now uses short connect timeouts and a single attempt (boto3, redis, kafka-python, nats, pika, psycopg, pymysql, pymongo, pymemcache, smtplib, and their Node.js counterparts), so it fails in about five seconds; the guides explain the firewall and offer the tunnel and the pskit client instead.

## [1.3.3] - 2026-10-22

### Added
- **Credentials for on-prem services**: choose the user and password when creating a service (studio *Security* box with *Generate*; `--user`, `--password`, `--password-env`), and whether it listens on `127.0.0.1` or the network. Redis / Valkey with a custom user get an ACL user with the `default` user disabled. Passwords are percent-encoded in URLs and validated; services that run without authentication (Kafka, ElasticMQ, Memcached, Mailpit) refuse a password and say how to keep them private.
- **Use a service from any program**: *How to use* on each on-prem service and `pskit resources onprem usage KEY [--reveal]`: address, credentials, Python and Node.js code that connects directly (Redis lists and streams, Kafka, NATS JetStream, RabbitMQ, ElasticMQ, MinIO, PostgreSQL, MySQL, MongoDB, Redis cache, Memcached, SMTP) with the library to install, terminal commands and security notes. Resource guides on premises gain section 7, *Use it from any other program*, with the host HTTP API (any driver) and the direct client.
- **Browse data**: studio *Resources → Data* and `pskit resources data KEY` page through waiting queue messages (peeked, not consumed), pending topic messages and bucket objects (prefix filter, preview, delete); built-in queue messages can be deleted one by one. New host endpoints `GET /__pskit/resources/<key>/data`, `GET|DELETE /__pskit/resources/<key>/object`, `DELETE /__pskit/resources/<key>/message`, `GET /__pskit/queues/<name>/peek`. The redis, redis_stream and pskit_host drivers (and custom classes with `peek`) are browsable; services that count a delivery when showing a message show their depth.

## [1.3.2] - 2026-10-22

### Added
- **How to use, for every resource**: studio *Resources → How to use* and `pskit resources usage KEY` show an end-to-end guide for that resource on the current provider and stage: the library to install for Python and Node.js and how pskit packages it, the `pskit.yml` and trigger, handler code (publish / consume / connect) with copy buttons, local tests (`pskit invoke`, `pskit dev`), deployed tests (`resources send`, `resources check`, `logs`, cloud CLI), provider notes and troubleshooting. Covers every provider and resource type: S3-compatible buckets on Alibaba, Tencent, Huawei, Oracle, IBM, DigitalOcean and Cloudflare get `boto3` / `@aws-sdk/client-s3` code with the right endpoint; queues and topics there use the SDK example from the resource guides, with its library in the install step.
- `docs/resource-usage.md`: libraries per provider and type, how dependencies reach the function, secrets and a testing checklist.

## [1.3.1] - 2026-10-22

### Added
- **Code for every resource**: the studio's *Test a resource* panel shows Python and Node.js handler code (publish + consume for queues, buckets and topics on each cloud; PostgreSQL, MySQL, MongoDB, Redis, Memcached and SMTP connection examples) with the client library to add.
- **`pskit resources check KEY`** and studio *Test connection*: queue depth, bucket object count, or a connection check (Redis `PING`), run from the on-prem host once deployed (`POST /__pskit/resources/<key>/check`), else from this machine.
- **`pskit resources clear KEY`** empties a built-in on-prem queue, bucket or topic (`DELETE /__pskit/resources/<key>/data`). Studio *Delete* asks whether to keep or delete a resource's data (one-click services: stop or delete the container).
- Node.js on premises: `submitQueue`, `submitTopic`, `putObject` and `deleteObject` in `pskit`, like the Python helpers (through `PSKIT_HOST_URL`).

### Fixed
- On premises: an ElasticMQ queue created on an SSH server failed with `QueueDoesNotExist`: the queue was created from this machine (often firewalled) and ElasticMQ forgets queues on restart. It is now created from the server over SSH when needed, and the `sqs` driver recreates a missing queue (`create_queue`, on by default for non-AWS endpoints).

## [1.3.0] - 2026-10-22

### Added
- **Resource guides** (`docs/resource-guides/`): step-by-step pages per provider and resource type (storage, queue, topic, database, cache, custom) for AWS, GCP, Azure, Alibaba, Tencent, Huawei, Oracle, IBM, DigitalOcean, Cloudflare and on premises: how to create the service in the console, where to find each value, the `pskit.yml` to attach it as an external resource, a handler snippet, how to test it and common errors.
- **One-click on-prem services** (`pskit resources onprem create|list|status|logs|backup|remove|catalog`, studio *Resources → On-prem services*): start Redis, Valkey, Kafka (Redpanda), NATS JetStream, RabbitMQ, ElasticMQ (SQS API), MinIO, PostgreSQL, MySQL, MariaDB, MongoDB, Memcached or Mailpit as a Docker container on this machine or any SSH server (the functions' server or another one; Docker is installed there when missing), or install Python / Docker on a server. The resource, its triggers on the functions you pick and `provider.options.env_file` are added to `pskit.yml`; generated passwords go to `.env.onprem`. Kafka, NATS and RabbitMQ get a driver class in `pskit_drivers/` and their client library in `requirements.txt`. Backups stream into `.pskit/backups/`.
- **`redis_stream` queue driver**: a Redis 6.2+ / Valkey stream with a consumer group (native leases and delivery counts, crash takeover with `XAUTOCLAIM`, several hosts per group). Offered as the *stream* role of Redis and Valkey.
- **`pskit_host` queue driver**: functions on one on-prem host consume the built-in queue of another, through new lease endpoints `POST /__pskit/queues/<name>/lease|ack|nack` (at-least-once).
- On premises: `provider.options.env_file` ships a `KEY=VALUE` file with the host (`host.env`) for local, SSH and Docker deploys and loads it at start, so `<name>_env` secrets need no systemd or container configuration and never reach Terraform state. `GET /__pskit/resources` lists resources with their backend, consumers and queue depth.
- Studio: **Guides** shows the resource guides for every cloud in the app, with *How to set up* links from the resource form.

### Fixed
- On premises: a driver-backed queue or bucket that no trigger consumes (only published to with `submit_queue` / `put_object` / `pskit resources send`, or used as a `dead_letter`) silently went to a local folder; drivers are now bound from `resources:` too. `dead_letter` may name a resource key. Managed queues, buckets and topics no event uses are created when the host starts.
- On premises (Windows): deploy failed with `WinError 206` when vendored packages made the staging path longer than 260 characters.
- `examples/19-custom-drivers/app/kafka_queue.py` polled with a zero timeout, so the consumer never joined its group and received nothing.
- `runtime_js/package.json` version now follows `__version__` (it was left at 1.2.0 in 1.2.1).

## [1.2.0] - 2026-10-21

### Added
- **Test resources directly**: `pskit resources send KEY` sends a message to a queue, uploads an object to a bucket or publishes to a topic, for managed resources (once deployed) and external / custom-named ones (right away). `pskit resources send --list` shows how to test every resource: sample payload, pskit and cloud CLI commands and console steps; for database, cache and custom resources it shows the `PSKIT_RESOURCE_*` variables and a Python / Node.js snippet. Studio: **Test a resource** panel and a **Test** button on every resource row.

### Fixed
- Azure: `pskit resources send` and `pskit trigger` read the storage account and Service Bus connection strings from the deployment's Terraform state, so `AZURE_STORAGE_CONNECTION_STRING` / `AZURE_SERVICEBUS_CONNECTION_STRING` are only needed as overrides. The error now shows the `az` command that prints them.

## [1.1.0] - 2026-10-21

### Added
- **Test functions with real events**: `pskit trigger` sends a test event to a deployed function through its trigger: an HTTP request, an SQS / Pub/Sub / Storage-queue / on-prem queue message, an S3 / GCS / Blob / on-prem upload, an SNS / Pub/Sub / Service Bus / on-prem topic message, or a direct invocation. `pskit trigger --list` shows, for every function and trigger, a sample payload, the local `pskit invoke` command, the `pskit trigger` command, the cloud's own CLI command and the console steps. Studio **Test** page: pick a trigger, edit or save the event, then Run locally or Send to the deployed stage with live logs, plus a How-to-test panel (studio, terminal, console).
- `pskit resources list | delete`: list the buckets, queues and topics pskit created (deployed, or kept by `--keep-resources`) and delete them permanently. Kept ones are remembered in `.pskit/<provider>-<stage>/kept/`, so they can be deleted after the stage is gone. Studio: **Resources → In the cloud**, with select, delete selected and delete all kept.

## [1.0.0] - 2026-10-21

### Added
- **Node.js and TypeScript functions** (`provider.runtime: nodejs18 | nodejs20 | nodejs22 | nodejs24`) on every provider. A service is either Python or Node.js. Handlers use the same `module.function` form, and the `pskit` package (vendored as `pskit_runtime/`) has the same Event / Context / Response / BatchResult API in camelCase, plus `invoke()`, resources and the embedded workflow engine. TypeScript is compiled with `tsc` while packaging (`package.node`). The on-prem host and `pskit dev` / `pskit invoke` run Node.js handlers through a JSON-lines worker. See `docs/nodejs.md` and `deploy_docs/NODE_RUNTIME.md`.
- `pskit remove --keep-resources`: destroy functions and triggers but keep managed buckets, queues and topics with their data (they leave the Terraform state). Studio's Deploy page has the matching switch.
- Studio:
  - **Project environment** creates `.venv` with a chosen interpreter and installs `requirements.txt`, or runs `npm install` for Node.js services.
  - Full VS Code: pick Python and Node.js versions; studio builds a code-server image with them once.
  - Triggers: **Create & select** adds a new queue, bucket or topic to Resources and selects it.
  - JS/TS editing: highlighting, handler stubs in TypeScript or ESM/CommonJS JavaScript, and Node.js runtimes in the runtime pickers.
  - On-prem deploy fields for Node.js (`node`, `node_url`, `node_sha256`, `host_python`).

## [0.9.0] - 2026-10-21

### Added
- `enabled: false` on functions and workflows: kept in `pskit.yml`, skipped on deploy. Combined with `providers.<cloud>` overrides it switches items (or single triggers) off on one cloud only.
- **Azure native workflows** on Azure Logic Apps (Consumption) with `engine: native` (`auto` stays embedded). The pskit output includes the trigger callback URL, and `pskit workflow start` uses it. Azure also outputs `log_analytics_workspace_id` when Application Insights is on.
- **Cloud logs** (`core/cloud_logs.py`): `pskit logs` and the dashboard read logs from AWS CloudWatch, GCP Cloud Logging and Azure Log Analytics, as well as on-prem. Log streams can be listed and deleted (AWS, on-prem) with `pskit logs --streams / --delete / --delete-all` and in the dashboard. On-prem hosts gain `GET /__pskit/logs/streams` and `DELETE /__pskit/logs`.
- **`pskit doctor`** (`core/setup_check.py`): checks Terraform, the cloud CLI, credentials, required provider options and on-prem SSH/Docker, with download links and per-OS install steps.
- `pskit --help` lists every command and workflow subcommand with examples; help is no longer truncated.
- Studio:
  - **Setup & credentials** page: the checks above, an `aws configure`-style profile form, provider environment variables for the session, browser logins (`az login`, `gcloud auth ...`) and an SSH connection test.
  - **Logs** page and per-function live logs: tail, list streams, delete selected or all.
  - File picker for the on-prem SSH private key.
  - Dropdowns (with a custom value) for region, stage, memory, timeout, log retention, plan SKUs, SSH user, timezone and more.
  - Schedules **at a specific time**: daily, weekdays, chosen days, monthly or yearly at HH:MM in a timezone.
  - Trigger options each provider rejects or ignores are derived from its validation and shown in the form. Unsupported auth modes are disabled, and only supported trigger types are offered.
  - The queue, bucket and topic source picker offers a new resource, a project resource, a pick from the cloud account (optionally added as an external resource), or a typed name.
  - Enable or disable a function or workflow everywhere or only on the current provider. Before deploy, and when switching provider, unsupported items are listed with a one-click "disable on this provider".
  - Clear the recent jobs list (all finished jobs, or one).

## [0.8.0] - 2026-10-21

### Added
- **`pskit studio`**: a local web UI to build a project without writing YAML.
  - New-project wizard; provider cards for all 11 targets with their capabilities; provider, region, runtime and provider-option forms; on-prem deploy method, services and tuning.
  - AWS-console-style **Create function** wizard. Trigger types follow what the selected provider supports, with HTTP path-parameter preview and CORS/auth, a cron/rate builder, and a queue/storage/topic source picker (new, from Resources, **Browse account** or typed).
  - Visual workflow builder: a diagram plus an inspector for every state type, choice rule groups, retry/catch, and nested parallel/map.
  - Resources with an on-prem driver picker for every built-in driver and custom classes; secret fields read from env vars.
  - Code page with a CodeMirror editor, or **Full VS Code**: code-server pulled into Docker on demand, run on the project and embedded.
  - Deploy page (validate/package/plan/deploy/info/remove with live logs, invoke, local workflow runs); raw-YAML mode with a diff against disk.
  - Edits stay in a draft that is validated live and saved with backups and conflict detection. `${...}` values are kept as written.
  - Session token, loopback bind, Host/Origin checks. See `docs/studio.md`.
- Studio account discovery: lists existing SQS queues, S3 buckets, SNS topics and state machines (boto3); Pub/Sub topics and subscriptions and GCS buckets (google-cloud-*); Azure queues and containers (connection string); and on-prem directories.
- `providers/onprem_catalog.py`: a data catalog of on-prem driver fields, kept in sync with validation by a test.

### Fixed
- The dashboard server reads a POST body before rejecting the request (403/415), so Windows no longer resets the connection before the client reads the error.

## [0.7.0] - 2026-10-21

### Added
- On-premises drivers that watch queues and buckets in other providers: `sqs` (AWS, JSON protocol + SigV4), `azure_queue` and `azure_blob` (Shared Key, SAS or connection string; Azurite), `pubsub` (pull subscription) and `gcs` (access token, `token_command` or the metadata server; emulators), `mns` (Alibaba Cloud) and `cloudflare_queue` (HTTP pull consumer). Leases use each service's own visibility timeout, so delivery stays at-least-once. See the provider matrix in `docs/resources.md`.
- S3 storage presets `aws`, `oss`, `cos`, `obs`, `oci`, `ibm_cos`, `spaces`, `r2` and `minio` (or `driver: s3` + `provider:`). `s3` without `endpoint` now targets AWS (virtual-host style), and credentials fall back to the `AWS_*` environment variables.
- `custom` queue and storage drivers: `class: package.module:ClassName` from your app, constructed with the remaining options. Import errors, constructor errors and missing methods are reported with the class name. `docs/resources.md` has a RabbitMQ example (AMQP with manual acks).
- Any on-prem driver parameter can be written as `<name>_env: VARIABLE`, read from the host's environment at start, so secrets stay out of `pskit_host.json` and Terraform state.
- `examples/19-custom-drivers`: runnable `custom` drivers (`SqliteQueue` with visibility timeout, receive counts and a dead-letter table; `FolderStorage` for local/NFS/SMB folders) plus RabbitMQ (pika) and Kafka (kafka-python) templates, all at-least-once.
- `examples/20-onprem-external-clouds`: one on-prem host consuming SQS, Azure Storage Queue, Pub/Sub, MNS and Cloudflare Queues and watching S3, Azure Blob, GCS, R2 and MinIO, with every secret read through `*_env`.

### Fixed
- The on-premises host makes the app importable before building its queue/storage drivers, so a `custom` driver class from the app loads at start.
- The on-premises host sets `PSKIT_ONPREM_ROOT` before building its drivers, so relative paths in driver options resolve against the host directory.

## [0.6.0] - 2026-10-21

### Added
- **`resources:`** for storage, queues, topics, databases, caches and custom services. A resource is managed (pskit creates it) or `external: true` (pskit only attaches it). Bound functions get `PSKIT_RESOURCES` and `PSKIT_RESOURCE_<KEY>_TYPE/NAME/EXTERNAL/<connection key>` variables, plus `ARN`/`URL` on AWS and `ID` for Pub/Sub on GCP. `functions:` limits which functions get a binding. `queue`, `storage` and `topic` events accept `resource: <key>`. Standalone managed resources are created on AWS, GCP, Azure and on premises; other providers report a validation error. AWS roles get a `pskit-resources` policy for the bound resources. See `docs/resources.md`.
- On-premises `provider.options` `execution_retention`, `workflow_workers`, `log_buffer`, `log_level` and `capture_output` to tune the host's execution store, workflow concurrency and log capture.
- `resource()`, `resources()` and `Resource` in `py_serverless_kit`, to read bindings the same way on every cloud.
- On-premises drivers for resources: `redis` queues (stdlib RESP client; `<key>`, `<key>:processing` and `<key>:claims`, with crash recovery) and `s3` storage (SigV4, MinIO and any S3-compatible store, `prefix`, `path_style`, `session_token`), plus a per-resource `directory`. Unreachable backends become host notes and the host keeps running.
- Workflow execution ids everywhere. The on-premises host tracks runs in `<data_dir>/executions/`: status, current state, history (`enter`/`exit`/`caught`/`retry`/`fail`), input, output and error. `GET /__pskit/executions[/<id>]` and `POST /__pskit/executions/<id>/cancel` inspect and control runs. Cancel stops before the next state and wakes `wait` states. `workflows.<name>.timeout` is enforced by the embedded engine (`TIMED_OUT`), and runs interrupted by a restart become `ABORTED`. Cloud orchestrators return `execution_id` with their synchronous result. See `docs/workflow-executions.md`.
- `pskit workflow start | executions | status | cancel` for deployed workflows on the on-premises host, AWS Step Functions (`pip install "py-serverless-kit[aws]"`) and Google Cloud Workflows (new `[gcp]` extra: `google-cloud-workflows`).
- On-premises logs: the host captures logging, `print`/stdout/stderr, one entry per invocation and host notes, tagged with function and request id, in memory and in `<data_dir>/logs/host.jsonl` (rotated). `GET /__pskit/logs` (`since`, `before`, `limit`, `level`, `function`, `source`, `q`), `GET /__pskit/stats` (invocations, errors and durations per function, queue depths), and `pskit logs [-f]`.
- A new React + Vite dashboard (single self-contained page) with sortable, paginated tables, deployment tabs (Functions, Workflows, Executions, Logs, Resources, Outputs) and light/dark themes. `pskit dashboard --serve` (new `--host`) adds a JSON API for live host health and stats, a log tail, and workflow executions (list, start, follow, cancel). The API checks the Host header and same-origin POSTs and keeps admin tokens server-side.
- `docs/scenarios.md`: step-by-step guides by use case.

### Changed
- **Breaking (on premises):** `POST /workflows/<name>` and `POST /__pskit/workflows/<name>` start the workflow in the background and answer `202 {"execution_id", "status": "RUNNING", "status_url", ...}`. Add `?wait=true` (or `Prefer: wait`, or `x-pskit-wait: true`) to get the old synchronous result. That result now also includes `execution_id`, `started_at` and `stopped_at`.
- `deployment.json` (and `pskit info --json`) include the deployment `key` (`<provider>-<stage>`) and `resources` (connection key names only).

### Fixed
- The on-premises host drains the request body before answering `401` for a missing admin token. On Windows the client previously saw a connection reset instead of the 401.
- Re-validating a dumped config no longer leaves each event's config as a plain dict.

Redeploy to pick up the new runtime. Handler code is unchanged.

## [0.5.2] - 2026-10-19

### Fixed
- On-premises SSH deploy as a normal user such as `azureuser`. With `deploy.sudo: true`, apply creates `deploy.path` with `sudo -n mkdir` and `chown`s it to the SSH user before `scp`. A user who cannot write `/opt` no longer fails with `Permission denied`.

Redeploy the on-premises host after upgrading. Handler code is unchanged.

## [0.5.1] - 2026-10-19

### Fixed
- On-premises `python: bundle` on Windows. Unpacking a Linux CPython into the project raised `WinError 206` (`The filename or extension is too long`) on setuptools test files under `pkg_resources/tests`. A remote deploy now copies that archive straight into `release.tar.gz` and leaves those test files out. A partial `onprem_app/python` tree from the failed unpack is removed on the next deploy.

Redeploy the on-premises host after upgrading. Handler code is unchanged.

## [0.5.0] - 2026-10-19

### Changed
- On-premises remote deploy copies one `release.tar.gz` with `scp` and starts it from a script on the server. `options.deploy.method: scp` is the same path as `ssh`. A `.pem` (`pem` or `identity_file`) is passed with `IdentitiesOnly`. `pskit deploy` asks for that path on a terminal for SSH as well as Docker; press Enter on the SSH prompt to keep the SSH agent or the default key. Docker on a server still requires a key.
- The server script restarts a systemd unit (`systemctl restart`, so a redeploy replaces the running process), installs and starts Docker when `method: docker` and `docker` is missing, and uses `sudo -n` so a missing sudoers rule fails immediately. It exports a normal `PATH` (non-login SSH often cannot see `systemctl` or `python3`). `pskit-run.sh` starts a bundled CPython when one was copied, then `python3.x`, then `python3`.
- Apply waits until `http://127.0.0.1:<port>/__pskit/health` answers. A dead process or container fails the deploy and prints `journalctl` or `docker logs`. A process that binds `0.0.0.0` is checked on `127.0.0.1`, including when `advertise` is a public URL.

Redeploy on-premises hosts to pick up the new provisioner. Handler code is unchanged.

## [0.4.0] - 2026-10-19

### Added
- On-premises Docker deploy to a server. Set `options.deploy.method: docker` and `options.deploy.host`. `pskit deploy` asks for a `.pem` private key when `options.deploy.pem` is unset (`identity_file` is the same field). The image is built on the machine that runs `pskit`, copied over SSH, and started with `docker run`. If `docker` is missing on the server, apply installs it (`docker.io` via apt, `docker` via dnf or yum, or `docker` via apk) and then loads the image. `install_docker: false` skips the install and fails if Docker is absent. `sudo` defaults to true for this path so the SSH user can install and start the daemon.

Redeploy on-premises Docker hosts to pick up the new provisioner. Handler code is unchanged.

## [0.3.0] - 2026-10-17

### Added
- On-premises deploy targets. `provider.options.deploy.method` is `local` (default, previous behaviour), `ssh` (copy the host over OpenSSH and start a process or systemd unit), or `docker` (build an image that already contains Python). When the server has no Python, set `python: bundle` to ship a portable CPython, or use `method: docker`. `python_home` / `python_url` cover air-gapped mirrors. Wheels are vendored for the target OS/arch (manylinux when the server is Linux).
- Example [17-on-premises-remote](examples/17-on-premises-remote): SSH + bundled interpreter + systemd.

### Fixed
- On-prem host: Windows process helpers (`ctypes.windll`, `subprocess.DETACHED_PROCESS`) are gated on `sys.platform == "win32"` so mypy on Linux/macOS CI no longer reports missing attributes.

Redeploy on-premises hosts to pick up the new `onprem_deploy.py` provisioner. Handler code is unchanged.

## [0.2.0] - 2026-10-17

### Added
- On-premises provider (`provider.name: onprem`). `pskit deploy` starts one long-lived Python process on the machine that runs the command. HTTP is served directly. Schedules, file queues (with dead-letter and partial batch failure), directory storage and file topics are created at start when they do not already exist. Point `provider.options.services.<kind>` at `{use: directory, path: ...}` to use a directory you already have. `existing: true` waits for that directory instead of creating it. Workflows run on the embedded engine inside the host, and `invoke()` stays in-process. `pskit remove` stops the process and leaves the data directory in place.
- Example [16-on-premises](examples/16-on-premises). Every other example has an `providers.onprem` block (its own port, public auth where a cloud authorizer does not apply, local state where the file used a cloud backend).

No change to handlers that already run on a cloud. Redeploy to pick up the new runtime if you use `BatchResult` or `invoke()` on premises.

## [0.1.3] - 2026-10-15

### Fixed
- AWS: `pskit deploy` failed with `creating Lambda Function ...: decomposing request: bufio.Scanner: token too long` once the bundle (e.g. with vendored dependencies) got large, because the zip was sent inline in every `CreateFunction` request. The artifact is now uploaded once to S3 (`aws_s3_object`) and each Lambda function references it via `s3_bucket`/`s3_key`. This also lifts the 50 MB inline upload limit.

### Added
- AWS options `artifact_bucket` (use an existing bucket for code uploads instead of the private `<service>-<stage>-code-*` bucket pskit creates) and `artifact_upload: s3 | direct` (`direct` restores the old inline upload).

No runtime changes. Existing AWS deployments get a new code bucket on the next `pskit deploy`; Lambda functions are updated in place.

## [0.1.2] - 2026-10-15

### Fixed
- Python 3.9 support: `pskit package`/`deploy` (and the Cloudflare provider) crashed with `TypeError: write_text() got an unexpected keyword argument 'newline'`, because `Path.write_text(newline=...)` only exists on Python 3.10+. Generated files are now written as UTF-8 bytes with `\n` line endings on every Python version.
- GCP adapter: the storage object `size` check now narrows `None` explicitly, so mypy passes on Python 3.9 CI. Runtime behavior is unchanged.

No runtime behavior changes: functions deployed with 0.1.1 don't need to be redeployed.

## [0.1.1] - 2026-10-15

### Changed
- Author and maintainer set to Asif Khan @ Kavion.ai (`py_serverless_kit.__author__`, package metadata, LICENSE).
- Project URLs (homepage, docs, issues, changelog) now point to https://github.com/kavion-ai/py-serverless-kit.
- README links are absolute so they work on the PyPI project page; added CI/PyPI/license badges.
- `scripts/validate_all_providers.py` explains that Terraform is optional instead of printing a traceback when it isn't installed.

### Added
- `deploy_docs/How_to_deploy.md`: short PyPI release guide with PowerShell commands and troubleshooting (e.g. TestPyPI `403`).
- `deploy_docs/HOW_TO_INSTALL_TERRAFORM.md`: installing Terraform on Windows.

No runtime changes: functions deployed with 0.1.0 don't need to be redeployed.

## [0.1.0] - 2026-10-15

### Added
- Portable handler API: `Event`, `HttpRequest`, `Record`, `Headers`, `Context`, `Response`, HTTP error classes, `BatchResult`, `invoke()`.
- `pskit.yml` configuration with `extends:`, `providers:` and `stages:` overrides, and `${env:}`, `${opt:}`, `${self:}`, `${file()}` and `${tf:}` variables.
- Providers: AWS (stable), Google Cloud (stable), Azure (stable), Alibaba Cloud (beta), Huawei Cloud (beta), Tencent Cloud (beta), DigitalOcean (beta), IBM Cloud (beta), Oracle Cloud (experimental), Cloudflare Workers (experimental).
- Triggers: HTTP (path params, CORS, auth), schedule (rate/cron), queue, storage, topic.
- Workflows: native AWS Step Functions and Google Cloud Workflows compilers, plus an embedded engine for the other providers and local runs.
- CLI: `init`, `validate`, `package`, `plan`, `deploy`, `remove`, `info`, `dashboard`, `dev`, `invoke`, `workflow run|show`, `providers`, `tf`.
- Deployment dashboard (self-contained HTML).
- Local dev server with hot reload, and `LocalRunner` for tests.
- `scripts/validate_all_providers.py`, which runs `terraform validate` for every provider.
