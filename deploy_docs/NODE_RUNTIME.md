# Node.js / TypeScript runtime: design contract

Maintainer document. It fixes the interfaces between the parts of the Node.js support so they can be
built and changed independently. User documentation lives in `docs/nodejs.md`.

## Language selection

* A service is **either Python or Node.js**, chosen by `provider.runtime`:
  `python3.9`..`python3.14` or `nodejs18`, `nodejs20`, `nodejs22`, `nodejs24`
  (`config.schema.NODE_RUNTIMES`, `runtime_language()`, `ServiceConfig.language`).
  A function may pin another runtime of the same language only.
* TypeScript is Node.js plus a compile step (`package.node.typescript`, auto-detected).
* Providers declare `node_runtimes = {"nodejs20": "<platform id>", ...}`. Empty = no Node.js
  (validation then reports `... does not support Node.js functions in pskit yet`).
  `Provider.runtime_id()` maps either language; `default_runtime_for("node")` picks nodejs20 or the nearest.
* `node_vendor_dependencies` (default True): npm-install production dependencies into the bundle.
  False where the platform installs from `package.json` itself (GCP, Azure).
* `node_bundle` (default False): the platform needs one self-contained file per entry (esbuild), e.g.
  Cloudflare Workers.

## Handlers

Same string as Python: `module.function` (or `module:function`). The module path uses dots for folders
and is resolved against the bundle root: `src.handlers.hello` → `src/handlers.{js,mjs,cjs}`
(TypeScript `src/handlers.ts` is compiled to `src/handlers.js` before packaging), or
`src/handlers/index.js`. The function is a named export (`export function hello` / `exports.hello`);
`default` export objects are searched too. Handlers may be sync or async:

```ts
import type { Event, Context } from "pskit";
import { Response, BatchResult } from "pskit";

export async function hello(event: Event, ctx: Context) {
  const name = event.http?.query.name ?? "world";
  ctx.logger.info("hello", { name });
  return { message: `Hello, ${name}!` };          // plain value -> JSON 200
}
```

## Bundle layout (Node.js)

```
<sources>                    package.source (or package.node.out_dir), .ts compiled to .js in place
pskit_runtime/               the JS runtime (copied from src/py_serverless_kit/runtime_js/), CommonJS, no deps
node_modules/                npm install --omit=dev (when vendored); node_modules/pskit -> copy of pskit_runtime
package.json                 the user's (or a generated minimal one); for remote builds it lists
                             "pskit": "file:./pskit_runtime" so `import "pskit"` resolves after the platform's npm install
pskit_manifest.json          identical to the Python manifest (Project.bundle_manifest)
<provider shims>             e.g. pskit_entry.js (AWS), index.js (GCP), src/functions/pskit.js (Azure)
```

Shims only `require("./pskit_runtime/adapters/<cloud>")` and re-export the platform entrypoint. The zip must
stay byte-reproducible (the builder already sorts entries and fixes timestamps; npm output must not add
timestamps: use `--no-audit --no-fund --ignore-scripts`, and keep `package-lock.json` when present).

## JS runtime API (`src/py_serverless_kit/runtime_js/`, package name `pskit`)

CommonJS, Node.js >= 18, **no dependencies**, mirrors the Python runtime (camelCase):

