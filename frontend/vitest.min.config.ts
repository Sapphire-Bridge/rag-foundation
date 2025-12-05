import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    setupFiles: [],
    pool: "threads",
    maxWorkers: 1,
    minWorkers: 1,
  },
});

