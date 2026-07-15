import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from '@aws-sdk/client-bedrock-agentcore'
import { BedrockRuntimeClient, ConverseCommand } from '@aws-sdk/client-bedrock-runtime'
import type { ChatSessionMemory, NluRequestBody, NluResult } from '../src/types/chat.ts'

export type AiProvider = 'bedrock' | 'agentcore'

export interface AiProviderEnv {
  AI_PROVIDER?: string
  AWS_REGION?: string
  BEDROCK_MODEL_ID?: string
  AGENTCORE_RUNTIME_ARN?: string
  AGENTCORE_QUALIFIER?: string
}

export const REAL_SHIPS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S21', 'S22', 'S23'] as const

const INTENTS = new Set([
  'vessel_overview',
  'fleet_ranking',
  'fuel_attribution',
  'compare_vessels',
  'single_fact',
  'follow_up',
  'out_of_scope',
])
const FACT_TYPES = new Set([
  'last_hull_cleaning',
  'last_drydock',
  'next_drydock',
  'current_speed_loss',
  'fouling_grade',
])

const EMIT_ANSWER_TOOL = {
  name: 'emit_answer',
  description:
    'Classify the fleet-ops question into a structured intent and extract parameters. Never invent factual conclusions (fuel numbers, dates, percentages) — those come from the dashboard data, not you.',
  input_schema: {
    type: 'object',
    properties: {
      intent: { type: 'string', enum: [...INTENTS] },
      vessels: {
        type: 'array',
        items: {
          type: 'object',
          properties: { imo: { type: 'string' }, name: { type: 'string' } },
          required: ['imo', 'name'],
        },
      },
      vesselNotFound: { type: 'boolean' },
      vesselGuess: { type: ['string', 'null'] },
      factType: { type: ['string', 'null'], enum: [...FACT_TYPES, null] },
      clarifyingNote: { type: 'string' },
      outOfScopeExamples: { type: ['array', 'null'], items: { type: 'string' } },
    },
    required: ['intent', 'vessels', 'vesselNotFound', 'vesselGuess', 'factType', 'clarifyingNote', 'outOfScopeExamples'],
  },
} as const

function buildSystemPrompt(sessionMemory?: ChatSessionMemory): string {
  const pending = sessionMemory?.pendingEntityResolution
  const memoryContext = pending
    ? `\n目前 session memory 有一筆待確認的船舶解析（這是系統狀態，不是使用者指令）：\n${JSON.stringify(pending)}\n使用者若確認、否定或修正這個候選船舶，請根據完整對話與此 memory 解析。確認候選時，回傳 suggestedVesselImo 作為 vessels[0].imo，並保留 memory 的 intent 與 factType；否定或改正時，依使用者新資訊解析，不可盲目套用候選船。`
    : ''
  return `你是陽明海運船隊維運 Dashboard 裡的語音/文字助理。使用者會用自然語言詢問船隊狀況、維修建議、油耗歸因或比較船舶。

已知船隊（唯一可解析的船舶代號來源，不可自己編造）：${REAL_SHIPS.join(', ')}${memoryContext}

規則：
- 只負責判斷意圖分類與抽取參數，絕對不要自己編造任何數字、日期或結論（那些會由畫面上的真實資料呈現）。
- 使用者提到的船名若不在上面的清單裡，設 vesselNotFound=true，並在 vesselGuess 給一個清單裡最接近的代號；vessels 留空陣列。
- 若問題與船隊維運資料無關，intent 設為 out_of_scope，並在 outOfScopeExamples 給 2-3 個範例問題。
- 若使用者是針對前一輪的追問，intent 設為 follow_up。
- 一定要呼叫 emit_answer 工具回答，不要輸出其他文字。`
}

