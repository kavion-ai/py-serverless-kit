# Concept: Node.js handlers

Handlers can be JavaScript or TypeScript as well as Python. The YAML, triggers, workflows, resources, local tools, and deploy commands stay the same. `provider.runtime` is `nodejs18`, `nodejs20`, `nodejs22`, or `nodejs24`. A service is one language: every function uses the provider's language. A function may pin another Node.js version with `functions.<name>.runtime`. TypeScript is Node.js plus a compile step.

```
pskit init my-api -p aws --typescript
pskit init my-api -p gcp --runtime nodejs22
```

The init help says `--typescript` is shorthand for `--language typescript`, and `--runtime` defaults to python3.12 or nodejs20. Support differs by cloud. AWS, GCP, Azure, and Cloudflare list nodejs18, nodejs20, and nodejs22 in the Node.js doc. Alibaba, Oracle, and IBM list nodejs18 and nodejs20. Tencent, Huawei, and DigitalOcean list nodejs18. On premises lists nodejs18 through nodejs24 and the host needs `node`. Cloudflare bundles with esbuild. GCP and Azure install from `package.json` in their remote builds. The others install into the zip, except Oracle, which installs in the image build.

The handler string is `module.function`, dots for folders, relative to `package.source`. `src.handlers.hello` is the `hello` export of `src/handlers.ts`, `.js`, `.mjs`, `.cjs`, or `src/handlers/index.js`. Handlers may be sync or async. The API mirrors Python in camelCase: `event.http.pathParams`, `ctx.requestId`, `ctx.remainingTimeMs()`, `invoke`, and `resource`. One language per service. Split Python and Node.js into two services if you need both. pskit does not type-check JavaScript files.

Sources: `docs/nodejs.md#nodejs-and-typescript`, `docs/nodejs.md#choosing-the-runtime`, `docs/nodejs.md#handlers`, `docs/nodejs.md#limitations`
