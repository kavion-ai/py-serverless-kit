# Example: 21-nodejs-typescript

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include README.md, package.json, pskit.yml, tsconfig.json.

Comments in pskit.yml: 

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

pskit compiles the `.ts` files with `tsc` when it packages or runs the service. Types for
`import { Response } from "pskit"` come from `.pskit/types/pskit/index.d.ts` (written by
`pskit init` / `pskit package`), so editors resolve them without installing anything.

## Run locally

Needs Node.js 18+ on PATH (and `tsc`, or `npx` to fetch it).
