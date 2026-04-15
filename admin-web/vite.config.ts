import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5174,
    host: '0.0.0.0',
    proxy: {
      '/admin': {
        target: process.env.VITE_ADMIN_API_TARGET || 'http://localhost:19000',
        changeOrigin: true,
      },
      '/health': {
        target: process.env.VITE_ADMIN_API_TARGET || 'http://localhost:19000',
        changeOrigin: true,
      },
    },
  },
})
