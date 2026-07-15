"""
基於斜率的維修效果分析 v2.0

相比簡單的中位數差值方法：
• 更準確捕捉「防止衰退」的效果
• 對異常值不敏感
• 能區分「臨時現象」vs「真實改善」
"""

import numpy as np
from scipy import stats
import statistics


def calculate_slope_improvement(before_days, before_sl_values, after_days, after_sl_values):
    """
    計算維修前後的斜率改善

    Args:
        before_days: 維修前的相對天數
        before_sl_values: 維修前的 Speed Loss 值
        after_days: 維修後的相對天數
        after_sl_values: 維修後的 Speed Loss 值

    Returns:
        {
            'slope_before': float,      # 維修前每天 SL 變化（%/day）
            'slope_after': float,       # 維修後每天 SL 變化（%/day）
            'slope_improvement': float, # 斜率改善程度
            'before_trend': str,        # '衰退' 或 '改善'
            'after_trend': str,         # '衰退' 或 '改善'
            'r_squared_before': float,  # 前期擬合度
            'r_squared_after': float    # 後期擬合度
        }
    """

    if len(before_days) < 3 or len(after_days) < 3:
        return None

    try:
        # 前期線性回歸
        slope_before, intercept_before, r_value_before, p_value_before, std_err_before = stats.linregress(
            before_days, before_sl_values
        )
        r_squared_before = r_value_before ** 2

        # 後期線性回歸
        slope_after, intercept_after, r_value_after, p_value_after, std_err_after = stats.linregress(
            after_days, after_sl_values
        )
        r_squared_after = r_value_after ** 2

        # 斜率改善 = 前期斜率 - 後期斜率
        # 正值 = 改善（衰退減速或逆轉）
        slope_improvement = slope_before - slope_after

        return {
            'slope_before': round(slope_before, 6),
            'slope_after': round(slope_after, 6),
            'slope_improvement': round(slope_improvement, 6),
            'before_trend': '衰退' if slope_before > 0.0001 else ('改善' if slope_before < -0.0001 else '穩定'),
            'after_trend': '衰退' if slope_after > 0.0001 else ('改善' if slope_after < -0.0001 else '穩定'),
            'r_squared_before': round(r_squared_before, 3),
            'r_squared_after': round(r_squared_after, 3)
        }
    except Exception as e:
        return None


def classify_maintenance_by_slope(slope_improvement: float, maintenance_type: str) -> dict:
    """
    基於斜率改善程度分類維修效果

    Args:
        slope_improvement: 斜率改善值（%/day）
        maintenance_type: 維修類型

    Returns:
        {
            'category': 'excellent' | 'good' | 'ok' | 'poor' | 'failed',
            'severity': 'NORMAL' | 'WARNING' | 'CRITICAL',
            'description': str,
            'is_anomalous': bool
        }
    """

    # 根據維修類型調整閾值
    if maintenance_type == 'DD':
        thresholds = {
            'excellent': 0.15,  # > 0.15 %/day
            'good': 0.08,       # 0.08-0.15
            'ok': 0.02,         # 0.02-0.08
            'poor': -0.02,      # -0.02-0.02
            'failed': -0.02     # < -0.02
        }
    elif maintenance_type in ['UWC+PP', 'UWI+PP']:
        thresholds = {
            'excellent': 0.12,
            'good': 0.06,
            'ok': 0.01,
            'poor': -0.02,
            'failed': -0.02
        }
    elif maintenance_type in ['PP', 'UWC']:
        thresholds = {
            'excellent': 0.08,
            'good': 0.04,
            'ok': 0.00,
            'poor': -0.02,
            'failed': -0.02
        }
    else:
        thresholds = {
            'excellent': 0.10,
            'good': 0.05,
            'ok': 0.00,
            'poor': -0.02,
            'failed': -0.02
        }

    if slope_improvement > thresholds['excellent']:
        return {
            'category': 'excellent',
            'severity': 'NORMAL',
            'description': f'🟢 優秀改善 (斜率改善 {slope_improvement:+.4f} %/day)',
            'is_anomalous': False
        }
    elif slope_improvement > thresholds['good']:
        return {
            'category': 'good',
            'severity': 'NORMAL',
            'description': f'🟢 良好改善 (斜率改善 {slope_improvement:+.4f} %/day)',
            'is_anomalous': False
        }
    elif slope_improvement > thresholds['ok']:
        return {
            'category': 'ok',
            'severity': 'NORMAL',
            'description': f'🟡 輕度改善 (斜率改善 {slope_improvement:+.4f} %/day)',
            'is_anomalous': False
        }
    elif slope_improvement > thresholds['poor']:
        return {
            'category': 'poor',
            'severity': 'WARNING',
            'description': f'🟠 改善有限 (斜率改善 {slope_improvement:+.4f} %/day)',
            'is_anomalous': True
        }
    else:
        return {
            'category': 'failed',
            'severity': 'CRITICAL',
            'description': f'🔴 維修失敗 (斜率改善 {slope_improvement:+.4f} %/day，衰退加速)',
            'is_anomalous': True
        }


