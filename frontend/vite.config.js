import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: './',
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8008',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/setup.js',
    css: false,
    include: ['tests/**/*.test.{js,jsx}'],
  },
})
