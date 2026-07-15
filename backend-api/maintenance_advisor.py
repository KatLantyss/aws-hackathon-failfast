"""
維修建議與決策支持系統 v1.0

基於 74 個維護事件的統計分析，為每個維修類型制定異常判定和建議標準
"""

import numpy as np

# ═══════════════════════════════════════════════════════════════════════════
# 1. 維修類型特定的異常判定標準
# ═══════════════════════════════════════════════════════════════════════════

MAINTENANCE_TYPES = {
    'DD': {
        'name': '進塢',
        'description': '全面塗裝 + 機械保養',
        'has_physical_intervention': True,
        'typical_cost_usd': 350000,  # 估計成本
        'expected_improvement_pct': 13.27,  # 平均改善
        'success_rate': 0.857,  # 85.7%
        'anomaly_thresholds': {
            'excellent': (-20, -15),      # 改善超常
            'good': (-15, -10),           # 良好改善
            'normal': (-10, -3),          # 正常改善
            'warning': (-3, 0),           # 改善不足
            'critical': (0, 100)          # 未改善或惡化
        }
    },
    'UWC': {
        'name': '船殼清洗',
        'description': '水下船殼清洗',
        'has_physical_intervention': True,
        'typical_cost_usd': 45000,
        'expected_improvement_pct': -2.23,  # 平均反而惡化！
        'success_rate': 0.167,  # 只有 16.7%
        'anomaly_thresholds': {
            'excellent': (-15, -10),
            'good': (-10, -5),
            'normal': (-5, -1),
            'warning': (-1, 2),           # 容許微弱惡化
            'critical': (2, 100)
        }
    },
    'PP': {
        'name': '螺旋槳拋光',
        'description': '螺旋槳表面拋光',
        'has_physical_intervention': True,
        'typical_cost_usd': 38000,
        'expected_improvement_pct': 3.04,
        'success_rate': 0.636,  # 63.6%
        'anomaly_thresholds': {
            'excellent': (-18, -12),
            'good': (-12, -6),
            'normal': (-6, -1.5),
            'warning': (-1.5, 2),
            'critical': (2, 100)
        }
    },
    'UWC+PP': {
        'name': '清洗 + 拋光',
        'description': '複合維修：清洗 + 拋光',
        'has_physical_intervention': True,
        'typical_cost_usd': 78000,
        'expected_improvement_pct': 2.71,  # 複合效果不穩定
        'success_rate': 0.571,  # 57.1%
        'anomaly_thresholds': {
            'excellent': (-20, -12),
            'good': (-12, -6),
            'normal': (-6, -2.5),
            'warning': (-2.5, 1),
            'critical': (1, 100)
        }
    },
    'UWI': {
        'name': '純水下檢查',
        'description': '水下檢查（無物理介入）',
        'has_physical_intervention': False,
        'typical_cost_usd': 8000,
        'expected_improvement_pct': 0,  # 不應改善
        'success_rate': 0.0,  # 不應有改善
        'anomaly_thresholds': {
            'excellent': (0, 0),
            'good': (0, 0),
            'normal': (-1, 1),           # 微弱變化可接受
            'warning': (-2, 0),          # 有改善是異常
            'critical': (-100, -2)       # 明顯改善是異常
        }
    },
    'UWI+PP': {
        'name': '檢查 + 拋光',
        'description': '複合維修：檢查後拋光',
        'has_physical_intervention': True,
        'typical_cost_usd': 42000,
        'expected_improvement_pct': 4.45,
        'success_rate': 0.516,  # 51.6%
        'anomaly_thresholds': {
            'excellent': (-20, -12),
            'good': (-12, -6),
            'normal': (-6, -2.5),
            'warning': (-2.5, 1),
            'critical': (1, 100)
        }
    }
}