def analyze_maintenance_with_slope(
    ship_id: str,
    event_day: float,
    maintenance_type: str,
    records: list  # [{'day': float, 'sl': float}, ...]
) -> dict:
    """
    完整的基於斜率的維修分析

    Args:
        ship_id: 船舶 ID
        event_day: 維修事件發生的天數
        maintenance_type: 維修類型
        records: 所有 Speed Loss 記錄

    Returns:
        {
            'slope_analysis': {...},
            'classification': {...},
            'median_delta': float,  # 用於對比
            'consistency': str,     # 兩種方法的一致性
        }
    """

    WINDOW = 45

    # 蒐集前後數據
    before_records = [r for r in records if r['sl'] is not None and (event_day - WINDOW) <= r['day'] < event_day]
    after_records = [r for r in records if r['sl'] is not None and event_day < r['day'] <= (event_day + WINDOW)]

    if len(before_records) < 3 or len(after_records) < 3:
        return None

    # 相對天數（以維修日為基準）
    before_days = np.array([r['day'] - event_day for r in before_records])
    before_sl = np.array([r['sl'] for r in before_records])
    after_days = np.array([r['day'] - event_day for r in after_records])
    after_sl = np.array([r['sl'] for r in after_records])

    # 斜率分析
    slope_result = calculate_slope_improvement(before_days, before_sl, after_days, after_sl)
    if not slope_result:
        return None

    # 分類
    classification = classify_maintenance_by_slope(slope_result['slope_improvement'], maintenance_type)

    # 中位數差值（用於對比）
    before_median = np.median(before_sl)
    after_median = np.median(after_sl)
    median_delta = after_median - before_median

    # 檢查兩種方法的一致性
    consistency = 'consistent'
    if (median_delta < 0 and slope_result['slope_improvement'] < 0) or \
       (median_delta > 0 and slope_result['slope_improvement'] > 0):
        consistency = 'consistent'
    else:
        consistency = 'inconsistent'

    return {
        'slope_analysis': slope_result,
        'classification': classification,
        'median_delta': round(median_delta, 2),
        'before_median': round(before_median, 2),
        'after_median': round(after_median, 2),
        'consistency': consistency,
        'n_before': len(before_records),
        'n_after': len(after_records)
    }


# 輔助函數：用於決策支持
def get_maintenance_recommendation_by_slope(current_speed_loss: float, maintenance_history: list) -> dict:
    """
    基於斜率分析的維修建議

    Args:
        current_speed_loss: 當前 Speed Loss %
        maintenance_history: [{type, slope_improvement, date}, ...]

    Returns:
        {
            'recommendation': str,
            'urgency': 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW',
            'expected_improvement': float,  # 基於歷史斜率分析
            'reasoning': str
        }
    """

    # 統計各維修類型的平均斜率改善
    type_improvements = {}
    for m in maintenance_history:
        mtype = m.get('type')
        slope_imp = m.get('slope_improvement', 0)
        if mtype not in type_improvements:
            type_improvements[mtype] = []
        type_improvements[mtype].append(slope_imp)

    # 計算平均值
    avg_improvements = {k: np.mean(v) for k, v in type_improvements.items()}

    # 選擇維修方案
    if current_speed_loss >= 30:
        recommended_type = 'DD'
        urgency = 'CRITICAL'
        reasoning = '船體污損嚴重，需全面處理'
    elif current_speed_loss >= 20:
        # 選擇過往斜率改善最好的複合維修
        best_type = max(avg_improvements, key=avg_improvements.get) if avg_improvements else 'UWC+PP'
        recommended_type = best_type if best_type in ['UWC+PP', 'UWI+PP'] else 'UWC+PP'
        urgency = 'HIGH'
        reasoning = f'中度污損，基於歷史數據選擇 {recommended_type}'
    elif current_speed_loss >= 10:
        recommended_type = 'UWC+PP'
        urgency = 'MEDIUM'
        reasoning = '輕度污損'
    else:
        recommended_type = None
        urgency = 'LOW'
        reasoning = '監控中'

    expected_improvement = avg_improvements.get(recommended_type, 0.05) if recommended_type else 0

    return {
        'recommendation': f'建議進行 {recommended_type} 維修' if recommended_type else '監控中',
        'urgency': urgency,
        'expected_slope_improvement': round(expected_improvement, 6),
        'reasoning': reasoning
    }
