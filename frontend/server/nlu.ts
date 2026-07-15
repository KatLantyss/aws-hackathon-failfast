import type { IncomingMessage, ServerResponse } from 'node:http'
import type { NluRequestBody } from '../src/types/chat.ts'
import { classifyWithAwsAi, type AiProviderEnv } from './aiProvider.ts'
import { readJsonBody } from './readBody.ts'

export async function handleNlu(
  req: IncomingMessage,
  res: ServerResponse,
  env: AiProviderEnv,
) {
  res.setHeader('Content-Type', 'application/json')

  try {
    const body = await readJsonBody<NluRequestBody>(req)
    if (!body.message || !body.message.trim()) {
      res.statusCode = 400
      res.end(JSON.stringify({ error: 'message is required' }))
      return
    }

    const result = await classifyWithAwsAi(body, env)
    res.statusCode = 200
    res.end(JSON.stringify(result))
  } catch (err) {
    res.statusCode = 502
    res.end(JSON.stringify({
      error: err instanceof Error ? err.message : 'AWS AI request failed',
    }))
  }
}