def detect_maintenance_anomaly(maintenance_type: str, delta: float, is_uwi_only: bool = False):
    """
    按維修類型檢測異常

    Args:
        maintenance_type: 維修類型 (DD, UWC, PP, UWC+PP, UWI, UWI+PP)
        delta: Speed Loss 變化 (after - before)，負值表示改善
        is_uwi_only: 是否為純 UWI（無其他維修）

    Returns:
        {
            'is_anomalous': bool,
            'severity': 'CRITICAL' | 'WARNING' | 'NORMAL',
            'category': 'excellent' | 'good' | 'normal' | 'warning' | 'critical',
            'reason': str
        }
    """
    if delta is None:
        return {
            'is_anomalous': False,
            'severity': 'NORMAL',
            'category': 'unknown',
            'reason': '數據不足'
        }

    mtype = MAINTENANCE_TYPES.get(maintenance_type)
    if not mtype:
        return {
            'is_anomalous': False,
            'severity': 'NORMAL',
            'category': 'unknown',
            'reason': f'未知維修類型: {maintenance_type}'
        }

    # 純 UWI 特殊邏輯
    if is_uwi_only and maintenance_type == 'UWI':
        if delta < -1.0:
            return {
                'is_anomalous': True,
                'severity': 'CRITICAL',
                'category': 'critical',
                'reason': f'純檢查不應改善 (Δ={delta:.2f}%)'
            }
        elif -1.0 <= delta <= 1.0:
            return {
                'is_anomalous': False,
                'severity': 'NORMAL',
                'category': 'normal',
                'reason': f'正常（無顯著變化）'
            }
        else:
            return {
                'is_anomalous': False,
                'severity': 'NORMAL',
                'category': 'normal',
                'reason': f'正常（微弱惡化在可接受範圍）'
            }

    # 查找分類
    thresholds = mtype['anomaly_thresholds']
    category = None
    for cat_name, (lower, upper) in thresholds.items():
        if lower <= delta < upper:
            category = cat_name
            break

    if category is None:
        if delta > thresholds['critical'][1]:
            category = 'critical'
        elif delta < thresholds['excellent'][0]:
            category = 'excellent'

    # 判斷異常
    is_anomalous = category in ['warning', 'critical']
    severity = 'CRITICAL' if category == 'critical' else ('WARNING' if category == 'warning' else 'NORMAL')

    category_desc = {
        'excellent': '卓越改善',
        'good': '良好改善',
        'normal': '正常改善',
        'warning': '異常警告',
        'critical': '嚴重異常'
    }

    return {
        'is_anomalous': is_anomalous,
        'severity': severity,
        'category': category,
        'reason': f'{category_desc.get(category, "未知")}: {mtype["name"]} (Δ={delta:.2f}%)'
    }


def recommend_maintenance_by_slope(current_speed_loss: float, maintenance_history_slope: list) -> dict:
    """
    基於斜率分析的維修建議（新方法）

    Args:
        current_speed_loss: 當前 Speed Loss %
        maintenance_history_slope: [{type, slope_improvement, success_count, total_count}, ...]

    Returns:
        維修建議
    """

    # 統計各維修類型的斜率改善和成功率
    type_stats = {}
    for m in maintenance_history_slope:
        mtype = m.get('type')
        slope_imp = m.get('slope_improvement', 0)
        if mtype not in type_stats:
            type_stats[mtype] = {
                'improvements': [],
                'success_count': 0,
                'total_count': 0
            }
        type_stats[mtype]['improvements'].append(slope_imp)

    # 計算平均斜率改善
    avg_improvements = {}
    for mtype, stats in type_stats.items():
        if stats['improvements']:
            avg_improvements[mtype] = np.mean(stats['improvements'])

    # 基於 Speed Loss 選擇維修
    if current_speed_loss >= 30:
        recommended_type = 'DD'
        urgency = 'CRITICAL'
        reasoning = '船體污損嚴重 (SL ≥ 30%)，進塢是最有效的選擇'
    elif current_speed_loss >= 20:
        # 選擇平均斜率改善最好的複合維修
        if 'UWC+PP' in avg_improvements and 'UWI+PP' in avg_improvements:
            best_complex = 'UWC+PP' if avg_improvements['UWC+PP'] > avg_improvements['UWI+PP'] else 'UWI+PP'
            recommended_type = best_complex
        else:
            recommended_type = 'UWC+PP'
        urgency = 'HIGH'
        reasoning = f'中度污損 (SL ≥ 20%)，基於歷史斜率選擇複合維修'
    elif current_speed_loss >= 10:
        recommended_type = 'UWC+PP'
        urgency = 'MEDIUM'
        reasoning = '輕度污損 (SL ≥ 10%)，複合維修應有效'
    else:
        recommended_type = None
        urgency = 'LOW'
        reasoning = '監控中'

    expected_slope_imp = avg_improvements.get(recommended_type, 0.05) if recommended_type else 0

    return {
        'recommendation': f'建議進行 {MAINTENANCE_TYPES[recommended_type]["name"]}' if recommended_type else '監控中',
        'maintenance_type': recommended_type,
        'urgency': urgency,
        'expected_slope_improvement': round(expected_slope_imp, 6),
        'estimated_cost': MAINTENANCE_TYPES[recommended_type]['typical_cost_usd'] if recommended_type else 0,
        'reasoning': reasoning
    }


