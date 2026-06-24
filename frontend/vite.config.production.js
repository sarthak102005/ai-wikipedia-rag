import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Production-optimized Vite config
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['react', 'react-dom', 'framer-motion'],
        }
      }
    }
  }
})
