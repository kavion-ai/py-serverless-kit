# Studio: Create service

How to open: Resources > + On-prem service

The + Create service button on the On-prem services panel opens the same drawer. Resources > + SMTP server

That button opens the drawer with the smtp type. Both resource buttons are disabled when the provider is not onprem.

What it is for: Start a catalog service with Docker, or install a runtime, and add a service to the draft. The drawer title is "Create a service" until you pick a card, then "Create <label>".

What you see: Catalog groups in the component are Queues & streams, Redis-compatible (cache, queue, stream), Object storage, Databases, Mail (receive e-mail, run functions), Secret managers, AWS emulators, Monitoring & tracing, Identity & search, Automation, web & tools, and three "Install on a server" groups (languages and Docker, web servers, process managers and tools). Each card shows the label, notes or image, the port, and a web UI line when the catalog entry has one. After you pick a service: Resource key (help says handlers use resource("key")), Use as when the entry has more than one role. The labels in the file are Queue, Stream (consumer group), Cache, Database, Bucket, Service, Secret manager, and SMTP server (mail trigger). Where follows. Where is This machine (disabled for a runtime), One SSH server, or Scaling cluster. Scaling cluster is hidden for a database, because that role uses the Scaling control, unless the service is already on a cluster. It is disabled when no cluster exists. A database also has Scaling: Single server, or Primary + read replicas when that service supports replicas. Port, and a Security box. SMTP adds Domains. The placeholder is inbound.example.com. The domains help says mail for other domains is refused, so it is never an open relay.

What you can do: Create, or Install for a runtime, calls `api.onpremCreate`. The label is Creating… while the job runs and Created when it succeeds. An empty password is generated. The password help says it is stored only in the env file and .pskit/, never in pskit.yml. Generate fills a password. The service user help says the default is the catalog `default_user`, or the string pskit. Pick another returns to the catalog. A new SSH connection has Host, User, SSH port, Log in with (Key file, SSH agent / default key, or Password), and Use sudo. This card does not copy the host or user placeholders from the form.

Tips and limits: This machine help says functions deployed elsewhere cannot reach 127.0.0.1, and to use an SSH server for them. The Server in the cluster help says Auto picks the reachable server with the most free memory that is under every capacity limit, when the job starts. docs/studio.md says a ready service can add the resource, provider.options.env_file, and triggers on the functions you ticked.

Sources: `dashboard-ui/src/studio/components/OnPremServices.tsx`, `dashboard-ui/src/studio/views/Resources.tsx`, `docs/studio.md#project-environment-trigger-resources-and-remove`
