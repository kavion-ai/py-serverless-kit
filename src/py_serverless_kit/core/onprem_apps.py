"""More one-click on-prem services: AWS emulators, secret managers, monitoring, identity, search, automation, tools.

Each entry is built with ``onprem_services._svc`` (passed in, to keep the import one-way) and merged into
``SERVICES``. Nothing here needs code of its own: ``connect`` templates describe the resource and env values pskit
writes, ``sidecars`` add the containers a service needs (Infisical: PostgreSQL and Redis) and ``generate`` creates
the random keys it needs once. ``{port_<n>}`` in a template is the host port of the container's extra port ``n``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

# Services that come with their own sign-up / admin account (pskit sets no login for them).
SELF_LOGIN: Tuple[str, ...] = ("uptime-kuma", "n8n", "portainer", "gitea", "nginx-proxy-manager")
# Services with no authentication at all (keep them on 127.0.0.1 or a private network).
NO_AUTH_APPS: Tuple[str, ...] = ("localemu", "prometheus", "mosquitto", "jaeger")
DEFAULT_USERS = {"neo4j": "neo4j"}

_WEB = {"URL": "http://{address}:{port}"}
_WEB_LOGIN = {"URL": "http://{address}:{port}", "USER": "{user}", "PASSWORD": "{password}"}


def apps(svc: Callable[..., Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        # ------------------------------------------------------------------ AWS emulators
        "localemu": svc(
            "LocalEmu (AWS emulator: SQS, S3, Secrets Manager, ...)",
            "localemu/localemu:latest",
            4566,
            ("queue", "storage", "secrets"),
            env={"DASHBOARD_API_OPEN": "1", "PERSISTENCE": "1"},
            notes="An open-source AWS emulator (Apache-2.0 fork of LocalStack, 130+ services) on one port: the sqs / "
            "s3 drivers, get_secret(), boto3, the AWS CLI and Terraform work with endpoint_url. Credentials are not "
            "checked (test / test). Built-in dashboard with an S3 browser. For development and tests.",
            gui=({"port": 4566, "path": "/_localemu/dashboard", "label": "Dashboard", "login": "none"},),
            ready_path="/_localemu/health",
            group="AWS emulators",
        ),
        # ------------------------------------------------------------------ secrets
        "infisical": svc(
            "Infisical (secrets manager with web UI)",
            "infisical/infisical:latest",
            8080,
            ("secrets",),
            env={
                "ENCRYPTION_KEY": "{encryption_key}",
                "AUTH_SECRET": "{auth_secret}",
                "DB_CONNECTION_URI": "postgres://infisical:{password}@{container}-db:5432/infisical",
                "REDIS_URL": "redis://{container}-redis:6379",
                "SITE_URL": "http://{address}:{port}",
                "TELEMETRY_ENABLED": "false",
                "NODE_ENV": "production",
            },
            sidecars=(
                {"name": "db", "image": "postgres:16-alpine", "data": "/var/lib/postgresql/data",
                 "env": {"POSTGRES_USER": "infisical", "POSTGRES_PASSWORD": "{password}", "POSTGRES_DB": "infisical"},
                 "health": "pg_isready -U infisical -d infisical"},
                {"name": "redis", "image": "redis:7-alpine", "data": "/data",
                 "health": "redis-cli ping | grep -q PONG"},
            ),
            generate={"encryption_key": "hex16", "auth_secret": "b64_32"},
            ready_path="/api/status",
            notes="Open-source secrets manager (projects, environments, versions, audit log, access control) with "
            "its own PostgreSQL and Redis next to it. Open the web UI and create the admin account, then a project and "
            "a machine identity (Universal Auth): put its client id / secret and the project id in the env file and "
            "get_secret() / getSecret() read from Infisical. ENCRYPTION_KEY stays in the env file: keep it, the data "
            "cannot be read without it.",
            gui=({"port": 8080, "label": "Infisical", "login": "signup"},),
            group="Secrets",
        ),
        # ------------------------------------------------------------------ monitoring
        "grafana": svc(
            "Grafana (dashboards)",
            "grafana/grafana:11.3.0",
            3000,
            ("custom",),
            data="/var/lib/grafana",
            env={"GF_SECURITY_ADMIN_USER": "{user}", "GF_SECURITY_ADMIN_PASSWORD": "{password}",
                 "GF_ANALYTICS_REPORTING_ENABLED": "false"},
            ready_path="/api/health",
            backup="tar czf - -C /var/lib/grafana .",
            backup_ext="tar.gz",
            notes="Dashboards and alerts over Prometheus, Loki, PostgreSQL, ClickHouse and 100+ data sources.",
            gui=({"port": 3000, "label": "Grafana", "login": "user"},),
            connect={"env": _WEB_LOGIN, "connection": {"url": "http://{address}:{port}", "user": "{user}",
                                                       "password_env": "{prefix}_PASSWORD"}},
            group="Monitoring",
        ),
        "prometheus": svc(
            "Prometheus (metrics)",
            "prom/prometheus:v2.55.1",
            9090,
            ("custom",),
            data="/prometheus",
            ready_path="/-/ready",
            notes="Metrics database and query UI. Scrapes itself by default; add targets in "
            "/etc/prometheus/prometheus.yml (Console: sh). No login: keep it on a private network.",
            gui=({"port": 9090, "label": "Prometheus UI", "login": "none"},),
            connect={"env": _WEB, "connection": {"url": "http://{address}:{port}"}},
            group="Monitoring",
        ),
        "uptime-kuma": svc(
            "Uptime Kuma (uptime monitor)",
            "louislam/uptime-kuma:1",
            3001,
            ("custom",),
            data="/app/data",
            ready_path="/",
            backup="tar czf - -C /app/data .",
            backup_ext="tar.gz",
            notes="Checks HTTP, TCP, DNS, Docker containers ... every minute and alerts by mail, Slack, Telegram. "
            "Create the admin account on the first visit.",
            gui=({"port": 3001, "label": "Uptime Kuma", "login": "signup"},),
            connect={"env": _WEB, "connection": {"url": "http://{address}:{port}"}},
            group="Monitoring",
        ),
        "jaeger": svc(
            "Jaeger (tracing, OpenTelemetry)",
            "jaegertracing/all-in-one:1.62.0",
            16686,
            ("custom",),
            extra_ports=(4317, 4318),
            env={"COLLECTOR_OTLP_ENABLED": "true"},
            ready_path="/",
            notes="Distributed tracing: send OpenTelemetry traces to OTLP gRPC :4317 or HTTP :4318 and search them in "
            "the UI. Keeps traces in memory. No login: keep it on a private network.",
            gui=({"port": 16686, "label": "Jaeger UI", "login": "none"},),
            connect={"env": {"URL": "http://{address}:{port}", "OTLP_ENDPOINT": "http://{address}:{port_4318}"},
                     "connection": {"url": "http://{address}:{port}",
                                    "otlp_http": "http://{address}:{port_4318}",
                                    "otlp_grpc": "{address}:{port_4317}"}},
            group="Monitoring",
        ),
        # ------------------------------------------------------------------ identity
        "keycloak": svc(
            "Keycloak (login, SSO, OAuth2 / OIDC)",
            "quay.io/keycloak/keycloak:26.0",
            8080,
            ("custom",),
            data="/opt/keycloak/data",
            command=("start-dev",),
            env={"KC_BOOTSTRAP_ADMIN_USERNAME": "{user}", "KC_BOOTSTRAP_ADMIN_PASSWORD": "{password}",
                 "KC_HEALTH_ENABLED": "true"},
            ready_path="/realms/master",
            notes="Identity provider: users, groups, social login, MFA and OpenID Connect / OAuth2 tokens for your "
            "APIs. Runs in dev mode (H2 database in the volume, HTTP); put it behind HTTPS for production.",
            gui=({"port": 8080, "path": "/admin/", "label": "Admin console", "login": "user"},),
            connect={"env": {**_WEB_LOGIN, "ISSUER": "http://{address}:{port}/realms/master"},
                     "connection": {"url": "http://{address}:{port}",
                                    "issuer": "http://{address}:{port}/realms/master", "user": "{user}",
                                    "password_env": "{prefix}_PASSWORD"}},
            group="Identity",
        ),
        # ------------------------------------------------------------------ search and vector databases
        "meilisearch": svc(
            "Meilisearch (search engine)",
            "getmeili/meilisearch:v1.11",
            7700,
            ("custom",),
            data="/meili_data",
            env={"MEILI_MASTER_KEY": "{password}", "MEILI_ENV": "development", "MEILI_NO_ANALYTICS": "true"},
            ready_path="/health",
            notes="Typo-tolerant full-text search with a REST API and a search preview UI (the master key is the "
            "password).",
            gui=({"port": 7700, "label": "Search preview", "login": "token"},),
            connect={"env": {"URL": "http://{address}:{port}", "API_KEY": "{password}"},
                     "connection": {"url": "http://{address}:{port}", "api_key_env": "{prefix}_API_KEY"}},
            group="Search",
        ),
        "typesense": svc(
            "Typesense (search engine)",
            "typesense/typesense:27.1",
            8108,
            ("custom",),
            data="/data",
            command=("--data-dir", "/data", "--api-key", "{password}", "--enable-cors"),
            ready_path="/health",
            notes="Fast typo-tolerant search with a REST API (the API key is the password).",
            connect={"env": {"URL": "http://{address}:{port}", "API_KEY": "{password}"},
                     "connection": {"url": "http://{address}:{port}", "api_key_env": "{prefix}_API_KEY"}},
            group="Search",
        ),
        "qdrant": svc(
            "Qdrant (vector database)",
            "qdrant/qdrant:v1.12.4",
            6333,
            ("database",),
            extra_ports=(6334,),
            data="/qdrant/storage",
            env={"QDRANT__SERVICE__API_KEY": "{password}"},
            ready_path="/healthz",
            notes="Vector similarity search for embeddings (RAG, recommendations). REST on the port, gRPC on 6334; "
            "the API key is the password.",
            gui=({"port": 6333, "path": "/dashboard", "label": "Dashboard", "login": "token"},),
            connect={"env": {"URL": "http://{address}:{port}", "API_KEY": "{password}"},
                     "connection": {"url": "http://{address}:{port}", "api_key_env": "{prefix}_API_KEY"}},
            group="Databases",
        ),
        "clickhouse": svc(
            "ClickHouse (analytics database)",
            "clickhouse/clickhouse-server:24.8",
            8123,
            ("database",),
            extra_ports=(9000,),
            data="/var/lib/clickhouse",
            env={"CLICKHOUSE_USER": "{user}", "CLICKHOUSE_PASSWORD": "{password}", "CLICKHOUSE_DB": "{database}",
                 "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT": "1"},
            ready_path="/ping",
            notes="Column-store SQL for analytics and logs. HTTP on the port (SQL playground at /play), native "
            "protocol on 9000.",
            gui=({"port": 8123, "path": "/play", "label": "SQL playground", "login": "user"},),
            connect={"env": {"URL": "http://{address}:{port}", "USER": "{user}", "PASSWORD": "{password}"},
                     "connection": {"host": "{address}", "port": "{port}", "database": "{database}", "user": "{user}",
                                    "url_env": "{prefix}_URL", "password_env": "{prefix}_PASSWORD"}},
            group="Databases",
        ),
        "neo4j": svc(
            "Neo4j (graph database)",
            "neo4j:5",
            7687,
            ("database",),
            extra_ports=(7474,),
            data="/data",
            env={"NEO4J_AUTH": "neo4j/{password}"},
            notes="Graph database queried with Cypher over Bolt (the port); Neo4j Browser on 7474. The user is "
            "always neo4j.",
            gui=({"port": 7474, "label": "Neo4j Browser", "login": "user"},),
            connect={"env": {"URL": "bolt://{address}:{port}", "USER": "neo4j", "PASSWORD": "{password}"},
                     "connection": {"url": "bolt://{address}:{port}", "user": "neo4j",
                                    "password_env": "{prefix}_PASSWORD"}},
            group="Databases",
        ),
        # ------------------------------------------------------------------ messaging
        "mosquitto": svc(
            "Eclipse Mosquitto (MQTT broker)",
            "eclipse-mosquitto:2",
            1883,
            ("custom",),
            data="/mosquitto/data",
            command=("mosquitto", "-c", "/mosquitto-no-auth.conf"),
            notes="MQTT for IoT devices and sensors. Anonymous access: keep it on a private network.",
            connect={"env": {"URL": "mqtt://{address}:{port}"}, "connection": {"url": "mqtt://{address}:{port}"}},
            group="Queues and streams",
        ),
        # ------------------------------------------------------------------ automation and tools
        "n8n": svc(
            "n8n (workflow automation)",
            "n8nio/n8n:latest",
            5678,
            ("custom",),
            data="/home/node/.n8n",
            env={"N8N_SECURE_COOKIE": "false", "GENERIC_TIMEZONE": "UTC", "N8N_DIAGNOSTICS_ENABLED": "false"},
            ready_path="/healthz",
            backup="tar czf - -C /home/node/.n8n .",
            backup_ext="tar.gz",
            notes="Visual workflow automation with 400+ integrations; call your pskit functions with its HTTP node "
            "or the Lambda-compatible invoke API. Create the owner account on the first visit.",
            gui=({"port": 5678, "label": "n8n", "login": "signup"},),
            connect={"env": _WEB, "connection": {"url": "http://{address}:{port}"}},
            group="Automation",
        ),
        "portainer": svc(
            "Portainer (Docker UI)",
            "portainer/portainer-ce:2.21.4",
            9000,
            ("custom",),
            extra_ports=(9443,),
            data="/data",
            run_args=("-v", "/var/run/docker.sock:/var/run/docker.sock"),
            notes="Manage the server's containers, images, volumes and networks in the browser. Create the admin "
            "account within 5 minutes of the first start (otherwise restart it).",
            gui=({"port": 9000, "label": "Portainer", "login": "signup"},),
            connect={"env": _WEB, "connection": {"url": "http://{address}:{port}"}},
            group="Tools",
        ),
        "gitea": svc(
            "Gitea (Git hosting)",
            "gitea/gitea:1.22",
            3000,
            ("custom",),
            data="/data",
            ready_path="/",
            backup="tar czf - -C /data .",
            backup_ext="tar.gz",
            notes="Self-hosted Git with pull requests, issues, packages and Actions. Finish the install page on the "
            "first visit; the first account is the admin.",
            gui=({"port": 3000, "label": "Gitea", "login": "signup"},),
            connect={"env": _WEB, "connection": {"url": "http://{address}:{port}"}},
            group="Tools",
        ),
        "nginx-proxy-manager": svc(
            "Nginx Proxy Manager (reverse proxy, Let's Encrypt)",
            "jc21/nginx-proxy-manager:latest",
            81,
            ("custom",),
            extra_ports=(80, 443),
            data="/data",
            ready_path="/",
            notes="Point domains at your functions (port 8080) and services with free HTTPS certificates, from a web "
            "UI. First login admin@example.com / changeme (you are asked to change it). Needs ports 80 and 443 free.",
            gui=({"port": 81, "label": "Admin UI", "login": "signup"},),
            connect={"env": _WEB, "connection": {"url": "http://{address}:{port}"}},
            group="Web",
        ),
    }
