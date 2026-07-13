import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import basicSsl from '@vitejs/plugin-basic-ssl'
import { voicebotApiPlugin } from './server/voicebotApiPlugin.ts'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // getUserMedia/AudioContext require a secure context — a plain http://
  // LAN address (e.g. testing on a phone via http://192.168.x.x:5173) does
  // NOT count as one, so the VoiceBot mic silently can't start there. Run
  // `npm run dev:mobile` to serve over a self-signed https:// cert instead.
  const useHttps = process.env.HTTPS === 'true'

  return {
    plugins: [
      vue(),
      tailwindcss(),
      ...(useHttps ? [basicSsl()] : []),
      voicebotApiPlugin({
        ANTHROPIC_API_KEY: env.ANTHROPIC_API_KEY,
        ANTHROPIC_MODEL: env.ANTHROPIC_MODEL,
        OPENAI_API_KEY: env.OPENAI_API_KEY,
        OPENAI_STT_MODEL: env.OPENAI_STT_MODEL,
      }),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
  }
})