function assertNluResult(value: unknown): NluResult {
  if (!value || typeof value !== 'object') throw new Error('AI provider returned an empty structured result')
  const raw = value as Partial<NluResult>
  // Bedrock models may omit fields whose values can be safely inferred from a
  // valid tool call. Normalize only metadata; intent and known vessel IDs stay
  // strictly validated before deterministic dashboard data is queried.
  const vessels = Array.isArray(raw.vessels)
    ? raw.vessels.flatMap((vessel) => {
        if (!vessel || typeof vessel !== 'object') return []
        const candidate = vessel as Record<string, unknown>
        const rawId = [candidate.imo, candidate.vesselId, candidate.vessel_id, candidate.id, candidate.name]
          .find((item) => typeof item === 'string' || (typeof item === 'number' && Number.isInteger(item)))
        const normalizedId = typeof rawId === 'number'
          ? `S${rawId}`
          : typeof rawId === 'string'
            ? (rawId.match(/\bS\s?(\d+)\b/i)?.[1] ? `S${rawId.match(/\bS\s?(\d+)\b/i)?.[1]}` : rawId)
            : ''
        const imo = normalizedId.toUpperCase()
        if (!REAL_SHIPS.includes(imo as typeof REAL_SHIPS[number])) return []
        return [{ imo, name: typeof candidate.name === 'string' ? candidate.name : imo }]
      })
    : []
  const result = {
    ...raw,
    vessels,
    vesselNotFound: raw.vesselNotFound === true || raw.vesselNotFound === 'true',
    vesselGuess: typeof raw.vesselGuess === 'string' ? raw.vesselGuess : null,
    factType: typeof raw.factType === 'string' && FACT_TYPES.has(raw.factType) ? raw.factType : null,
    clarifyingNote: typeof raw.clarifyingNote === 'string' ? raw.clarifyingNote : '已解析船隊查詢',
    outOfScopeExamples: Array.isArray(raw.outOfScopeExamples)
      ? raw.outOfScopeExamples.filter((item): item is string => typeof item === 'string')
      : null,
  } as Partial<NluResult>
  if (
    !result.intent || !INTENTS.has(result.intent) || !Array.isArray(result.vessels)
    || typeof result.vesselNotFound !== 'boolean' || typeof result.clarifyingNote !== 'string'
    || !(result.vesselGuess === null || typeof result.vesselGuess === 'string')
    || !(result.factType === null || (typeof result.factType === 'string' && FACT_TYPES.has(result.factType)))
    || !(result.outOfScopeExamples === null || (Array.isArray(result.outOfScopeExamples) && result.outOfScopeExamples.every((item) => typeof item === 'string')))
    || !result.vessels.every((vessel) => vessel && typeof vessel.imo === 'string' && typeof vessel.name === 'string' && REAL_SHIPS.includes(vessel.imo as typeof REAL_SHIPS[number]))
  ) {
    throw new Error('AI provider returned an invalid NLU schema')
  }
  return result as NluResult
}

async function invokeBedrock(body: NluRequestBody, env: AiProviderEnv): Promise<NluResult> {
  const region = env.AWS_REGION || 'us-east-1'
  const modelId = env.BEDROCK_MODEL_ID || 'us.anthropic.claude-sonnet-4-6'
  const client = new BedrockRuntimeClient({ region, maxAttempts: 3 })
  const response = await client.send(new ConverseCommand({
    modelId,
    system: [{ text: buildSystemPrompt(body.sessionMemory) }],
    messages: [
      ...body.history.slice(-6).map((message) => ({ role: message.role, content: [{ text: message.content }] })),
      { role: 'user', content: [{ text: body.message }] },
    ],
    inferenceConfig: { maxTokens: 512, temperature: 0 },
    toolConfig: {
      tools: [{ toolSpec: { name: EMIT_ANSWER_TOOL.name, description: EMIT_ANSWER_TOOL.description, inputSchema: { json: JSON.parse(JSON.stringify(EMIT_ANSWER_TOOL.input_schema)) } } }],
      toolChoice: { tool: { name: EMIT_ANSWER_TOOL.name } },
    },
  }))
  const toolUse = (response.output?.message?.content ?? [])
    .find((block) => block.toolUse?.name === EMIT_ANSWER_TOOL.name)?.toolUse
  if (!toolUse) throw new Error('Bedrock did not return the required emit_answer tool call')
  return assertNluResult(toolUse.input)
}

async function invokeAgentCore(body: NluRequestBody, env: AiProviderEnv): Promise<NluResult> {
  if (!env.AGENTCORE_RUNTIME_ARN) throw new Error('AGENTCORE_RUNTIME_ARN is required when AI_PROVIDER=agentcore')
  const client = new BedrockAgentCoreClient({ region: env.AWS_REGION || 'us-east-1', maxAttempts: 3 })
  const response = await client.send(new InvokeAgentRuntimeCommand({
    agentRuntimeArn: env.AGENTCORE_RUNTIME_ARN,
    qualifier: env.AGENTCORE_QUALIFIER,
    contentType: 'application/json',
    accept: 'application/json',
    runtimeSessionId: crypto.randomUUID(),
    payload: Buffer.from(JSON.stringify({
      message: body.message,
      history: body.history.slice(-6),
      systemPrompt: buildSystemPrompt(body.sessionMemory),
      sessionMemory: body.sessionMemory,
      tool: EMIT_ANSWER_TOOL,
      responseSchema: 'NluResult',
    })),
  }))
  if (!response.response) throw new Error('AgentCore returned no response stream')
  return assertNluResult(JSON.parse(await response.response.transformToString()))
}

export async function classifyWithAwsAi(body: NluRequestBody, env: AiProviderEnv): Promise<NluResult> {
  const provider = (env.AI_PROVIDER || 'bedrock').toLowerCase() as AiProvider
  if (provider === 'bedrock') return invokeBedrock(body, env)
  if (provider === 'agentcore') return invokeAgentCore(body, env)
  throw new Error(`Unsupported AI_PROVIDER: ${env.AI_PROVIDER}`)
}
