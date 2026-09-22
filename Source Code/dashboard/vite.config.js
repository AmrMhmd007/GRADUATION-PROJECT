import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to every network interface, not just localhost — this is what
    // lets a TA's phone on the same Wi-Fi/campus network open the dashboard
    // at http://<this-mac's-lan-ip>:5173 instead of only working on this
    // machine. Combined with client.js's runtime API-host detection, no
    // per-device config is needed.
    host: true,
  },
})
