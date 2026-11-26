import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
          vue: ['vue']
        }
      }
    }
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
