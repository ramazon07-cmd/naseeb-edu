import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api goes to Django from the same origin as the app, so the HttpOnly refresh
// cookie (SameSite=Strict, Path=/api/auth/) is first-party in development. The
// Host header is kept: Django then sees the app's own origin.
const apiProxy = { '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000' } }

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/src/translations/')) return 'translations'
          if (id.includes('/node_modules/lucide-react/')) return 'icons'
          if (id.includes('/node_modules/react/') || id.includes('/node_modules/react-dom/')) return 'react-vendor'
          // The Essay Lab editor engine: only the lazy editor chunk imports it.
          if (/\/node_modules\/(@tiptap|prosemirror-[a-z-]+|linkifyjs|orderedmap|rope-sequence|w3c-keyname)\//.test(id)) return 'editor-vendor'
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: apiProxy,
  },
  preview: {
    port: 4173,
    proxy: apiProxy,
  },
})
