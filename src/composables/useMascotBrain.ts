import { useRouter } from 'vue-router'
import { useFleetStore } from '@/stores/fleetStore'
import { useSpotlightStore } from '@/stores/spotlightStore'
import { predictMaintenanceWindow } from '@/utils/predictiveMaintenance'

export interface MascotReply {
  text: string
}

/**
 * Rule-based responder for the demo. Swap the body of `ask()` for a call to
 * an LLM (e.g. AWS Bedrock) that returns structured tool calls — the actions
 * below (navigateTo / highlight / openVessel) are exactly the tool surface
 * an LLM function-calling loop would invoke.
 */
export function useMascotBrain() {
  const router = useRouter()
  const fleet = useFleetStore()
  const spotlight = useSpotlightStore()

  function navigateTo(name: string) {
    router.push({ name })
  }

  function highlight(selector: string) {
    spotlight.show(selector)
  }

  function openVessel(id: string) {
    navigateTo('overview')
    setTimeout(() => {
      fleet.selectVessel(id)
      highlight(`[data-tour="ship-${id}"]`)
    }, 300)
  }

  async function ask(question: string): Promise<MascotReply> {
    const q = question.toLowerCase()

    const critical = fleet.vessels.find((v) => v.status === 'critical')
    if ((q.includes('高風險') || q.includes('風險') || q.includes('危險') || q.includes('清潔') || q.includes('拋光') || q.includes('維修')) && critical) {
      openVessel(critical.id)
      const p = predictMaintenanceWindow(critical)
      const timing = p.breached
        ? `已超過門檻，建議於下次靠港（${p.recommendedDate}）安排水下清潔`
        : `預計 ${p.daysToBreach} 天後達門檻，建議提前規劃於 ${p.recommendedDate} 靠港時清潔`
      return { text: `目前 ${critical.name} 的 Speed Loss 達 ${critical.speed_loss_pct}%，${timing}，預估可省 ${p.estFuelSavingTDay} t/day 油耗。我幫你打開它的詳細資料了 👉` }
    }

    if (q.includes('儀表板') || q.includes('dashboard') || q.includes('趨勢')) {
      navigateTo('dashboard')
      highlight('[data-tour="nav-dashboard"]')
      return { text: '帶你去節能決策儀表板，這裡可以比較各船的 Speed Loss 與油耗喔。' }
    }

    if (q.includes('歷史') || q.includes('history') || q.includes('午報') || q.includes('紀錄')) {
      navigateTo('history')
      highlight('[data-tour="nav-history"]')
      return { text: '這是歷史午報與水下清潔／拋光紀錄，AI 會自動標註異常成因。' }
    }

    if (q.includes('總覽') || q.includes('地圖') || q.includes('船隊') || q.includes('overview')) {
      navigateTo('overview')
      highlight('[data-tour="radar-panel"]')
      return { text: '這是船隊即時相對位置總覽，點船的圖示可以看詳細效能分析。' }
    }

    if (q.includes('平均') || q.includes('速度損失') || q.includes('speed loss')) {
      navigateTo('overview')
      highlight('[data-tour="stat-avg-speedloss"]')
      return { text: '這張卡片顯示目前船隊的平均 Speed Loss，數值越高代表推進效率下降越多。' }
    }

    return {
      text:
        '我可以幫你導覽這個系統，例如可以問我：「哪艘船需要安排水下清潔？」「帶我去儀表板」「歷史紀錄在哪裡？」'
    }
  }

  return { ask }
}
