import type { Connect, Plugin, ViteDevServer, PreviewServer } from 'vite'
import { handleNlu } from './nlu.ts'
import { handleStt } from './stt.ts'

export interface VoicebotEnv {
  ANTHROPIC_API_KEY?: string
  ANTHROPIC_MODEL?: string
  OPENAI_API_KEY?: string
  OPENAI_STT_MODEL?: string
}

function registerRoutes(middlewares: Connect.Server, env: VoicebotEnv) {
  middlewares.use('/api/nlu', (req, res) => {
    if (req.method !== 'POST') {
      res.statusCode = 405
      res.end('Method Not Allowed')
      return
    }
    void handleNlu(req, res, env)
  })

  middlewares.use('/api/stt', (req, res) => {
    if (req.method !== 'POST') {
      res.statusCode = 405
      res.end('Method Not Allowed')
      return
    }
    void handleStt(req, res, env)
  })
}

/** Local dev-time proxy for the VoiceBot overlay's Claude (NLU) and OpenAI (STT) calls, so API keys never reach the browser. */
export function voicebotApiPlugin(env: VoicebotEnv): Plugin {
  return {
    name: 'voicebot-api-proxy',
    configureServer(server: ViteDevServer) {
      registerRoutes(server.middlewares, env)
    },
    configurePreviewServer(server: PreviewServer) {
      registerRoutes(server.middlewares, env)
    },
  }
}
