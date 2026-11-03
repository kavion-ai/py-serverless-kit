// Unit tests of the pure studio modules: bundle every src/**/*.test.ts with esbuild (installed with vite) and run
// them with Node's built-in test runner. No extra dependencies; `npm test`.
import { build } from "esbuild";
import { mkdtempSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function find(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...find(path));
    else if (name.endsWith(".test.ts")) out.push(path);
  }
  return out.sort();
}

const filter = process.argv[2];
const tests = find(join(root, "src")).filter((t) => !filter || t.includes(filter));
if (!tests.length) {
  console.error("no *.test.ts files found");
  process.exit(1);
}
const out = mkdtempSync(join(tmpdir(), "pskit-ui-tests-"));
try {
  const files = [];
  for (const test of tests) {
    const outfile = join(out, basename(test).replace(/\.ts$/, ".mjs"));
    await build({
      entryPoints: [test],
      outfile,
      bundle: true,
      platform: "node",
      format: "esm",
      target: "node18",
      logLevel: "warning",
      // Vite's import.meta.env does not exist under Node.
      define: { "import.meta.env": "{}" },
    });
    files.push(outfile);
  }
  const run = spawnSync(process.execPath, ["--test", ...files], { stdio: "inherit" });
  process.exitCode = run.status ?? 1;
} finally {
  rmSync(out, { recursive: true, force: true });
}
