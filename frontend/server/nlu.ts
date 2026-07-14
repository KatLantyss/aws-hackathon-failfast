import type { IncomingMessage, ServerResponse } from 'node:http'
import Anthropic from '@anthropic-ai/sdk'
import type { NluRequestBody, NluResult } from '../src/types/chat.ts'
import { readJsonBody } from './readBody.ts'

// Real competition ships (S1-S23)
const REAL_SHIPS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12','S21','S22','S23']

const EMIT_ANSWER_TOOL = {
  name: 'emit_answer',
  description:
    'Classify the fleet-ops question into a structured intent and extract parameters. Never invent factual conclusions (fuel numbers, dates, percentages) — those come from the real dashboard data, not you.',
  input_schema: {
    type: 'object' as const,
    properties: {
      intent: {
        type: 'string',
        enum: [
          'vessel_overview',
          'fleet_ranking',
          'fuel_attribution',
          'compare_vessels',
          'single_fact',
          'follow_up',
          'out_of_scope',
        ],
      },
      vessels: {
        type: 'array',
        description:
          'Resolved vessel(s) from the known fleet list this question refers to. 1 vessel for vessel_overview/fuel_attribution/single_fact/follow_up, 2 for compare_vessels, 0 for fleet_ranking/out_of_scope.',
        items: {
          type: 'object',
          properties: {
            imo: { type: 'string' },
            name: { type: 'string' },
          },
          required: ['imo', 'name'],
        },
      },
      vesselNotFound: {
        type: 'boolean',
        description: 'True if the user named a specific vessel that is not in the known fleet list.',
      },
      vesselGuess: {
        type: ['string', 'null'],
        description: 'Best-guess closest real vessel name when vesselNotFound is true, else null.',
      },
      factType: {
        type: ['string', 'null'],
        enum: ['last_hull_cleaning', 'last_drydock', 'next_drydock', 'current_speed_loss', 'fouling_grade', null],
        description: 'Only set when intent is single_fact.',
      },
      clarifyingNote: {
        type: 'string',
        description:
          'One short Traditional Chinese phrase paraphrasing what you understood the user to be asking, e.g. "查詢 YM WELLNESS 目前狀況". For out_of_scope, a short explanation of why it is out of scope instead.',
      },
      outOfScopeExamples: {
        type: ['array', 'null'],
        items: { type: 'string' },
        description: '2-3 example in-scope questions in Traditional Chinese, only when intent is out_of_scope.',
      },
    },
    required: ['intent', 'vessels', 'vesselNotFound', 'vesselGuess', 'factType', 'clarifyingNote', 'outOfScopeExamples'],
  },
}

function buildSystemPrompt(): string {
  const fleetList = REAL_SHIPS.join(', ')
  return `你是陽明海運船隊維運 Dashboard 裡的語音/文字助理。使用者會用自然語言詢問船隊狀況、維修建議、油耗歸因或比較船舶。

已知船隊（唯一可解析的船舶代號來源，不可自己編造）：${fleetList}

規則：
- 只負責判斷意圖分類與抽取參數，絕對不要自己編造任何數字、日期或結論（那些會由畫面上的真實資料呈現）。
- 使用者提到的船名若不在上面的清單裡，設 vesselNotFound=true，並在 vesselGuess 給一個清單裡最接近的代號；vessels 留空陣列。
- 若問題與船隊維運資料無關（天氣、閒聊、其他公司事務等），intent 設為 out_of_scope，並在 outOfScopeExamples 給 2-3 個範例問題。
- 若使用者是針對前一輪的追問（例如「信心程度多高」「上個月呢」），intent 設為 follow_up。
- 一定要呼叫 emit_answer 工具回答，不要輸出其他文字。`
}

export async function handleNlu(
  req: IncomingMessage,
  res: ServerResponse,
  env: { ANTHROPIC_API_KEY?: string; ANTHROPIC_MODEL?: string },
) {
  res.setHeader('Content-Type', 'application/json')

  if (!env.ANTHROPIC_API_KEY) {
    res.statusCode = 500
    res.end(JSON.stringify({ error: 'ANTHROPIC_API_KEY is not set in .env' }))
    return
  }

  try {
    const body = await readJsonBody<NluRequestBody>(req)
    if (!body.message || !body.message.trim()) {
      res.statusCode = 400
      res.end(JSON.stringify({ error: 'message is required' }))
      return
    }

    const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY })
    const response = await client.messages.create({
      model: env.ANTHROPIC_MODEL || 'claude-sonnet-5',
      max_tokens: 1024,
      system: buildSystemPrompt(),
      messages: [
        ...body.history.slice(-6).map((m) => ({ role: m.role, content: m.content })),
        { role: 'user' as const, content: body.message },
      ],
      tools: [EMIT_ANSWER_TOOL],
      tool_choice: { type: 'tool', name: 'emit_answer' },
    })

    const toolUse = response.content.find((block) => block.type === 'tool_use')
    if (!toolUse || toolUse.type !== 'tool_use') {
      res.statusCode = 502
      res.end(JSON.stringify({ error: 'Claude did not return a structured answer' }))
      return
    }

    const result = toolUse.input as NluResult
    res.statusCode = 200
    res.end(JSON.stringify(result))
  } catch (err) {
    res.statusCode = 500
    res.end(JSON.stringify({ error: err instanceof Error ? err.message : 'NLU request failed' }))
  }
}
