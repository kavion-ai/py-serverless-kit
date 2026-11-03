# 21 · Node.js + TypeScript

The same pskit features as the Python examples, with handlers written in TypeScript:
HTTP routes, a queue worker with partial batch failures, a schedule and a workflow.

## Files

| File | Purpose |
| --- | --- |
| `pskit.yml` | `runtime: nodejs20` makes this a Node.js service; handlers point at `src/*.ts` |
| `src/http.ts` | HTTP handlers (`hello`, `createOrder`, `getOrder`) |
| `src/jobs.ts` | queue consumer returning a `BatchResult`, scheduled report |
| `src/workflow.ts` | workflow tasks; `ValidationError` is caught by the workflow |
| `src/orders.ts` | shared logic, no cloud SDK |
| `tsconfig.json` | maps `pskit` to `.pskit/types/pskit/index.d.ts`, which pskit writes |
| `package.json` | your npm dependencies (none here) |

## The YAML

```yaml
provider:
  runtime: nodejs20            # nodejs18 | nodejs20 | nodejs22 | nodejs24
functions:
  hello:
    handler: src.http.hello    # src/http.ts -> export function hello
```

pskit compiles the `.ts` files with `tsc` when it packages or runs the service. Types for
`import { Response } from "pskit"` come from `.pskit/types/pskit/index.d.ts` (written by
`pskit init` / `pskit package`), so editors resolve them without installing anything.

## Run locally

Needs Node.js 18+ on PATH (and `tsc`, or `npx` to fetch it).

```bash
pskit dev                                                  # http://127.0.0.1:3000/hello?name=Ada
pskit invoke -f create-order --method POST --path /orders -d @events/order.json
pskit invoke -f process-orders -t queue -d '[{"item": "pen"}, {"item": ""}]'
pskit workflow run order-pipeline -i @events/order.json
pskit workflow run order-pipeline -i @events/bad-order.json   # FAILED OrderRejected
```

## Deploy

```bash
pskit deploy                   # AWS Lambda, nodejs20.x
pskit deploy -p gcp            # any provider with Node.js support, see docs/nodejs.md
```
