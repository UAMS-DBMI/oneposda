/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served by nginx at /abc/; in development the API is reached through the
// compose nginx on localhost so the logintoken cookie is first-party.
export default defineConfig({
  base: "/abc/",
  plugins: [react()],
  server: {
    proxy: {
      "/papi": { target: "http://localhost", changeOrigin: false },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
  },
});
