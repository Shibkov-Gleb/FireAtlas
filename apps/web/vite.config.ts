import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { rmSync } from 'node:fs';
import { resolve } from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [
      react(),
      {
        name: 'exclude-demo-assets',
        closeBundle() {
          if (mode !== 'demo') {
            for (const file of ['mockServiceWorker.js', 'demo-report.pdf'])
              rmSync(resolve(import.meta.dirname, 'dist', file), { force: true });
          }
        },
      },
    ],
    server: {
      proxy: {
        '/api': {
          target: process.env.API_PROXY_TARGET ?? env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    build: { sourcemap: true },
  };
});
