## pskit's own browsers (when the native UI is missing)

Some services ship without a usable web UI. OpenBao's release images say *"OpenBao UI is not available in this
binary"*, and MinIO's community console no longer has the admin pages. For these, **Browse** on the service's row
opens pskit's UI in the studio:

| Service | Browser | What you can do |
|---|---|---|
| MinIO, RustFS, LocalStack, LocalEmu, Amazon S3 compatible | **Buckets (S3)** | Create and delete buckets (with every object and old version); folders and breadcrumbs; filter by name; 25 to 1000 objects per page with next / previous; upload several files (up to 64 MB each); download; info (size, type, ETag, metadata); old versions (list, download); rename / move and copy; share links valid 1 hour, 1 day or 7 days (S3 presigned URLs); bucket versioning on / off; bucket policy (private, public read, or your JSON) |
| fake-gcs-server | **Buckets (Cloud Storage)** | The same, without versioning, policies and signed links |
| OpenBao | **Secrets** | Folders, open a secret (values hidden until *Show values*), copy a value, versions (pick an old one), add / edit (each save is a new version), delete |
| LocalStack, LocalEmu, AWS Secrets Manager compatible | **Secrets (Secrets Manager)** | List with paging, open, add / edit, delete |

The studio talks to the service from your machine. When its port is closed by a firewall, it goes over the server's
SSH login instead (`127.0.0.1:<port>` on the server). Credentials stay in `.pskit/onprem-services.json` and never
reach the browser page.

Every service and role above was created with Docker and driven through its pskit driver (publish, receive, settle;
put, list, get) during development. Queues and buckets on Azurite, LocalStack, fake-gcs-server and RustFS are created
on first use by the driver (`create_queue` / `create_bucket`), from the host's side, so a firewall between your laptop
and the server doesn't matter and an emulator restart is survived. Extra ports (consoles, Azurite's queue port) move
with the main port: a second RabbitMQ on port 5682 gets its UI on 15682.
