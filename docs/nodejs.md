# Node.js and TypeScript

Handlers can be written in JavaScript or TypeScript as well as Python. The YAML, triggers, workflows,
resources, local tools and deploy commands are the same; only `provider.runtime` changes.

```bash
pskit init my-api -p aws --typescript      # Node.js 20 + TypeScript
pskit init my-api -p gcp --runtime nodejs22  # JavaScript on Node.js 22
cd my-api && pskit dev
```

## Choosing the runtime

```yaml
provider:
  name: aws
  runtime: nodejs20        # nodejs18 | nodejs20 | nodejs22 | nodejs24
```

A service is either Python or Node.js: every function uses the provider's language (a function may pin
another Node.js version with `functions.<name>.runtime`). TypeScript is Node.js plus a compile step that pskit
runs for you.

| Provider | Node.js runtimes | Dependencies |
|---|---|---|
| AWS Lambda | nodejs18, nodejs20, nodejs22 | installed into the zip (`npm install --omit=dev`) |
| Google Cloud Functions | nodejs18, nodejs20, nodejs22 | installed by Cloud Build from `package.json` |
| Azure Functions | nodejs18, nodejs20, nodejs22 | installed by the remote (Oryx) build from `package.json` |
| Alibaba Function Compute | nodejs18, nodejs20 | installed into the zip |
| Tencent SCF | nodejs18 | installed into the zip |
| Huawei FunctionGraph | nodejs18 | installed into the zip |
| Oracle Functions | nodejs18, nodejs20 | installed in the image build |
| IBM Code Engine | nodejs18, nodejs20 | installed into the zip |
| DigitalOcean Functions | nodejs18 | installed into the zip |
| Cloudflare Workers | nodejs18, nodejs20, nodejs22 | bundled into one file with esbuild |
| On premises | nodejs18 … nodejs24 | installed into the bundle; the host needs `node` |

See [providers.md](providers.md) for per-cloud details and limits.

## Handlers

The handler string works like Python's: `module.function`, with dots for folders, relative to `package.source`.
`src.handlers.hello` is the `hello` export of `src/handlers.ts` (or `.js`, `.mjs`, `.cjs`, or
`src/handlers/index.js`). Handlers can be sync or `async`.

```ts
import { BatchResult, NotFound, Response } from "pskit";
import type { Context, Event } from "pskit";

export async function hello(event: Event, ctx: Context) {
  const name = event.http?.query.name ?? "world";
  ctx.logger.info("saying hello", { name });
  return { message: `Hello, ${name}!` };            // plain value -> JSON 200
}

export async function getItem(event: Event) {
  const item = await find(event.http!.pathParams.id);
  if (!item) throw new NotFound("no such item");     // -> 404 JSON
  return Response.json(item, 200);
}

export async function worker(event: Event, ctx: Context) {
  const result = new BatchResult();
  for (const record of event.records) {
    try { await process(record.json()); } catch { result.fail(record); }
  }
  return result;                                      // retry only the failed records
}
```

The API mirrors the [Python handler API](handlers.md) in camelCase: `event.http.pathParams`,
`event.http.json()`, `record.text()`, `ctx.requestId`, `ctx.remainingTimeMs()`, `invoke("other-fn", data)`,
`resource("orders")`. Workflow `retry` / `catch` rules match the error's class name
(`class ValidationError extends Error {}` → `ValidationError`).

### Secrets

`getSecret(name, field?, { store, default })`, `getSecrets(name)` and `putSecret(name, value)` work like the Python
calls (Vault / OpenBao, AWS Secrets Manager, or environment variables); see
[handlers.md](handlers.md#get_secret-secrets-on-every-provider).

## TypeScript

* pskit compiles `.ts` files with `tsc` when it packages or runs the service. It uses the project's
  `node_modules/.bin/tsc`, then `tsc` on `PATH`, then `npx --yes -p typescript@5 tsc`.
* TypeScript is detected from a `tsconfig.json` or a `.ts` handler; force it with
  `package.node.typescript: true | false`.
* With a `tsconfig.json`, pskit extends it and only overrides the output settings (`outDir`, `rootDir`,
  `noEmit: false`), so your `strict`, `target` and `paths` apply. Without one it compiles to CommonJS / ES2022.
* Type errors fail the build, with the compiler output in the error.
* Using Node.js APIs (`process`, `Buffer`, `fs`) from TypeScript needs their types: `npm install --save-dev @types/node`.
* **Types for `pskit`** need no npm package: `pskit init`, `pskit package` and `pskit dev` write
  `.pskit/types/pskit/index.d.ts`, and the generated `tsconfig.json` maps the module to it:

  ```json
  { "compilerOptions": { "paths": { "pskit": ["./.pskit/types/pskit/index.d.ts"] } } }
  ```
  Leave out `baseUrl` and `moduleResolution: "node"`: TypeScript 7 removed them.

  Run `pskit package` once (or `pskit init`) if your editor can't resolve `pskit` yet.

## Calling an on-prem host from other Node.js programs

The `pskit` package also has `PskitClient` for scripts outside pskit; `pskit client install-node` copies the package
into `./node_modules/pskit`. See [client.md](client.md).

## Dependencies and packaging

`package.json` dependencies are bundled with the function: either `npm install --omit=dev --ignore-scripts`
into the zip (`npm ci` when a `package-lock.json` exists), or by the platform's own build where it has one
(table above). `pskit package --skip-deps` skips the install. The pskit runtime itself is vendored as
`pskit_runtime/` (and `node_modules/pskit`); it has no dependencies.

```yaml
package:
  source: .
  node:
    install: true              # force (true) / skip (false) npm install into the bundle
    typescript: true           # default: auto-detected
    build: [npm, run, build]   # your own build step instead of pskit's tsc...
    out_dir: dist              # ...and the folder it writes (bundled instead of `source`)
    bundle: false              # esbuild one file per entry (always on for Cloudflare)
    npm_args: [--legacy-peer-deps]
```

Node.js 18+ and npm must be on `PATH` where you package. ES modules work too:
set `"type": "module"` in `package.json` or use `.mjs` files; handlers are loaded with `import()`.

## Local development

`pskit dev`, `pskit invoke` and `pskit workflow run` work as for Python. pskit builds the service into
`.pskit/local-node/` (compiling TypeScript) and runs it in a Node.js worker process, one per function so each
gets its own environment. The dev server rebuilds and restarts the worker when a `.ts`, `.js` or `.json` file
changes.

```bash
pskit invoke -f hello --path "/hello?name=Ada"
pskit invoke -f worker -t queue -d '[{"id": 1}, {"id": 2}]'
pskit workflow run order-pipeline -i @events/order.json --history
```

Dependencies resolve from the project's `node_modules`, so run `npm install` first if you have any.

## Limitations

* One language per service. Split Python and Node.js functions into two services (they can call each other
  over HTTP or a queue).
* Local runs serve HTTP through pskit's router, not a cloud gateway, as with Python.
* pskit doesn't type-check JavaScript files. Add `// @ts-check` or switch to TypeScript for that.

A complete example: [`examples/21-nodejs-typescript`](../examples/21-nodejs-typescript/README.md).
