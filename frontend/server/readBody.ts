import type { IncomingMessage } from 'node:http'

export function readRawBody(req: IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = []
    req.on('data', (chunk) => chunks.push(chunk))
    req.on('end', () => resolve(Buffer.concat(chunks)))
    req.on('error', reject)
  })
}

export async function readJsonBody<T>(req: IncomingMessage): Promise<T> {
  const raw = await readRawBody(req)
  return JSON.parse(raw.toString('utf-8')) as T
}
