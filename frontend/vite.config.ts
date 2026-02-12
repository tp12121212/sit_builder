import fs from 'node:fs'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const devPort = Number.parseInt(env.VITE_DEV_PORT ?? '443', 10)
  const httpsCertPath = env.VITE_DEV_HTTPS_CERT_PATH
  const httpsKeyPath = env.VITE_DEV_HTTPS_KEY_PATH
  const hasHttpsFiles = !!(
    httpsCertPath &&
    httpsKeyPath &&
    fs.existsSync(httpsCertPath) &&
    fs.existsSync(httpsKeyPath)
  )

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: Number.isFinite(devPort) ? devPort : 443,
      strictPort: true,
      https: hasHttpsFiles
        ? {
            cert: fs.readFileSync(httpsCertPath),
            key: fs.readFileSync(httpsKeyPath),
          }
        : undefined,
      proxy: {
        '/v1': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          ws: true,
        },
        '/health': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
