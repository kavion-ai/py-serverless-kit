"""Write the first concept cards. Facts come from docs/ and config/schema.py."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KNOW = ROOT / "ai-agent" / "training" / "knowledge"
CARDS = KNOW / "cards" / "concept"
JSONL = KNOW / "cards.jsonl"

PAGES: list[dict] = []


def add(cid: str, title: str, tags: list[str], providers: list[str], sources: list[str], text: str) -> None:
    PAGES.append(
        {
            "id": cid,
            "kind": "concept",
            "title": title,
            "tags": tags,
            "providers": providers,
            "text": text.strip() + "\n",
            "sources": sources,
        }
    )


add(
    "concept-config-file",
    "Concept: the pskit.yml file",
    ["config", "pskit.yml"],
    [],
    ["docs/configuration.md#top-level", "docs/configuration.md#configuration-reference-pskityml"],
    """
# Concept: the pskit.yml file

pskit looks for `pskit.yml`, `pskit.yaml`, `serverless_kit.yml`, or `serverless_kit.yaml` in the current directory. Pass `-c FILE` to use another file. Unknown keys are rejected, so a typo fails fast.

The documented top-level keys are `service` (required), `provider` (required), `package`, `functions`, `workflows`, `resources`, `hooks`, `custom`, `providers`, `stages`, and `extends`. `service` is a string of 2–32 characters: lowercase letters, digits, and `-`, starting with a letter. `provider` may be a mapping or the shorthand string `provider: aws`, which means `provider: {name: aws}`.

`functions` maps a name to a function. Names start with a letter and use letters, digits, `-`, and `_`, with a maximum of 63 characters. `workflows` and `resources` are maps and default to empty. `hooks` maps a hook name to a list of shell commands. `custom` is any mapping and exists so `${self:custom...}` can read it. `providers` and `stages` hold overrides. `extends` names another file to inherit.

`package` has its own section. Deployed function names are built later as `<service>-<stage>-<function>`, lowercased, with invalid characters replaced and long names shortened with a stable hash.

Sources: `docs/configuration.md#configuration-reference-pskityml`, `docs/configuration.md#top-level`
""",
)

add(
    "concept-provider",
    "Concept: the provider block",
    ["config", "provider"],
    [],
    [
        "docs/configuration.md#provider",
        "docs/configuration.md#default-runtime",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Concept: the provider block

`provider.name` is required unless you pass `--provider`. The names in `PROVIDERS` are aws, azure, gcp, alibaba, oracle, ibm, digitalocean, tencent, huawei, cloudflare, and onprem. `region` is a string and falls back to the provider default. `stage` defaults to `dev` and must match `[a-z][a-z0-9-]{0,15}`. `--stage` overrides the file.

`runtime` is one of python3.9 through python3.14. If you do not pin it, pskit uses python3.12 when the cloud supports it, otherwise the newest supported version below 3.12: python3.11 on DigitalOcean, IBM, and Oracle, and python3.10 on Tencent. Pinning a runtime the cloud lacks is a `pskit validate` error.

`memory` defaults to 256 MB and is an int from 64 to 32768. `timeout` defaults to 30 seconds, from 1 to 3600, and must also be at or under that provider's maximum. `architecture` is `x86_64` or `arm64` and defaults to `x86_64`. The doc says it is used by AWS and for pip wheel selection.

`environment` and `tags` are maps. Environment values are converted to strings. Tags merge with `pskit-service`, `pskit-stage`, and `managed-by`. `log_retention_days` is an int or null and defaults to 14 for the AWS CloudWatch log group. `options` holds provider-specific settings. `state` and `terraform` configure the Terraform backend and the Terraform binary.

Sources: `docs/configuration.md#provider`, `docs/configuration.md#default-runtime`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "concept-functions",
    "Concept: functions in pskit.yml",
    ["config", "functions"],
    [],
    ["docs/configuration.md#functions", "src/py_serverless_kit/config/schema.py"],
    """
# Concept: functions in pskit.yml

Each entry under `functions` needs a `handler`. The schema requires `package.module.function` or `module:function`. The doc also writes it as `package.module.function` or `package.module:function`, relative to `package.source`.

Optional fields and their defaults: `description` is an empty string. `enabled` defaults to true. False keeps the function in the file and skips it on deploy. Workflows take `enabled` too. `runtime`, `memory`, `timeout`, and `architecture` inherit from `provider` when omitted. Function `memory` is 64–32768 and `timeout` is 1–3600 when set. `environment` and `tags` default to empty maps and are merged over the provider-level maps. `events` defaults to an empty list, which means an invoke-only function. `concurrency` is an int of at least 0 when set. The doc describes it as reserved concurrency or max instances where the provider supports it. `iam` is added to the provider-level statements. `options` defaults to an empty mapping and is merged into the provider's function resource.

Two functions cannot declare the same `METHOD /path`. The schema labels a function for the dashboard from its event types: no events is invoke-only, only http is http, only schedule is scheduled, http plus anything else is http+event, and any other mix is event-driven.

Sources: `docs/configuration.md#functions`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "concept-events",
    "Concept: events",
    ["events", "triggers"],
    [],
    ["docs/events.md#events-triggers", "src/py_serverless_kit/config/schema.py"],
    """
# Concept: events

Each function has a list of `events`. Each entry is a single-key mapping. The key is the trigger type. `EVENT_TYPES` in `config/schema.py` is http, schedule, queue, storage, topic, and smtp. A function with no events is invoke-only: the events doc says it can be called by workflows, by `invoke()`, or by the provider's own CLI.

The events doc's support table marks http on every provider, with a note that Huawei HTTP needs `provider.options.apig_instance_id`. Schedule is absent on Oracle and IBM. Queue is marked for AWS SQS, GCP Pub/Sub, Azure Storage Queue, and on-prem files. Storage is marked for AWS S3, GCP GCS, Azure Blob created only, Alibaba OSS, Oracle Object Storage, Tencent COS, Huawei OBS, and an on-prem directory. Topic is marked for AWS SNS, GCP Pub/Sub, Azure Service Bus, Alibaba MNS, Huawei SMN, and on-prem files. smtp is marked only for the on-prem SMTP service. `pskit validate` reports an error for a trigger or option the selected provider cannot honour.

An smtp event is written `- smtp: {resource: inbound-mail}` on the SMTP server resource. The handler gets from, to, cc, subject, text, html, headers, and attachments, plus the same mail as an Amazon SES event at `Records[0].ses`.

Sources: `docs/events.md#events-triggers`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "concept-event-http",
    "Concept: HTTP events",
    ["events", "http", "cors"],
    [],
    ["docs/events.md#http", "src/py_serverless_kit/config/schema.py"],
    """
