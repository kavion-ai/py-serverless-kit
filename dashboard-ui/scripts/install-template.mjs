// Copy the single-file build to the Python package as the dashboard template.
// Fails when the generator placeholders are missing or appear more than once,
// because the generator substitutes them with plain string replacement.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "../dist/index.html");
const target = resolve(here, "../../src/py_serverless_kit/dashboard/template.html");

let html = readFileSync(source, "utf8").replace(/\r\n/g, "\n");
if (!html.endsWith("\n")) html += "\n";

for (const token of ["{{TITLE}}", "{{DATA}}"]) {
  const count = html.split(token).length - 1;
  if (count !== 1) {
    console.error(`template must contain ${token} exactly once, found ${count}`);
    process.exit(1);
  }
}
if (!html.includes('<script type="application/json" id="data">{{DATA}}</script>')) {
  console.error("the data script tag was rewritten by the build");
  process.exit(1);
}
if (/<script[^>]+src=|<link[^>]+href=/.test(html)) {
  console.error("build is not self-contained (external script or stylesheet)");
  process.exit(1);
}

writeFileSync(target, html, "utf8");
console.log(`wrote ${target} (${(Buffer.byteLength(html) / 1024).toFixed(1)} KiB)`);
