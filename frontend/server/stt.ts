import type { IncomingMessage, ServerResponse } from 'node:http'
import OpenAI, { toFile } from 'openai'
import { readRawBody } from './readBody.ts'

export async function handleStt(
  req: IncomingMessage,
  res: ServerResponse,
  env: { OPENAI_API_KEY?: string; OPENAI_STT_MODEL?: string },
) {
  res.setHeader('Content-Type', 'application/json')

  if (!env.OPENAI_API_KEY) {
    res.statusCode = 500
    res.end(JSON.stringify({ error: 'OPENAI_API_KEY is not set in .env' }))
    return
  }

  try {
    const audio = await readRawBody(req)
    if (audio.length === 0) {
      res.statusCode = 400
      res.end(JSON.stringify({ error: 'Empty audio payload' }))
      return
    }

    const contentType = req.headers['content-type'] || 'audio/webm'
    const client = new OpenAI({ apiKey: env.OPENAI_API_KEY })
    const transcription = await client.audio.transcriptions.create({
      file: await toFile(audio, 'speech.webm', { type: contentType }),
      model: env.OPENAI_STT_MODEL || 'whisper-1',
    })

    res.statusCode = 200
    res.end(JSON.stringify({ text: transcription.text.trim() }))
  } catch (err) {
    res.statusCode = 500
    res.end(JSON.stringify({ error: err instanceof Error ? err.message : 'STT request failed' }))
  }
}
