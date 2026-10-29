import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: Number(process.env.WEB_PORT ?? 5173),
    // 5001, not 5000: macOS uses 5000 for AirPlay Receiver and Flask can't start there.
    proxy: { '/api': `http://127.0.0.1:${process.env.API_PORT ?? 5001}` },
  },
})