def recommend_maintenance(current_speed_loss: float, maintenance_history: list, current_degradation_rate: float = None):
    """
    根據當前 Speed Loss 建議最合適的維修

    Args:
        current_speed_loss: 當前 Speed Loss %
        maintenance_history: 過去維修的 [{type, delta, date}, ...]
        current_degradation_rate: 衰退速率 %/day（可選）

    Returns:
        {
            'recommendation': str,
            'maintenance_type': str,
            'urgency': 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL',
            'expected_improvement': float,
            'estimated_cost': float,
            'success_probability': float,
            'reasoning': str
        }
    """

    # 風險評估
    if current_speed_loss >= 30:
        urgency = 'CRITICAL'
    elif current_speed_loss >= 20:
        urgency = 'HIGH'
    elif current_speed_loss >= 10:
        urgency = 'MEDIUM'
    else:
        urgency = 'LOW'

    # 分析過去維修效果
    maintenance_success = {}
    for mtype in MAINTENANCE_TYPES.keys():
        matching = [m for m in maintenance_history if m.get('type') == mtype and m.get('delta') is not None]
        if matching:
            successful = sum(1 for m in matching if m['delta'] < 0)
            maintenance_success[mtype] = successful / len(matching)
        else:
            maintenance_success[mtype] = MAINTENANCE_TYPES[mtype]['success_rate']

    # 選擇維修類型
    if current_speed_loss >= 20:
        # 嚴重污損：優先進塢
        recommended_type = 'DD'
        reasoning = '船體污損嚴重 (SL ≥ 20%)，需全面處理'
    elif current_speed_loss >= 12:
        # 中度污損：複合維修
        uwc_pp_success = maintenance_success.get('UWC+PP', 0.571)
        if uwc_pp_success > 0.5:
            recommended_type = 'UWC+PP'
            reasoning = f'中度污損，複合維修成功率 {uwc_pp_success:.1%}'
        else:
            recommended_type = 'DD'
            reasoning = '複合維修效果差，建議進塢'
    else:
        # 輕度污損：清洗或拋光
        recommended_type = 'UWC+PP'
        reasoning = '輕度污損，清洗 + 拋光應可恢復'

    mtype_info = MAINTENANCE_TYPES[recommended_type]

    return {
        'recommendation': f"建議進行 {mtype_info['name']} 維修",
        'maintenance_type': recommended_type,
        'urgency': urgency,
        'expected_improvement': mtype_info['expected_improvement_pct'],
        'estimated_cost': mtype_info['typical_cost_usd'],
        'success_probability': maintenance_success.get(recommended_type, mtype_info['success_rate']),
        'reasoning': reasoning,
        'alternative_type': 'DD' if recommended_type != 'DD' else 'UWC+PP'
    }


def calculate_maintenance_roi(
    expected_fuel_saving_mt_per_month: float,
    fuel_price_usd_per_mt: float,
    maintenance_cost_usd: float,
    success_probability: float = 1.0
) -> dict:
    """
    計算維修的投資回報

    Args:
        expected_fuel_saving_mt_per_month: 預期月度節油 (MT)
        fuel_price_usd_per_mt: 燃油價格 (USD/MT)
        maintenance_cost_usd: 維修成本 (USD)
        success_probability: 成功機率 (0-1)

    Returns:
        {
            'monthly_savings_usd': float,
            'annual_savings_usd': float,
            'payback_months': float,
            'roi_pct': float,
            'break_even_days': float
        }
    """

    monthly_savings = expected_fuel_saving_mt_per_month * fuel_price_usd_per_mt * success_probability
    annual_savings = monthly_savings * 12

    if monthly_savings > 0:
        payback_months = maintenance_cost_usd / monthly_savings
        break_even_days = maintenance_cost_usd / (monthly_savings / 30)
    else:
        payback_months = float('inf')
        break_even_days = float('inf')

    roi_pct = ((annual_savings - maintenance_cost_usd / 12) / maintenance_cost_usd * 100) if maintenance_cost_usd > 0 else 0

    return {
        'monthly_savings_usd': round(monthly_savings, 2),
        'annual_savings_usd': round(annual_savings, 2),
        'payback_months': round(payback_months, 1),
        'roi_pct': round(roi_pct, 1),
        'break_even_days': round(break_even_days, 1)
    }


# 用於後端的輔助函數
def get_fleet_maintenance_priority(vessels_data: list) -> list:
    """
    對船隊進行優先級排序

    Args:
        vessels_data: [{vessel_id, current_speed_loss, fuel_consumption}, ...]

    Returns:
        按優先級排序的船舶列表
    """

    priorities = []
    for vessel in vessels_data:
        sl = vessel.get('current_speed_loss', 0)
        fuel = vessel.get('daily_fuel_consumption', 1)

        # 優先級分數 = Speed Loss × 燃油消耗（考慮營運成本）
        priority_score = sl * fuel

        priorities.append({
            'vessel_id': vessel['vessel_id'],
            'speed_loss': sl,
            'daily_fuel_consumption': fuel,
            'priority_score': priority_score,
            'urgency': 'CRITICAL' if sl >= 30 else ('HIGH' if sl >= 20 else ('MEDIUM' if sl >= 10 else 'LOW'))
        })

    return sorted(priorities, key=lambda x: -x['priority_score'])
