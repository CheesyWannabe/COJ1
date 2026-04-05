import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/upload-reference": "http://localhost:8000",
      "/submit": "http://localhost:8000",
      "/results": "http://localhost:8000",
    },
  },
});
