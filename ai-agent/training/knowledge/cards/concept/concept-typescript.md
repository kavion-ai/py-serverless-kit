# Concept: TypeScript and Node packaging

pskit compiles `.ts` files with `tsc` when it packages or runs the service. It uses `node_modules/.bin/tsc`, then `tsc` on `PATH`, then `npx --yes -p typescript@5 tsc`. TypeScript is detected from a `tsconfig.json` or a `.ts` handler. `package.node.typescript` true or false forces it. With a tsconfig, pskit extends it and only overrides `outDir`, `rootDir`, and `noEmit: false`. Without one it compiles to CommonJS / ES2022. Type errors fail the build. Node.js API types need `npm install --save-dev @types/node`.

`pskit init`, `pskit package`, and `pskit dev` write `.pskit/types/pskit/index.d.ts`. The generated tsconfig maps the `pskit` module to that file. The doc says to leave out `baseUrl` and `moduleResolution: "node"` because TypeScript 7 removed them.

`package.node` fields are `install` (force or skip npm install), `typescript`, `build` (a command list instead of pskit's tsc), `out_dir` (bundled instead of `source`), `bundle` (esbuild one file per entry; always on for Cloudflare), and `npm_args`. Dependencies use `npm install --omit=dev --ignore-scripts`, or `npm ci` when `package-lock.json` exists, unless the platform builds remotely. The runtime is vendored as `pskit_runtime/` and `node_modules/pskit` and has no dependencies.

```
pskit package --skip-deps
```

Node.js 18+ and npm must be on `PATH` where you package. `"type": "module"` or `.mjs` files load handlers with `import()`. `pskit dev`, `pskit invoke`, and `pskit workflow run` build into `.pskit/local-node/` and run one Node worker per function. The dev server rebuilds when a `.ts`, `.js`, or `.json` file changes. Dependencies resolve from the project's `node_modules`.

Sources: `docs/nodejs.md#typescript`, `docs/nodejs.md#dependencies-and-packaging`, `docs/nodejs.md#local-development`, `src/py_serverless_kit/config/schema.py`
