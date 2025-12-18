import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 开发环境代理：将 /tasks 等 API 请求转发给 FastAPI (8000)
      '/tasks': 'http://127.0.0.1:8000',
      '/settings': 'http://127.0.0.1:8000'
    }
  },
  build: {
    // 构建输出目录直接指向后端的 static 文件夹
    outDir: '../app/static',
    emptyOutDir: true, // 构建前清空 static 目录
  }
})