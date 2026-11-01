import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.MLB_DASHBOARD_API_TARGET || 'http://127.0.0.1:8000';

// Both dev and local production preview use the same-origin API contract.
// The target is server-side configuration; credentials never belong in VITE_* variables.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': apiTarget,
      '/health': apiTarget,
    },
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: {
      '/api': apiTarget,
      '/health': apiTarget,
    },
  },
});
