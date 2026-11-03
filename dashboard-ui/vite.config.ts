import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// One self-contained HTML file (inline JS + CSS). scripts/install-template.mjs
// copies it to src/py_serverless_kit/dashboard/template.html.
export default defineConfig({
  plugins: [react(), viteSingleFile({ removeViteModuleLoader: true })],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2019",
    cssCodeSplit: false,
    assetsInlineLimit: 100000000,
    reportCompressedSize: false,
    modulePreload: false,
  },
  server: {
    // `pskit dashboard --serve --port 8765` answers /api during `npm run dev`.
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
