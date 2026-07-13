import {
  fetchFleetVessels,
  fetchFuelAttribution,
  fetchMaintenanceRecommendation,
  fetchSpeedLoss,
  fetchVessel,
} from '@/mock/api'
import { VESSEL_REFS } from '@/mock/reference'
import { CONFIDENCE_LABEL } from '@/utils/format'
import type { ChatCardSpec, ChatFactType, ChatTurn, NluResult } from '@/types/chat'

const INTENT_LABEL: Record<NluResult['intent'], string> = {
  vessel_overview: '目前狀況',
  fleet_ranking: '優先排行',
  fuel_attribution: '油耗歸因',
  compare_vessels: '污損比較',
  single_fact: '快速查詢',
  follow_up: '追問',
  out_of_scope: '超出範疇',
}

const FACT_TYPE_LABEL: Record<ChatFactType, string> = {
  last_hull_cleaning: '上次船體清洗',
  last_drydock: '上次坐塢',
  next_drydock: '下次坐塢',
  current_speed_loss: '目前 Speed Loss',
  fouling_grade: '污損等級',
}

function makeId() {
  return `turn-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function vesselNotFoundTurn(userText: string, vesselGuess: string | null): ChatTurn {
  const replyText = vesselGuess
    ? `找不到符合的船，你是不是指「${vesselGuess}」？`
    : `找不到符合的船，目前船隊有：${VESSEL_REFS.map((v) => v.name).join('、')}。`
  return {
    id: makeId(),
    userText,
    intent: 'out_of_scope',
    replyText,
    cards: [],
    vesselImo: null,
    vesselName: null,
    breadcrumbLabel: '查無此船',
  }
}

function outOfScopeTurn(userText: string, nlu: NluResult): ChatTurn {
  const examples = nlu.outOfScopeExamples?.length
    ? `\n\n你可以試著問：\n${nlu.outOfScopeExamples.map((e) => `・${e}`).join('\n')}`
    : ''
  return {
    id: makeId(),
    userText,
    intent: 'out_of_scope',
    replyText: `${nlu.clarifyingNote}${examples}`,
    cards: [],
    vesselImo: null,
    vesselName: null,
    breadcrumbLabel: INTENT_LABEL.out_of_scope,
  }
}

/** "Which vessel do you mean?" — asked instead of dead-ending when a vessel-dependent intent has no resolved vessel. Records what to resume once one is given. */
function vesselClarificationTurn(userText: string, intent: NluResult['intent'], factType: ChatFactType | null): ChatTurn {
  const topicLabel = factType ? FACT_TYPE_LABEL[factType] : INTENT_LABEL[intent]
  return {
    id: makeId(),
    userText,
    intent,
    replyText: `請問是想查詢哪一艘船的「${topicLabel}」？目前船隊有：${VESSEL_REFS.map((v) => v.name).join('、')}，直接說船名即可。`,
    cards: [],
    vesselImo: null,
    vesselName: null,
    breadcrumbLabel: `${topicLabel} › 請選船隻`,
    awaitingVesselFor: { intent, factType },
  }
}

function findConfidence(cards: ChatCardSpec[]): 'high' | 'medium' | 'low' | null {
  for (const card of cards) {
    if (card.type === 'maintenance' || card.type === 'fuelWaterfall') return card.data.confidence
  }
  return null
}

function factAnswer(factType: ChatFactType, vessel: Awaited<ReturnType<typeof fetchVessel>>, lastHullCleaningDate: string | null): string {
  if (!vessel) return '目前查無這艘船的資料。'
  switch (factType) {
    case 'last_hull_cleaning':
      return lastHullCleaningDate ? `上次船體清洗日期為 ${lastHullCleaningDate}。` : `尚無船體清洗紀錄，最近一次坐塢為 ${vessel.lastDrydockDate}。`
    case 'last_drydock':
      return `上次坐塢日期為 ${vessel.lastDrydockDate}。`
    case 'next_drydock':
      return `下次預計坐塢日期為 ${vessel.nextDrydockDue}。`
    case 'current_speed_loss':
      return `目前 Speed Loss 為 ${vessel.speedLossPct.toFixed(1)}%。`
    case 'fouling_grade':
      return `目前船體污損等級為「${vessel.foulingGrade}」。`
  }
}

/** Resolves a Claude-classified intent into a ChatTurn using only real mock/api.ts data — the LLM never supplies the final numbers. */
export async function resolveChatTurn(userTextRaw: string, nluRaw: NluResult, previousTurn: ChatTurn | null): Promise<ChatTurn> {
  const userText = userTextRaw

  if (nluRaw.vesselNotFound) {
    return vesselNotFoundTurn(userText, nluRaw.vesselGuess)
  }

  // Resuming a pending "which vessel?" clarification — as long as this reply
  // resolved a vessel, finish the ORIGINAL request rather than whatever
  // intent Claude guessed for a message that might just be a bare ship name.
  const pending = previousTurn?.awaitingVesselFor
  const nlu: NluResult = pending && nluRaw.vessels[0] ? { ...nluRaw, intent: pending.intent, factType: pending.factType } : nluRaw

  if (nlu.intent === 'out_of_scope') {
    return outOfScopeTurn(userText, nlu)
  }

  if (nlu.intent === 'follow_up') {
    if (!previousTurn) return outOfScopeTurn(userText, nlu)
    const confidence = findConfidence(previousTurn.cards)
    const replyText = confidence
      ? `信心程度為「${CONFIDENCE_LABEL[confidence]}」。`
      : `${nlu.clarifyingNote}——目前資料如上方卡片所示，暫無法進一步細分。`
    return {
      id: makeId(),
      userText,
      intent: 'follow_up',
      replyText,
      cards: previousTurn.cards,
      vesselImo: previousTurn.vesselImo,
      vesselName: previousTurn.vesselName,
      breadcrumbLabel: `${previousTurn.breadcrumbLabel} › 追問`,
    }
  }

  if (nlu.intent === 'fleet_ranking') {
    const vessels = await fetchFleetVessels()
    const ranked = [...vessels]
      .sort((a, b) => b.speedLossPct - a.speedLossPct)
      .slice(0, 3)
    const replyText = ranked.length
      ? `目前優先需要安排維修的船舶：${ranked.map((v) => v.name).join('、')}。`
      : '目前船隊沒有維修優先建議。'
    return {
      id: makeId(),
      userText,
      intent: 'fleet_ranking',
      replyText,
      cards: [{ type: 'ranking', vessels: ranked }],
      vesselImo: null,
      vesselName: null,
      breadcrumbLabel: INTENT_LABEL.fleet_ranking,
    }
  }

  if (nlu.intent === 'compare_vessels') {
    const [va, vb] = nlu.vessels
    if (!va || !vb) return outOfScopeTurn(userText, nlu)
    const [vesselA, vesselB, seriesA, seriesB] = await Promise.all([
      fetchVessel(va.imo),
      fetchVessel(vb.imo),
      fetchSpeedLoss(va.imo),
      fetchSpeedLoss(vb.imo),
    ])
    if (!vesselA || !vesselB || !seriesA || !seriesB) return outOfScopeTurn(userText, nlu)
    const worse = vesselA.speedLossPct >= vesselB.speedLossPct ? vesselA : vesselB
    return {
      id: makeId(),
      userText,
      intent: 'compare_vessels',
      replyText: `${vesselA.name} 目前 Speed Loss ${vesselA.speedLossPct.toFixed(1)}%，${vesselB.name} 為 ${vesselB.speedLossPct.toFixed(1)}%，${worse.name} 船體污損較嚴重。`,
      cards: [{ type: 'compare', a: { vessel: vesselA, series: seriesA }, b: { vessel: vesselB, series: seriesB } }],
      vesselImo: null,
      vesselName: `${vesselA.name} / ${vesselB.name}`,
      breadcrumbLabel: `${vesselA.name} vs ${vesselB.name} › ${INTENT_LABEL.compare_vessels}`,
    }
  }

  // remaining intents (vessel_overview / fuel_attribution / single_fact) all need exactly one resolved vessel
  const target = nlu.vessels[0]
  if (!target) return vesselClarificationTurn(userText, nlu.intent, nlu.factType)

  if (nlu.intent === 'single_fact') {
    const [vessel, series] = await Promise.all([fetchVessel(target.imo), fetchSpeedLoss(target.imo)])
    const lastHullCleaning = series?.events.filter((e) => e.type === 'hull_cleaning').map((e) => e.date).sort().pop() ?? null
    const factType = nlu.factType ?? 'current_speed_loss'
    return {
      id: makeId(),
      userText,
      intent: 'single_fact',
      replyText: factAnswer(factType, vessel, lastHullCleaning),
      cards: [],
      vesselImo: target.imo,
      vesselName: target.name,
      breadcrumbLabel: `${target.name} › ${INTENT_LABEL.single_fact}`,
    }
  }

  if (nlu.intent === 'fuel_attribution') {
    const [vessel, attribution] = await Promise.all([fetchVessel(target.imo), fetchFuelAttribution(target.imo)])
    if (!vessel || !attribution) return outOfScopeTurn(userText, nlu)
    const top = [...attribution.attribution].sort((a, b) => b.impactMt - a.impactMt)[0]
    const excessMt = attribution.actualFuelMt - attribution.baselineFuelMt
    const pct = excessMt > 0 ? ((top.impactMt / excessMt) * 100).toFixed(0) : '0'
    return {
      id: makeId(),
      userText,
      intent: 'fuel_attribution',
      replyText: `${vessel.name} 目前超額油耗中，${top.label}占比最高，約 ${pct}%。`,
      cards: [{ type: 'fuelWaterfall', vessel, data: attribution }],
      vesselImo: target.imo,
      vesselName: target.name,
      breadcrumbLabel: `${target.name} › ${INTENT_LABEL.fuel_attribution}`,
    }
  }

  // vessel_overview
  const [vessel, series, recommendation, fleet] = await Promise.all([
    fetchVessel(target.imo),
    fetchSpeedLoss(target.imo),
    fetchMaintenanceRecommendation(target.imo),
    fetchFleetVessels(),
  ])
  if (!vessel || !series || !recommendation) return outOfScopeTurn(userText, nlu)
  const fleetAvg = fleet.reduce((s, v) => s + v.speedLossPct, 0) / fleet.length
  const comparison = vessel.speedLossPct > fleetAvg * 1.05 ? '高於船隊平均' : vessel.speedLossPct < fleetAvg * 0.95 ? '低於船隊平均' : '接近船隊平均'
  const cards: ChatCardSpec[] = [
    { type: 'gauge', vessel },
    { type: 'speedLoss', vessel, series },
    { type: 'maintenance', vessel, data: recommendation },
  ]
  return {
    id: makeId(),
    userText,
    intent: 'vessel_overview',
    replyText: `${vessel.name} 目前 Speed Loss ${vessel.speedLossPct.toFixed(1)}%，${comparison}，建議於 ${recommendation.windowStart} 至 ${recommendation.windowEnd} 安排水下清洗。`,
    cards,
    vesselImo: target.imo,
    vesselName: target.name,
    breadcrumbLabel: `${target.name} › ${INTENT_LABEL.vessel_overview}`,
  }
}
