import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("@element-plus/icons-vue")) return "element-icons";
          if (id.includes("element-plus")) return "element-plus";
          if (id.includes("vue") || id.includes("pinia")) return "vue-vendor";
          return "vendor";
        },
      },
    },
  },
  server: {
    port: 7003,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.ts",
  },
});
