import { readFileSync } from 'node:fs'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { checkBuildApiConfig } from './scripts/api-config.mjs'
import { injectSessionKey } from './src/sessionKeys.js'
import { i18nDictionaries } from './scripts/i18n-plugin.mjs'

// /api goes to Django from the same origin as the app, so the HttpOnly refresh
// cookie (Path=/api/auth/) is first-party in development. The Host header is
// kept: Django then sees the app's own origin.
const apiProxy = { '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000' } }

// index.html's inline boot script reads the same session key as the app.
const sessionKey = { name: 'naseeb-session-key', transformIndexHtml: injectSessionKey }

// frontend/VERSION holds MAJOR.MINOR.PATCH.BUILD. It lives inside frontend/ so it is part of the Docker build
// context and of a Vercel project rooted at frontend/. A missing file falls back to 0.0.0.0; a malformed one fails the build.
function readAppVersion() {
  let text
  try { text = readFileSync(new URL('./VERSION', import.meta.url), 'utf8').trim() } catch { return '0.0.0.0' }
  if (!/^\d+\.\d+\.\d+\.\d+$/.test(text)) throw new Error(`VERSION must look like 1.2.3.4, got "${text}"`)
  return text
}
const appVersion = readAppVersion()

export default defineConfig(({ command, mode }) => {
  // A deploy that could not reach the API (e.g. Vercel without
  // NASEEB_API_ORIGIN) fails here instead of serving index.html for /api.
  if (command === 'build') checkBuildApiConfig({ ...loadEnv(mode, process.cwd(), ''), ...process.env })
  return config
})

const config = {
  define: { __APP_VERSION__: JSON.stringify(appVersion) },
  plugins: [react(), sessionKey, i18nDictionaries()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // One chunk per language dictionary (see scripts/i18n-plugin.mjs).
          if (id.startsWith('\0virtual:i18n/')) return `i18n-${id.slice('\0virtual:i18n/'.length)}`
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
}
