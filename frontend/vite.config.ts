import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, /api is proxied to the FastAPI server. In Docker, nginx does the same.
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, proxy: { '/api': process.env.API_URL || 'http://localhost:8000' } },
  preview: { port: 4173, proxy: { '/api': process.env.API_URL || 'http://localhost:8000' } },
})