# Concept: HTTP events

The shorthand `- http: GET /users/{id}` sets the method and path. `- http: /health` is GET. The long form uses `path`, `method`, `cors`, `auth`, and `authorizer`. Methods in the schema are GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, and ANY. A star is stored as ANY. The default path is `/` and the default method is GET.

`{name}` matches one segment and lands in `event.http.path_params["name"]`. `{name+}` matches the rest of the path and is only allowed as the last segment. Parameter names are identifiers, so `{user_id}` is valid and `{user-id}` is not. The runtime matches routes itself, so path params and 405 Method Not Allowed work on clouds with no API gateway (GCP, IBM, DigitalOcean, Cloudflare), including when the platform adds or strips a path prefix. Two functions may not declare the same `METHOD /path`.

`cors: true` uses the defaults. A mapping may set `origins` (default `["*"]`), `methods` (default GET POST PUT PATCH DELETE OPTIONS), `headers` (default Content-Type, Authorization, X-Requested-With), `expose_headers`, `allow_credentials` (default false), and `max_age` (default 600). The runtime answers OPTIONS preflights with 204 and adds Access-Control-* headers on every cloud. AWS also configures CORS on the HTTP API.

`auth` is none, iam, jwt, or key. none is public on all providers. iam is aws, gcp, and huawei. jwt is aws only and needs `authorizer.issuer` and `authorizer.audience`. key is azure and huawei. Tencent's API Gateway has no PATCH. On Tencent and Huawei, `{path+}` becomes a prefix route. On Oracle it becomes `{path*}`.

Sources: `docs/events.md#http`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "concept-event-schedule",
    "Concept: schedule events",
    ["events", "schedule"],
    [],
    ["docs/events.md#schedule"],
    """
# Concept: schedule events

A schedule is a rate or a cron, not both. Shorthand `- schedule: 5 minutes` is a rate. Shorthand `- schedule: "0 3 * * *"` is a 5-field cron. The long form uses exactly one of `rate` or `cron`, plus optional `input`, `timezone` (default UTC), `enabled` (default true), and `name`. A rate looks like `<n> minute(s)|hour(s)|day(s)`. The handler gets `event.type == "schedule"` and `event.data` equal to `input`.

pskit converts that syntax per cloud. AWS uses EventBridge Scheduler (`rate(5 minutes)` or cron with a day-of-week conversion and `?`). GCP Cloud Scheduler uses 5-field cron, and rates become cron such as `*/5 * * * *`. Azure uses a 6-field NCRONTAB and is always UTC on Linux Consumption. Alibaba uses `@every 5m` or a 6-field cron with `CRON_TZ=` when a timezone is set. Tencent uses a 7-field cron. Huawei uses `Rate` such as `5m` or a 6-field cron with `?`. DigitalOcean and Cloudflare use 5-field cron. On-prem uses an in-process scheduler: a rate in seconds, or 5-field cron. A rate such as `7 minutes` is valid on-prem.

A rate that cannot be expressed as cron on cron-only clouds fails validation. Use a divisor of 60 minutes or 24 hours. `timezone` is honoured by AWS, GCP, and Alibaba in the cron form. Azure ignores it with a warning.

Sources: `docs/events.md#schedule`
""",
)

add(
    "concept-handlers",
    "Concept: handler signatures",
    ["handlers", "runtime"],
    [],
    [
        "docs/handlers.md#handler-api",
        "docs/handlers.md#handler-signatures",
        "docs/handlers.md#get_secret-secrets-on-every-provider",
    ],
    """
# Concept: handler signatures

The handler API is importable from `py_serverless_kit` and behaves the same on every cloud. The runtime uses only the standard library and is copied into every deployment bundle. You do not add `py-serverless-kit` to the function's `requirements.txt`.

The documented import list is Event, EventType, HttpRequest, Record, Headers, Context, Response, HttpError, BadRequest, Unauthorized, Forbidden, NotFound, MethodNotAllowed, Conflict, UnprocessableEntity, TooManyRequests, BatchResult, and invoke. Later sections also import `invoke` on its own, and `get_secret`, `get_secrets`, `put_secret`, and `SecretNotFound`.

A handler may take `(event, ctx)`, or only `event`. An `async def` is awaited. `handler` in pskit.yml is `package.module.function` or `package.module:function`, relative to `package.source`.

`get_secret("db-password")` reads a plain secret. `get_secret("stripe", "webhook")` reads one field of a JSON secret. `default=""` avoids `SecretNotFound`. `put_secret` writes on Vault / OpenBao and Secrets Manager. The store comes from `PSKIT_SECRETS_DRIVER`: `vault`, `aws`, or `env` (the default). Values are cached for 60 seconds. `store="other"` reads `PSKIT_OTHER_*`.

Sources: `docs/handlers.md#handler-api`, `docs/handlers.md#handler-signatures`, `docs/handlers.md#get_secret-secrets-on-every-provider`
""",
)

add(
    "concept-event-object",
    "Concept: the Event object",
    ["handlers", "event"],
    [],
    [
        "docs/handlers.md#event",
        "docs/handlers.md#httprequest",
        "docs/handlers.md#record",
        "src/py_serverless_kit/runtime/event.py",
    ],
    """
# Concept: the Event object

`Event.type` in the handlers doc is listed as http, schedule, queue, storage, topic, invoke, or workflow, with constants on `EventType`. `EventType` in `runtime/event.py` also defines `SMTP = "smtp"`. `EventType.ALL` is http, schedule, queue, storage, topic, invoke, workflow, and smtp. The code comment says smtp `data` is the parsed mail. The handlers table omits smtp. The code wins. invoke and workflow are runtime types. They are not entries in `EVENT_TYPES`.

Other attributes: `provider` is the cloud name or `local`. `function` is the logical name. `http` is an `HttpRequest` or None. `records` is a list of `Record` for queue, topic, and storage batches. `data` is the payload of schedule, invoke, and workflow events. `time` is UTC from the platform, or now. `source` is optional, for example a queue ARN. `raw` is the untouched native payload. Helpers are `is_http`, `is_batch`, `json()`, iteration over `records`, and `to_dict()`.

`HttpRequest` has upper-case `method`, `path`, `route`, case-insensitive `headers` (repeated headers joined with `", "`), `query` (last value wins), `multi_query`, `path_params`, `body` as bytes, `source_ip`, `content_type`, and `cookies`. `text()`, `json(default=...)`, and `form()` decode the body. Invalid or empty JSON raises `BadRequest` unless you pass `default`.

A `Record` has `id`, `body`, `attributes`, `source`, and storage fields `bucket`, `key`, `size`, and `action` (`created` or `deleted`), plus `raw`, `text()`, and `json()`.

Sources: `docs/handlers.md#event`, `docs/handlers.md#httprequest`, `docs/handlers.md#record`, `src/py_serverless_kit/runtime/event.py`
""",
)

