import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/ors-api': {
        target: 'https://api.openrouteservice.org',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/ors-api/, ''),
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
