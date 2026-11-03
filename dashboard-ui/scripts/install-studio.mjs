// Copy the single-file studio build into the Python package.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "../dist-studio/studio.html");
const target = resolve(here, "../../src/py_serverless_kit/studio/studio.html");

let html = readFileSync(source, "utf8").replace(/\r\n/g, "\n");
if (!html.endsWith("\n")) html += "\n";
if (/<script[^>]+src=|<link[^>]+href=/.test(html)) {
  console.error("studio build is not self-contained (external script or stylesheet)");
  process.exit(1);
}
if (!html.includes('<div id="root"></div>')) {
  console.error("studio build lost its root element");
  process.exit(1);
}
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, html, "utf8");
console.log(`wrote ${target} (${(Buffer.byteLength(html) / 1024).toFixed(1)} KiB)`);