add(
    "concept-responses",
    "Concept: return values and HTTP errors",
    ["handlers", "http"],
    [],
    ["docs/handlers.md#returning-a-response", "docs/handlers.md#errors", "docs/handlers.md#context"],
    """
# Concept: return values and HTTP errors

An HTTP handler's return value is converted. `Response(...)` is used as is. `None` becomes 204 No Content. A dict, list, number, dataclass, or pydantic model becomes JSON 200. A str is `text/plain` 200. Bytes are `application/octet-stream` 200. A pair `(body, status)` or a triple `(body, status, headers)` is Flask-style. JSON serialisation handles datetime and date as ISO 8601, plus Decimal, UUID, set, and objects with `model_dump()` or `to_dict()`.

`Response` constructors in the doc are `json`, `text`, `html`, `binary`, `redirect` (status 302 in the example), and `no_content`. `set_cookie` takes `max_age`, `path`, `http_only`, `secure`, and `same_site`. Binary bodies are base64-encoded for gateways. For a non-HTTP event, the return value goes back to the caller as is, including the workflow's next state and the result of `invoke()`.

Raise an `HttpError` subclass for a JSON error. The status table is BadRequest 400, Unauthorized 401, Forbidden 403, NotFound 404, MethodNotAllowed 405, Conflict 409, UnprocessableEntity 422, and TooManyRequests 429.

`Context` carries `request_id`, `function`, `provider`, `service`, `stage`, `region`, `memory_mb` when the platform reports it, `remaining_time_ms()` (or None), a `logger` with function, request_id, and provider bound, `env` as `os.environ`, and `raw` as the native context.

Sources: `docs/handlers.md#returning-a-response`, `docs/handlers.md#errors`, `docs/handlers.md#context`
""",
)

add(
    "concept-variables",
    "Concept: config variables",
    ["config", "variables", "secrets"],
    [],
    ["docs/configuration.md#variables"],
    """
# Concept: config variables

pskit resolves four variable forms in the config. `${env:NAME}` is an environment variable and is an error if unset. `${env:NAME, default}` uses `default` when it is unset. `${opt:stage}`, `${opt:provider}`, and `${opt:region}` are the effective CLI values. `${opt:x, default}` is allowed. `${self:dotted.path}` reads the merged config, for example `${self:service}` or `${self:custom.table}`. `${file(path.json)}` reads a file relative to the config. `.json` and `.yml` are parsed. Other files are stripped text.

When a value is exactly one variable, its type is kept, so `memory: ${self:custom.mem}` stays an int. Variables can nest across passes. Unresolved variables are reported together.

Two forms are not resolved by pskit and are passed through. `${tf:<terraform expression>}` becomes a live Terraform reference, for example `${tf:aws_dynamodb_table.orders.arn}` in an IAM statement or an environment value. Every other `${` in user values is escaped, so Terraform does not interpret it. Any other `${...}`, such as an IAM policy variable like `${aws:username}`, stays literal.

The doc says not to put secrets in YAML. Use `${env:...}` for CI-provided values, or reference a secret manager with `${tf:...}`.

Sources: `docs/configuration.md#variables`
""",
)

add(
    "concept-overrides",
    "Concept: providers, stages, and extends",
    ["config", "multi-cloud", "stages"],
    [],
    [
        "docs/configuration.md#providers-per-cloud-overrides",
        "docs/configuration.md#stages-per-stage-overrides",
        "docs/configuration.md#extends-inherit-files",
        "docs/configuration.md#precedence-later-wins",
    ],
    """
# Concept: providers, stages, and extends

`providers:` holds per-cloud overrides. The block for the active provider (`provider.name` or `--provider`) is deep-merged into the config. Inside a block, ProviderConfig keys may be written directly as shorthand for `provider: {...}`: region, stage, runtime, memory, timeout, architecture, environment, tags, iam, log_retention_days, options, state, and terraform. Any top-level key can be overridden too, including `functions`.

Setting `enabled: false` on a function or workflow under one provider keeps it for the other clouds and skips it there. Replacing a function's `events` list replaces the list. It does not append. Disabled functions and workflows are warnings from `pskit validate`. A workflow that calls a disabled function is an error. The doc says studio writes these overrides from the Deploy page, a provider switch, and the function wizard.

`stages.<name>` deep-merges that stage. The example sets `provider.memory` and one function's `concurrency` for prod. `extends` is one file or a list. Relative paths resolve from the extending file. A circular extends is an error.

Precedence, later wins: for each file in the extends chain, parents first, that file's own values, then that file's `providers.<active>` block, so a child's explicit values beat a parent's per-provider overrides. Then `stages.<active>` across all files, child wins. Then `stages.<active>.providers.<active>`. Then CLI flags `--provider`, `--stage`, and `--region`. Dicts are deep-merged. Lists are replaced.

Sources: `docs/configuration.md#providers-per-cloud-overrides`, `docs/configuration.md#stages-per-stage-overrides`, `docs/configuration.md#extends-inherit-files`, `docs/configuration.md#precedence-later-wins`
""",
)

add(
    "concept-resources",
    "Concept: resources",
    ["resources", "config"],
    [],
    [
        "docs/configuration.md#resources",
        "src/py_serverless_kit/config/schema.py",
        "ai-agent/training/knowledge/conflicts.md",
    ],
    """
# Concept: resources

`resources` maps a name to a service the functions use. pskit creates a managed resource. `external: true` means it already exists, or runs outside pskit, and pskit does not create or destroy it. Every bound function gets `PSKIT_RESOURCE_<KEY>_*` variables. Handlers read them with `resource("key")`.

`RESOURCE_TYPES` in `config/schema.py` is storage, queue, topic, database, cache, custom, and smtp. The type list in `docs/configuration.md#resources` omits smtp. The code wins, and the same gap is recorded for `docs/resources.md`. database, cache, and custom must be `external: true`. The schema rejects a non-event resource type that is not external, with the message that pskit does not create that type.

`name` defaults to the key, or the tail of `connection.arn`. `connection` is a map of scalar values exposed to handlers. Keys start with a letter and use letters, digits, or `_`. Nested maps and lists are rejected. `functions` defaults to every user function. `options` is provider-specific.

queue, storage, and topic events can name a resource: `- queue: {resource: jobs}`. The event then uses the resource's native name and `existing` follows `external`.

Sources: `docs/configuration.md#resources`, `src/py_serverless_kit/config/schema.py`, `ai-agent/training/knowledge/conflicts.md`
""",
)

