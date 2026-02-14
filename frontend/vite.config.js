import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 从环境变量读取端口，默认为3000
const port = process.env.VITE_PORT ? parseInt(process.env.VITE_PORT) : 3000

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    cors: true,
    host: '0.0.0.0',
    port,
    proxy: {
      '/api': 'http://localhost:5000',
      '/ws': {
        target: 'ws://localhost:8765',
        ws: true
      }
    }
  }
})
