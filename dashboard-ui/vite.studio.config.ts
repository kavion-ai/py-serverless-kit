import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// pskit studio: a second single-file app sharing src/components with the dashboard.
// scripts/install-studio.mjs copies dist-studio/studio.html to src/py_serverless_kit/studio/studio.html.
export default defineConfig({
  plugins: [react(), viteSingleFile({ removeViteModuleLoader: true })],
  build: {
    outDir: "dist-studio",
    emptyOutDir: true,
    target: "es2019",
    cssCodeSplit: false,
    assetsInlineLimit: 100000000,
    reportCompressedSize: false,
    modulePreload: false,
    chunkSizeWarningLimit: 2000,
    rollupOptions: { input: "studio.html" },
  },
  server: {
    // `pskit studio --port 8770` answers /api during `npm run dev:studio`
    // (or set VITE_MOCK=1 to use the in-browser mock API).
    open: "/studio.html",
    proxy: { "/api": "http://127.0.0.1:8770" },
  },
});