add(
    "concept-iam",
    "Concept: IAM statements",
    ["iam", "config"],
    [],
    [
        "docs/configuration.md#provider",
        "docs/configuration.md#functions",
        "docs/handlers.md#invoke-calling-another-function",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Concept: IAM statements

`provider.iam.statements` is a list of mappings with `effect`, `actions`, and `resources`. In the schema, `effect` is Allow or Deny and defaults to Allow. `actions` is required. `resources` defaults to `["*"]`. The configuration doc says the same defaults, and that the statements are AWS-style. Clouds that do not map them ignore them with a warning.

`provider.iam.role` is an optional string. The doc says it uses an existing role or agency instead of creating one. The schema description says an existing role or service account.

A function may have its own `iam` block in the same shape. The doc says those statements are added to the provider-level ones, and that a dedicated role is created on AWS. A statement can contain a Terraform reference such as `${tf:aws_dynamodb_table.orders.arn}`. That form is passed through. pskit does not resolve it as a config variable.

`invoke()` on AWS needs `lambda:InvokeFunction` in `iam.statements`, plus `py-serverless-kit[aws]` and `boto3` in requirements, as described in the handlers doc.

Sources: `docs/configuration.md#provider`, `docs/configuration.md#functions`, `docs/handlers.md#invoke-calling-another-function`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "concept-package",
    "Concept: packaging",
    ["package", "deploy"],
    [],
    ["docs/configuration.md#package"],
    """
# Concept: packaging

`package.source` defaults to `.`, the directory relative to the config whose files are bundled. `include` defaults to `["**/*"]`, using gitignore-style globs where `**` means any depth. `exclude` defaults to an empty list and is added to the built-in excludes. `requirements` defaults to `requirements.txt`. Lines that name `py-serverless-kit` are dropped because the runtime is vendored. `pip_args` defaults to an empty list of extra pip install flags. `vendor` follows the provider default. True forces `pip install` into the bundle. False ships `requirements.txt` instead.

Always excluded: `.git/**`, `.hg/**`, `.pskit/**`, `.terraform/**`, `.venv/**`, `venv/**`, `env/**`, `**/__pycache__/**`, `**/*.pyc`, `**/*.pyo`, `.pytest_cache/**`, `.mypy_cache/**`, `.ruff_cache/**`, `.idea/**`, `.vscode/**`, `node_modules/**`, `tests/**`, `dist/**`, `build/**`, `*.egg-info/**`, `**/.DS_Store`, `.env`, `.env.*`, `**/*.tfstate`, `**/*.tfstate.*`, `pskit*.yml`, `pskit*.yaml`, and `serverless_kit*.yml`.

Providers that build remotely (GCP, Azure, Oracle, Cloudflare) get a `requirements.txt` in the bundle. AWS, Alibaba, IBM, DigitalOcean, Tencent, and Huawei get dependencies pip-installed into the zip as Linux `manylinux2014` wheels for the target runtime and architecture.

Sources: `docs/configuration.md#package`
""",
)

add(
    "concept-hooks",
    "Concept: hooks",
    ["hooks", "deploy"],
    [],
    [
        "docs/configuration.md#hooks",
        "src/py_serverless_kit/core/deployer.py",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Concept: hooks

`hooks` maps a hook name to a list of shell commands. The schema allows only `before_package`, `after_package`, `before_deploy`, `after_deploy`, `before_remove`, and `after_remove`. Any other name fails validation with `unknown hooks`. An empty map is the default.

`Deployer.run_hook` prints `hook <name>: <cmd>`, then runs each command with `shell=True` in the project root. The environment is the current environment plus `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER`, and `PSKIT_WORK_DIR`. A non-zero exit raises `DeployError` with the hook name, the return code, and the command.

`package` runs `before_package` after validation and before the artifact is built, and `after_package` after `main.tf.json` is written. `deploy` calls `package`, then `before_deploy`, then Terraform, then `after_deploy` after the deployment record is saved. `plan` calls `package`, so the package hooks run, and it does not call the deploy hooks. `remove` runs `before_remove` before init and destroy, and `after_remove` after the record is marked removed.

The documented example runs `python scripts/gen_schema.py` on `before_package` and `python scripts/smoke_test.py` on `after_deploy`. Those paths are examples, not built-in scripts. Hooks are not function events.

Sources: `docs/configuration.md#hooks`, `src/py_serverless_kit/core/deployer.py`, `src/py_serverless_kit/config/schema.py`
""",
)


add(
    "concept-workflows",
    "Concept: workflows",
    ["workflows"],
    [],
    [
        "docs/workflows.md#workflows-state-machines",
        "docs/workflows.md#workflow-keys",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Concept: workflows

A workflow chains functions with branching, retries, waits, parallel branches, and fan-out. You define it once under `workflows` in pskit.yml. pskit runs it natively as AWS Step Functions, Google Cloud Workflows, or, when you set `engine: native`, Azure Logic Apps. Every other target uses the embedded engine inside an auto-generated `<workflow>-orchestrator` function. On premises that function runs inside the long-lived host, so the workflow is not cut off by a function timeout. `pskit workflow run` uses the same embedded engine locally.

Required keys are `start_at` (it must name a state) and `states`. `description` defaults to an empty string. `engine` defaults to `auto`: native on aws and gcp, embedded elsewhere, including Azure until you opt in. `native` is an error on a cloud without a native engine. `embedded` forces the embedded engine everywhere. `enabled` defaults to true. False keeps the workflow in the file and skips it on deploy. `timeout` is the AWS TimeoutSeconds, the embedded orchestrator function timeout capped at the provider maximum, and a limit the embedded engine enforces by ending the run `TIMED_OUT`.

`options.type` is AWS only: `STANDARD` or `EXPRESS`, default `STANDARD`. `options.http` is embedded only and defaults to true. False removes the orchestrator's HTTP trigger. `options.start_on_entry` is on premises only and defaults to true. `options.sync` is Azure native only and defaults to true. False drops the Response actions so the caller gets 202 at once.

Every `next`, `default`, and `catch.next` must name a state. Every `function` must exist under `functions`. Task handlers receive `event.type == "workflow"` and the state input in `event.data`. Their return value is the task result. Error names in `retry` and `catch` are the Python exception class names the handler raises.

Sources: `docs/workflows.md#workflows-state-machines`, `docs/workflows.md#workflow-keys`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "concept-workflow-states",
    "Concept: workflow states",
    ["workflows"],
    [],
    [
        "docs/workflows.md#state-types",
        "docs/workflows.md#data-flow",
        "docs/workflows.md#retry-and-catch",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Concept: workflow states

State types are task, choice, wait, pass, parallel, map, succeed, and fail. A task calls `function` and may set `input_path`, `result_path`, `retry`, `catch`, and `timeout_seconds`. A choice has `choices` and an optional `default`. With no match and no default the run fails with `States.NoChoiceMatched`. A wait sleeps for `seconds` or `seconds_path`. A pass injects `result` or passes the input through. Parallel runs `branches` at the same time and the result is a list, one item per branch. Map runs `iterator` for each item from `items_path`, with optional `max_concurrency`, and the result is a list. Succeed finishes with the current data. Fail finishes with `error` and `cause`.

A task, wait, pass, parallel, or map without `next` is treated as `end: true`. The schema sets `end` in that case. Every state can have a `comment`.

JSON paths are `$`, `$.a.b`, `$.items[0]`, and `$['key']`. `input_path` selects what the task receives. The default is `$`. `result_path` of `$` replaces the state data with the result. `$.payment` stores the result under that key. `null` discards the result. The schema default for `result_path` is `$`.

Retry `errors` are exception class names. `"*"` or `States.ALL` means any. Defaults in the schema and the doc are `max_attempts` 3, `interval_seconds` 1, and `backoff_rate` 2.0. `max_delay_seconds` is optional. The first matching retrier is used. When retries are exhausted, the first matching catcher routes to `next`. A catch `result_path` defaults to `$.error` and stores `error` and `cause`. With no match the run fails. A rule whose variable is missing or the wrong type is false, not a failure.

Sources: `docs/workflows.md#state-types`, `docs/workflows.md#data-flow`, `docs/workflows.md#retry-and-catch`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "concept-workflow-engines",
    "Concept: workflow engines and commands",
    ["workflows", "cli"],
    [],
    [
        "docs/workflows.md#engines",
        "docs/workflows.md#embedded-orchestrator",
        "docs/workflows.md#commands",
    ],
    """
# Concept: workflow engines and commands

AWS deploys `aws_sfn_state_machine` plus an IAM role that can invoke the task Lambdas. GCP deploys `google_workflows_workflow`. Tasks are OIDC-authenticated HTTP calls. Azure with `engine: native` deploys a Logic App. Tasks call `/_pskit/invoke/<function>` with the function key. Everywhere else, or with `engine: embedded`, pskit adds `<workflow>-orchestrator`. It runs the state machine and calls task handlers in-process in the same bundle.

Invoke the embedded orchestrator with `POST /workflows/<workflow>` and a JSON body when HTTP is available and `options.http` is not false, or invoke it directly. On a cloud the response is synchronous: status `SUCCEEDED` with `output`, or HTTP 500 with status `FAILED`. On premises the host answers 202 with `execution_id` at once, and `?wait=true` returns the result. The run can be listed, followed, and cancelled.

On premises, a workflow whose first state is a task also starts when that function runs on its own, unless `options.start_on_entry` is false. The call's input is the workflow input. The function does not run twice. An HTTP status of 400 or more starts nothing. Other clouds do not do this.

The whole embedded run must fit in one function invocation. The doc gives examples of 900 s on AWS, Huawei, and Tencent, 600 s on Azure, and 120 s on IBM. `pskit validate` warns when a long wait will not fit. GCP uses only the first retry rule, and only on task states. Azure Logic Apps also uses only the first retry rule, ignores the errors filter and `backoff_rate`, runs map iterations one at a time, and stops after 5000 states or `timeout` (default 1 hour).

```
pskit workflow run order-pipeline -i "{\"amount\": 50}"
pskit workflow show order-pipeline --format asl
pskit workflow executions order-pipeline --status RUNNING
```

`workflow run` exits 2 when the run fails. Wait states are skipped unless `--sleep` is set. `--history` prints the execution history. Deployed start, status, and cancel work against the on-premises host, AWS Step Functions, and Google Cloud Workflows.

Sources: `docs/workflows.md#engines`, `docs/workflows.md#embedded-orchestrator`, `docs/workflows.md#commands`
""",
)

add(
    "concept-terraform-state",
    "Concept: Terraform state",
    ["terraform", "state"],
    [],
    [
        "docs/architecture.md#state-handling",
        "docs/architecture.md#deploy-pipeline",
        "docs/configuration.md#state-remote-terraform-backend",
        "docs/configuration.md#terraform",
    ],
    """
# Concept: Terraform state

Each provider and stage has its own directory, `.pskit/<provider>-<stage>/`, with its own Terraform workspace and state. `aws-dev` and `gcp-prod` do not share state. By default the state file is `terraform.tfstate` in that directory. pskit writes a `.gitignore` inside `.pskit/`, and the architecture doc says not to commit `.pskit/`.

For a team or CI, set `provider.state` to a remote backend:

```text
provider:
  state:
    backend: s3
    config:
      bucket: my-tf-state
      key: orders/${opt:stage}.tfstate
      region: us-east-1
      dynamodb_table: tf-locks
```

`backend` is any Terraform backend type. The doc names s3, gcs, azurerm, http, and remote. `config` is that backend's settings. The architecture doc names S3 with a DynamoDB lock, GCS, azurerm, and Terraform Cloud as the team options. When `provider.state` is set, the local `terraform.tfstate` line in the deploy diagram does not apply.

`provider.terraform.binary` autodetects `terraform`, then `tofu`, or uses `PSKIT_TERRAFORM_BIN`. `required_version` defaults to `>= 1.5.0`. User strings in the generated JSON are escaped (`${` becomes `$${`) unless they are written as `${tf:...}`.

Sources: `docs/architecture.md#state-handling`, `docs/architecture.md#deploy-pipeline`, `docs/configuration.md#state-remote-terraform-backend`, `docs/configuration.md#terraform`
""",
)

add(
    "concept-deployment-json",
    "Concept: deployment.json",
    ["deploy", "dashboard"],
    [],
    [
        "src/py_serverless_kit/core/describe.py",
        "src/py_serverless_kit/core/deployer.py",
        "docs/dashboard.md#where-the-data-comes-from",
        "docs/architecture.md#deploy-pipeline",
    ],
    """
# Concept: deployment.json

After Terraform, `core/describe.py` writes `.pskit/<provider>-<stage>/deployment.json`. The constant is `RECORD_FILE`. `build_record` reads the config and the Terraform output named `pskit`. `pskit info --json` prints the same record. The dashboard reads every `.pskit/*/deployment.json`.

The record has `schema` 1 and `key` `<provider>-<stage>`. `status` passed into `build_record` defaults to `deployed`. `pskit remove` sets that file's status to `removed`. When nothing is deployed, `pskit dashboard` renders the configured functions as a `local` record. Other fields are `service`, `stage`, `provider`, `provider_display`, `provider_tier`, `region`, `endpoint` from the pskit output, `deployed_at` as a UTC timestamp, `pskit_version`, `config_file`, `artifact`, `functions`, `workflows`, `resources`, and `outputs`. `outputs` is every Terraform output except the `pskit` key.

Each function row includes the logical name, the cloud `resource_name`, handler, kind, runtime, memory, timeout, architecture, event summaries, `environment_keys`, and id, arn, url, and console when the output has them. A workflow row stores the engine, `start_at`, each state's type, the task function names, and id, url, and console. Resource rows store the key, type, whether it is external, the native name, bound functions, and `connection_keys` only. `resource_records` does not copy connection values, because they may hold secrets.

Sources: `src/py_serverless_kit/core/describe.py`, `src/py_serverless_kit/core/deployer.py`, `docs/dashboard.md#where-the-data-comes-from`, `docs/architecture.md#deploy-pipeline`
""",
)

add(
    "concept-dashboard",
    "Concept: the dashboard",
    ["dashboard"],
    [],
    [
        "docs/dashboard.md#dashboard",
        "docs/dashboard.md#what-it-shows",
        "docs/dashboard.md#live-mode",
        "docs/dashboard.md#security",
    ],
    """
# Concept: the dashboard

The dashboard is one self-contained HTML page. `pskit deploy` and `pskit remove` regenerate `.pskit/dashboard/index.html`. A static file shows deployments, functions, triggers, endpoints, ids, workflows, resources, and outputs as of the last deploy. You can open it from disk or host it. Live mode is `pskit dashboard --serve`. It re-reads records on refresh and adds host health and invocation stats on premises, logs, and workflow executions.

```
pskit dashboard --open
pskit dashboard --serve --open --port 9000
```

`--serve` binds 127.0.0.1 and port 8765 unless you change them. `-o` writes the HTML somewhere else. `-d` is the project root.

Overview has summary cards and a table of deployments with provider, tier, status (`deployed`, `removed`, or `local`), region, endpoint, and last update. A deployment page has Functions, Workflows, Executions, Logs, Resources, and Outputs. The URL hash keeps the deployment and tab, for example `#/onprem-dev/executions`. User data is rendered as text. Only `http(s)` URLs become links.

Live logs can tail, list streams, and delete on premises and AWS. GCP and Azure are read-only. Executions can be listed, started, followed, and cancelled for on-premises, AWS Step Functions, and GCP Workflows. A static page says those tabs need `--serve`.

Security: loopback is the default. `--host 0.0.0.0` prints a warning because anyone who can reach the port can read logs and start or cancel executions. A foreign Host header gets 421. POST requires `content-type: application/json`. Admin tokens and cloud credentials stay on the server. The page contains resource names, URLs, and ids, so the doc says to treat it as internal.

Sources: `docs/dashboard.md#dashboard`, `docs/dashboard.md#what-it-shows`, `docs/dashboard.md#live-mode`, `docs/dashboard.md#security`
""",
)

add(
    "concept-runtime",
    "Concept: the runtime",
    ["runtime", "architecture"],
    [],
    [
        "docs/architecture.md#runtime-flow",
        "docs/architecture.md#bundle-layout",
        "CLAUDE.md",
    ],
    """
# Concept: the runtime

Deploy-time is the CLI: pskit.yml becomes a zip and Terraform JSON, then Terraform runs. Run-time is `py_serverless_kit.runtime`, copied into every bundle. It uses only the standard library. CLAUDE.md says it must run on Python 3.9: no third-party imports, no `match`, and no runtime-evaluated union types. The rest of the package also supports Python 3.9.

A native event hits a generated shim, then `runtime/adapters/<cloud>.py`. `to_event` builds an `Event`. `to_context` builds a `Context`. `runtime/dispatch.py` `execute` looks up the function in `pskit_manifest.json` (or `PSKIT_FUNCTION` / `PSKIT_HANDLER`), matches HTTP routes, imports the handler, calls it, and awaits a coroutine. HTTP results become a `Response`. `HttpError` and other exceptions become JSON errors. Other event types return the result or re-raise so the platform can retry. `BatchResult` has its own meaning. The adapter turns the result back into the native response.

The zip holds your code, `py_serverless_kit` with `__init__.py`, `_version.py`, and `runtime/` only (no CLI, pydantic, yaml, or click), `pskit_manifest.json`, a cloud shim, and either installed dependencies or `requirements.txt`. The artifact is byte-identical for identical inputs: sorted zip entries and fixed timestamps. Unchanged code keeps the same hash.

`resources` become `PSKIT_RESOURCE_<KEY>_*` variables. `runtime/resources.py` reads them. On premises, a driver binding can make the host broker use `runtime/drivers/redis.py` or `runtime/drivers/s3.py` instead of directories.

Sources: `docs/architecture.md#runtime-flow`, `docs/architecture.md#bundle-layout`, `CLAUDE.md`
""",
)

add(
    "concept-pskit-envelope",
    "Concept: the __pskit envelope",
    ["runtime", "events"],
    [],
    [
        "docs/architecture.md#runtime-flow",
        "docs/events.md#schedule-invoke-envelope",
        "src/py_serverless_kit/runtime/adapters/base.py",
    ],
    """
# Concept: the __pskit envelope

Payloads that pskit itself produces are wrapped as `{"__pskit": "<schedule|workflow|invoke>", "data": ...}`. The architecture doc says these are schedule inputs, workflow task inputs, and `invoke()` calls. The events doc says the same for schedules that have `input`, workflow tasks, and `invoke()` calls. `envelope()` in `runtime/adapters/base.py` builds that object. The key constant is `ENVELOPE_KEY = "__pskit"`. Extra keyword arguments are copied onto the object beside `__pskit` and `data`.

`unwrap_envelope` reads a dict, or JSON text or bytes. When `__pskit` is present it returns the kind, `data`, and any other fields. A kind that is not in `EventType.ALL` is returned as `invoke`. Known kinds, including `smtp`, stay as written. If the value is not an envelope, the function returns None.

The adapter unwraps the envelope before the handler runs, so the handler sees `event.type` and `event.data`. That matters on clouds where everything arrives as HTTP: GCP, IBM, DigitalOcean, Cloudflare, and Oracle. On those clouds, failures come back as `500 {"errorType", "cause"}` so a native workflow can match the error by exception name. A schedule handler still sees `event.type == "schedule"` and `event.data` equal to the configured `input`. A workflow task still sees `event.type == "workflow"`.

Sources: `docs/architecture.md#runtime-flow`, `docs/events.md#schedule-invoke-envelope`, `src/py_serverless_kit/runtime/adapters/base.py`
""",
)

add(
    "concept-nodejs",
    "Concept: Node.js handlers",
    ["nodejs", "runtime"],
    [],
    [
        "docs/nodejs.md#nodejs-and-typescript",
        "docs/nodejs.md#choosing-the-runtime",
        "docs/nodejs.md#handlers",
        "docs/nodejs.md#limitations",
    ],
    """
# Concept: Node.js handlers

Handlers can be JavaScript or TypeScript as well as Python. The YAML, triggers, workflows, resources, local tools, and deploy commands stay the same. `provider.runtime` is `nodejs18`, `nodejs20`, `nodejs22`, or `nodejs24`. A service is one language: every function uses the provider's language. A function may pin another Node.js version with `functions.<name>.runtime`. TypeScript is Node.js plus a compile step.

```
pskit init my-api -p aws --typescript
pskit init my-api -p gcp --runtime nodejs22
```

The init help says `--typescript` is shorthand for `--language typescript`, and `--runtime` defaults to python3.12 or nodejs20. Support differs by cloud. AWS, GCP, Azure, and Cloudflare list nodejs18, nodejs20, and nodejs22 in the Node.js doc. Alibaba, Oracle, and IBM list nodejs18 and nodejs20. Tencent, Huawei, and DigitalOcean list nodejs18. On premises lists nodejs18 through nodejs24 and the host needs `node`. Cloudflare bundles with esbuild. GCP and Azure install from `package.json` in their remote builds. The others install into the zip, except Oracle, which installs in the image build.

The handler string is `module.function`, dots for folders, relative to `package.source`. `src.handlers.hello` is the `hello` export of `src/handlers.ts`, `.js`, `.mjs`, `.cjs`, or `src/handlers/index.js`. Handlers may be sync or async. The API mirrors Python in camelCase: `event.http.pathParams`, `ctx.requestId`, `ctx.remainingTimeMs()`, `invoke`, and `resource`. One language per service. Split Python and Node.js into two services if you need both. pskit does not type-check JavaScript files.

Sources: `docs/nodejs.md#nodejs-and-typescript`, `docs/nodejs.md#choosing-the-runtime`, `docs/nodejs.md#handlers`, `docs/nodejs.md#limitations`
""",
)

add(
    "concept-typescript",
    "Concept: TypeScript and Node packaging",
    ["nodejs", "typescript", "package"],
    [],
    [
        "docs/nodejs.md#typescript",
        "docs/nodejs.md#dependencies-and-packaging",
        "docs/nodejs.md#local-development",
        "src/py_serverless_kit/config/schema.py",
    ],
    """
# Concept: TypeScript and Node packaging

pskit compiles `.ts` files with `tsc` when it packages or runs the service. It uses `node_modules/.bin/tsc`, then `tsc` on `PATH`, then `npx --yes -p typescript@5 tsc`. TypeScript is detected from a `tsconfig.json` or a `.ts` handler. `package.node.typescript` true or false forces it. With a tsconfig, pskit extends it and only overrides `outDir`, `rootDir`, and `noEmit: false`. Without one it compiles to CommonJS / ES2022. Type errors fail the build. Node.js API types need `npm install --save-dev @types/node`.

`pskit init`, `pskit package`, and `pskit dev` write `.pskit/types/pskit/index.d.ts`. The generated tsconfig maps the `pskit` module to that file. The doc says to leave out `baseUrl` and `moduleResolution: "node"` because TypeScript 7 removed them.

`package.node` fields are `install` (force or skip npm install), `typescript`, `build` (a command list instead of pskit's tsc), `out_dir` (bundled instead of `source`), `bundle` (esbuild one file per entry; always on for Cloudflare), and `npm_args`. Dependencies use `npm install --omit=dev --ignore-scripts`, or `npm ci` when `package-lock.json` exists, unless the platform builds remotely. The runtime is vendored as `pskit_runtime/` and `node_modules/pskit` and has no dependencies.

```
pskit package --skip-deps
```

Node.js 18+ and npm must be on `PATH` where you package. `"type": "module"` or `.mjs` files load handlers with `import()`. `pskit dev`, `pskit invoke`, and `pskit workflow run` build into `.pskit/local-node/` and run one Node worker per function. The dev server rebuilds when a `.ts`, `.js`, or `.json` file changes. Dependencies resolve from the project's `node_modules`.

Sources: `docs/nodejs.md#typescript`, `docs/nodejs.md#dependencies-and-packaging`, `docs/nodejs.md#local-development`, `src/py_serverless_kit/config/schema.py`
""",
)

add(
    "concept-event-queue",
    "Concept: queue events",
    ["events", "queue"],
    [],
    ["docs/events.md#queue", "docs/events.md#events-backed-by-a-resource"],
    """
# Concept: queue events

`- queue: jobs` is shorthand. The long form sets `name`, `existing` (default false: pskit creates the queue), `batch_size` (1–10000, example 10), `batch_window` (0–300 seconds), `visibility_timeout` (the doc says the AWS default is max(30, 6 times the function timeout)), `dead_letter`, `max_receive`, and `fifo`.

The handler gets `event.type == "queue"` and `event.records`, one `Record` per message. Return a `BatchResult` to retry only the failed messages where the provider supports that.

On AWS SQS, batch size, batch window, dead-letter, max receive, and fifo are used. Fifo adds a `.fifo` suffix and content-based deduplication. Partial failure uses `batchItemFailures`. On GCP the queue is a Pub/Sub topic with a push trigger, because GCP has no SQS-style pull trigger. Batch size, batch window, dead-letter, and fifo are ignored. A dead-letter or fifo setting warns. The whole delivery is retried. On Azure Storage Queue those options are ignored. Poison messages go to `<queue>-poison`. Azure queue names must be 3–63 lowercase letters, digits, and dashes. The whole delivery is retried.

On premises a file broker implements batch size, batch window, visibility, dead-letter, max receive, and fifo. `BatchResult` retries only the failed ids, as on AWS. `provider.options.services.queue` is `builtin` or `{use: directory, path: ...}`. `existing: true` waits for that directory.

An event can point at a resource: `- queue: {resource: jobs, batch_size: 5}`. The event uses the resource's native name and `existing` follows `external`.

Sources: `docs/events.md#queue`, `docs/events.md#events-backed-by-a-resource`
""",
)

add(
    "concept-event-storage",
    "Concept: storage events",
    ["events", "storage"],
    [],
    ["docs/events.md#storage", "docs/events.md#events-backed-by-a-resource"],
    """
# Concept: storage events

`- storage: uploads-bucket` is shorthand. The long form sets `bucket`, `existing` (false means pskit creates the bucket), `events` (default `[created]`; `deleted` is the other value), `prefix`, and `suffix`. Each record has `bucket`, `key`, `size`, and `action` (`created` or `deleted`).

AWS uses S3 notifications and native filters. Created buckets block public access. GCP uses Cloud Storage via Eventarc. Filters are applied by the runtime. `created` and `deleted` become separate deployments. Azure is a blob trigger in the app's storage account, created or updated only, not deleted. The container name is 3–63 lowercase characters. An existing bucket in another account needs `options.storage_connection`. Alibaba OSS, Tencent COS, and Huawei OBS use native filters. A Tencent bucket name must be `<name>-<APPID>`. Oracle uses an Events rule and does not support the filters: the doc says to filter in the handler, and the bucket must have Emit Object Events enabled.

On premises the bucket is a directory. Prefix and suffix are applied in the host. `builtin` creates the directory. `{use: directory, path}` uses one you already have. The first start records current files and does not emit them.

`- storage: {resource: uploads, prefix: in/}` uses the resource's native name and sets `existing` from `external`. On premises a resource can move the bucket to an S3-compatible store. A storage event may set both `resource` and `bucket`: that bucket on the resource's storage service.

Sources: `docs/events.md#storage`, `docs/events.md#events-backed-by-a-resource`
""",
)

add(
    "concept-event-topic",
    "Concept: topic events",
    ["events", "topic"],
    [],
    [
        "docs/events.md#topic",
        "docs/events.md#events-triggers",
        "docs/events.md#events-backed-by-a-resource",
    ],
    """
# Concept: topic events

`- topic: order-events` is shorthand. The long form sets `name`, `existing` (default false), and `filter`. The example filter is `{type: ["created"]}`, described as an AWS SNS filter policy.

AWS applies the filter policy on the SNS subscription. GCP Pub/Sub does not apply `filter` and warns. Filter in the handler. Azure Service Bus uses a topic plus a subscription. `filter` is not applied and warns. `existing` needs `options.servicebus_namespace_id` and `options.servicebus_connection`. Alibaba MNS accepts `filter.tag` as a string only. Huawei SMN is listed with no filter mark. On premises the topic is a file topic with fan-out. The filter is an exact match on attributes, then on JSON body fields.

The events support table marks topic on AWS, GCP, Azure, Alibaba, Huawei, and on premises. Oracle, IBM, DigitalOcean, Tencent, and Cloudflare are unmarked. `pskit validate` reports a trigger the selected provider cannot honour.

A topic event can name a resource instead of a topic name. The event uses that resource's native name, and `existing` follows whether the resource is external. The function also receives the resource's connection details.

Sources: `docs/events.md#topic`, `docs/events.md#events-triggers`, `docs/events.md#events-backed-by-a-resource`
""",
)

add(
    "concept-batch-result",
    "Concept: BatchResult",
    ["handlers", "events"],
    [],
    ["docs/handlers.md#batchresult", "docs/events.md#queue"],
    """
# Concept: BatchResult

Return a `BatchResult` from a queue, topic, or storage handler to name the records that failed. Create one, loop `event.records`, and call `result.fail(record)` or `result.fail(record.id)` inside the except block. `BatchResult.of(failed_records)` is the other constructor in the doc. Returning the object reports those ids. Records you do not fail are treated as done.

```python
from py_serverless_kit import BatchResult

def worker(event, ctx):
    result = BatchResult()
    for record in event.records:
        try:
            process(record.json())
        except Exception:
            result.fail(record)
    return result
```

On AWS SQS the result becomes `batchItemFailures`, so only the failed messages are retried. On premises the host retries only the failed message ids and moves a message to `dead_letter` after `max_receive`. Locally the result is printed as `batchItemFailures`. On every other provider any failure raises `BatchFailure`, so the whole delivery is retried. The queue event table says the same for GCP and Azure: the whole delivery is retried.

The doc says to write idempotent handlers, because redelivery is normal on every cloud. A handler that raises instead of returning `BatchResult` fails the delivery the platform's usual way.

Sources: `docs/handlers.md#batchresult`, `docs/events.md#queue`
""",
)

add(
    "concept-third-party-providers",
    "Concept: third-party providers",
    ["providers", "architecture"],
    [],
    ["docs/architecture.md#third-party-providers", "CLAUDE.md"],
    """
# Concept: third-party providers

A provider subclasses `py_serverless_kit.providers.base.Provider`. The architecture example sets `name`, `display_name`, `tier = "experimental"`, `terraform_source`, `terraform_version`, `default_region`, `capabilities` such as HTTP and SCHEDULE, `runtimes`, and `max_timeout`. It implements `shim_files` and `render_resources`. `render_resources` adds resources to a `TerraformDoc` and emits `output "pskit"` shaped `{functions: {name: {id, url}}, workflows: {}, endpoint}`. Every built-in provider emits that output so `pskit info` and the dashboard stay provider-agnostic.

Register the class from your own package. The entry-point group is `py_serverless_kit.providers`:

```text
[project.entry-points."py_serverless_kit.providers"]
mycloud = "pskit_mycloud:MyCloudProvider"
```

`pskit providers` lists entry-point providers. `provider: {name: mycloud}` or `--provider mycloud` selects one. The loader accepts every built-in name plus every registered plug-in. The adapter should turn the native event into an `Event`, call `py_serverless_kit.runtime.dispatch.execute`, and turn the result back into the native response. The doc points the rest of the checklist at `deploy_docs/CONTRIBUTING.md`.

New built-in providers also start at tier `experimental` until they have been deployed, as CLAUDE.md states. A plug-in does not require a change inside pskit.

Sources: `docs/architecture.md#third-party-providers`, `CLAUDE.md`
""",
)


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def main() -> None:
    CARDS.mkdir(parents=True, exist_ok=True)
    rows = []
    if JSONL.is_file():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    by_id = {row["id"]: row for row in rows}
    bad = []
    for page in PAGES:
        n = words(page["text"])
        print(f"{page['id']} {n}")
        if n < 150 or n > 500:
            bad.append(f"{page['id']} has {n} words")
    if bad:
        raise SystemExit("\n".join(bad))
    for page in PAGES:
        path = CARDS / f"{page['id']}.md"
        path.write_bytes(page["text"].encode("utf-8"))
        by_id[page["id"]] = page
    ordered = [by_id[key] for key in sorted(by_id)]
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered)
    JSONL.write_bytes(payload.encode("utf-8"))
    print(f"jsonl={len(ordered)} concepts={len(PAGES)}")


if __name__ == "__main__":
    main()
