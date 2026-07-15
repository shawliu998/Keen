import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 1430, strictPort: true },
  preview: { host: "127.0.0.1", port: 1430, strictPort: true },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@keen/domain": fileURLToPath(new URL("../../packages/domain/src/index.ts", import.meta.url)),
      "@keen/ui": fileURLToPath(new URL("../../packages/ui/src/index.tsx", import.meta.url)),
    },
  },
  test: { environment: "jsdom", setupFiles: "./tests/setup.ts", css: true, globals: true },
});
