import path from 'node:path';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * Výstup do app/web/react/vehicle-list/ (relativně k tomuto souboru: ../web/react/vehicle-list).
 * Base musí odpovídat cestě, pod kterou budou assety v produkci servírovány z FastAPI /web/…
 */
const outDir = path.resolve(__dirname, '../web/react/vehicle-list');

export default defineConfig({
  plugins: [react()],
  base: '/web/react/vehicle-list/',
  build: {
    outDir,
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
