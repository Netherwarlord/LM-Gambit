// defineConfig comes from vitest/config rather than vite so the `test` block
// below type-checks; it is vite's own, widened with Vitest's options.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The Python server owns /api. In dev, Vite serves the UI on :5173 and proxies
// API + SSE calls through to uvicorn on :8765 so both share one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        // Server-sent events must not be buffered by the proxy.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              delete proxyRes.headers['content-length']
            }
          })
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Only our own tests; node_modules and the built bundle are not ours.
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
