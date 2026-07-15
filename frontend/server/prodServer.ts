import { createServer } from 'node:http'
import sirv from 'sirv'
import { handleNlu } from './nlu.ts'
import { handleStt } from './stt.ts'

const env = {
  AI_PROVIDER: process.env.AI_PROVIDER,
  AWS_REGION: process.env.AWS_REGION,
  BEDROCK_MODEL_ID: process.env.BEDROCK_MODEL_ID,
  AGENTCORE_RUNTIME_ARN: process.env.AGENTCORE_RUNTIME_ARN,
  AGENTCORE_QUALIFIER: process.env.AGENTCORE_QUALIFIER,
  OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  OPENAI_STT_MODEL: process.env.OPENAI_STT_MODEL,
}

const serveStatic = sirv('dist', {
  single: true,
  gzip: true,
  etag: true,
  setHeaders(res, pathname) {
    // Hashed filenames (e.g. /assets/index-<hash>.js) change whenever their
    // content changes, so they're safe to cache forever. index.html has a
    // stable name across deploys but its content (which hashed files it
    // references) changes — it must always be revalidated, or browsers can
    // serve a stale index.html pointing at assets that no longer exist in a
    // newer deploy, producing a blank page until a hard refresh.
    if (pathname === '/index.html' || pathname === '/') {
      res.setHeader('Cache-Control', 'no-cache')
    } else if (pathname.startsWith('/assets/')) {
      res.setHeader('Cache-Control', 'public, max-age=31536000, immutable')
    }
  },
})
const port = Number(process.env.PORT) || 8080

createServer((req, res) => {
  if (req.url === '/api/nlu' && req.method === 'POST') {
    void handleNlu(req, res, env)
    return
  }
  if (req.url === '/api/stt' && req.method === 'POST') {
    void handleStt(req, res, env)
    return
  }
  if (req.url === '/health') {
    res.statusCode = 200
    res.end('ok')
    return
  }
  serveStatic(req, res, () => {
    res.statusCode = 404
    res.end('Not found')
  })
}).listen(port, () => {
  console.log(`listening on :${port}`)
})