| Module | Exports |
|---|---|
| `index.js` | `Event, HttpRequest, Record, Headers, Context, Response, BatchResult, EventType, invoke, resources, resource, PskitError, BadRequest, NotFound, ...` |
| `event.js` | `EventType` (`http schedule queue storage topic invoke workflow`), `Event {type, provider, function, http, records, data, time, source, raw, json()}`, `HttpRequest {method, path, headers, query, multiQuery, pathParams, body: Buffer, sourceIp, route, text(), json(), form(), cookies}`, `Record {id, body, attributes, source, bucket, key, size, action, raw, text(), json()}`, `Headers` (case-insensitive get/has/entries), `eventFromDict(d)` (inverse of Python `Event.to_dict()` extended with full http/records, see worker protocol) |
| `context.js` | `Context {requestId, function, provider, service, stage, region, memoryMb, deadline, raw, env, logger, remainingTimeMs()}` |
| `log.js` | JSON-lines logger honouring `PSKIT_LOG_LEVEL`/`LOG_LEVEL` and `PSKIT_LOG_FORMAT=text`, same fields as Python `runtime/log.py` |
| `response.js` | `Response.json/text/html/binary/redirect/noContent`, `setCookie`, `render()` → `{status, headers, body: Buffer}`, `renderForGateway()` → `{status, headers, body: string, isBase64}`, `toResponse(value)` |
| `batch.js` | `BatchResult {failed, fail(recordOrId), ok}`, `BatchResult.of(...)` |
| `errors.js` | same error classes and HTTP status mapping as `runtime/errors.py` |
| `manifest.js` | loads `pskit_manifest.json` from the bundle root (`PSKIT_BUNDLE_ROOT` or two folders up from the runtime) |
| `routing.js` | path-template matching identical to `runtime/routing.py` (`{id}`, `{path+}`) |
| `dispatch.js` | `async execute(event, context, functionName?)` with the same semantics as Python `dispatch.execute`: manifest lookup, HTTP routing/CORS/405, handler import (cached, ESM via `import()`), sync/async call, error → JSON response, BatchResult passthrough |
| `invoke.js` | `async invoke(fn, payload, {async, timeout})`, same env contract as `runtime/invoke.py` |
| `resources.js` | `resources()`, `resource(name)` from `PSKIT_RESOURCE_*` like `runtime/resources.py` |
| `workflow.js` | the embedded engine, a port of `runtime/workflow.py` (same definition dialect, JSON paths, choice operators, retry/catch, parallel/map) and `orchestrate(event, ctx)` used by `pskit_runtime.workflow.orchestrate` |
| `adapters/base.js` | `envelope`, `unwrapEnvelope` (`__pskit` envelope), `maybeJson`, `b64Text`, `functionName`, `actionFrom` |
| `adapters/<cloud>.js` | one per provider: native event → `Event`/`Context`, call `execute`, result → native response; same behaviour as the Python adapter of that cloud |
| `worker.js` | the JSON-lines worker (below) used by the on-prem host and `pskit dev` / `pskit invoke` |
| `index.d.ts` | TypeScript declarations for everything above (`declare module "pskit"` is not needed: it is the package's own `types`) |

`package.json` of the runtime: `{"name": "pskit", "version": <pskit version>, "main": "index.js", "types": "index.d.ts"}`.

## Worker protocol (`node pskit_runtime/worker.js`)

Used where a Python process drives Node.js functions: the on-prem host and local `pskit dev` / `pskit invoke`.
One long-lived process per bundle; `cwd` = bundle root (or the project root locally, with `PSKIT_BUNDLE_ROOT`).
Requests are JSON lines on **stdin**, responses JSON lines on **stdout**; logs go to **stderr** (JSON lines,
the same shape the Python logger writes) so the host's log capture keeps working.

Request:
```json
{"id": "r1", "function": "hello", "event": {...}, "context": {"request_id": "...", "deadline": 1735000000.5, "memory_mb": 256}}
```
`event` is the full portable form:
```json
{"type": "http", "provider": "onprem", "function": "hello", "time": "2026-...Z", "source": null, "data": null,
 "http": {"method": "GET", "path": "/hello", "headers": {...}, "query": {...}, "multi_query": {...},
          "path_params": {...}, "body_b64": "", "source_ip": "127.0.0.1", "route": "/hello"},
 "records": [{"id": "...", "body": <json or string>, "body_b64": null, "attributes": {}, "source": "...",
              "bucket": null, "key": null, "size": null, "action": null}]}
```
Python side helper: `py_serverless_kit.runtime.event.Event.to_wire()` / `event_from_wire()` (added with the worker).

Response (exactly one per request, any order, matched by `id`):
```json
{"id": "r1", "ok": true, "kind": "http", "status": 200, "headers": {...}, "body_b64": "..."}
{"id": "r1", "ok": true, "kind": "batch", "failed": ["msg-2"]}
{"id": "r1", "ok": true, "kind": "value", "value": <json>}
{"id": "r1", "ok": false, "error": {"type": "ValueError", "message": "...", "stack": "..."}}
```
Requests run concurrently (async). `{"id": "x", "op": "ping"}` → `{"id": "x", "ok": true, "kind": "pong"}`.
On stdin EOF the worker finishes in-flight requests and exits 0.

## Packaging (`packaging/builder.py`)

For `language == "node"`:
1. If `package.node.build` is set, run it in the project (cwd = project root) and bundle `package.node.out_dir`
   (default `package.source`). Otherwise copy sources (same include/exclude, `node_modules/**`, `dist/**` excluded).
2. TypeScript (explicit or auto): run `tsc` (project `node_modules/.bin/tsc`, else `tsc` on PATH, else
   `npx --yes -p typescript@5 tsc`) with `--outDir <build> --rootDir <source> --module commonjs --target es2022
   --esModuleInterop --skipLibCheck --declaration false` over the handler files (respecting the user's
   `tsconfig.json` via `-p` when present, overriding outDir). A tsc failure is a `BuildError` with its output.
3. Copy `runtime_js/` to `<build>/pskit_runtime/`, write `pskit_manifest.json`, the provider shims.
4. Dependencies: when vendored, write/merge `package.json` and run `npm install --omit=dev --no-audit --no-fund
   --ignore-scripts` in the build dir (skipped with `--skip-deps`), then copy the runtime to `node_modules/pskit`.
   When not vendored, add `"pskit": "file:./pskit_runtime"` to `dependencies` of the bundled `package.json`.
   A `package.json` among the provider's `shim_files` is not written as a file: it is deep-merged over the
   user's `package.json` (provider keys win), e.g. `{"main": "index.js"}` for platforms that load the package's
   `main`. Other shim files replace user files at the same path, with a build warning.
5. When `node_bundle` (or `package.node.bundle`) is set, the provider's shim is bundled with esbuild
   (`node_modules/.bin/esbuild` → `esbuild` → `npx --yes esbuild@0.24`) into the single file the provider asks for.
   Optional provider hooks: `node_bundle_entries(config) -> {output_rel: entry_rel}` (default: every `.js/.mjs/.cjs`
   shim bundled in place) and `node_bundle_options` (default `--platform=node --format=cjs --target=node18`).

Node.js and npm must be on PATH for Node.js services; a missing tool is a `BuildError` with an install hint.

## Who owns what

| Part | Files |
|---|---|
| JS runtime | `src/py_serverless_kit/runtime_js/**` (except `adapters/<cloud>.js`), `tests/runtime_js/**` |
| Build, CLI, local | `packaging/builder.py`, `local/**`, `cli/main.py` + `cli/templates.py` (init `--runtime`), `runtime/event.py` wire helpers, `tests/test_packaging*`, `tests/test_local*` |
| Cloud providers | `providers/<cloud>.py` (node_runtimes, shims, render differences) + `runtime_js/adapters/<cloud>.js` + tests |
| On-prem | `providers/onprem*.py`, `runtime/onprem_host.py` (drive the worker), remote/docker installs Node.js |
