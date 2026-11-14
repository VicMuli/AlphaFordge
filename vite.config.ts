import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    host: '0.0.0.0',
    port: 3000,
    hmr: false,
    ws: false,
    allowedHosts: true,
    watch: {
      ignored: [
        '**/market_data/**',
        '**/researched_strategies/**',
        '**/optimization_runs/**',
        '**/backup_temp/**',
        '**/.aistudio/**',
        '**/dist/**',
        '**/__pycache__/**',
      ],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
