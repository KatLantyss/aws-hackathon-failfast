"""
ISO 19030-2 Speed Loss 計算模組
各艘船各自的 Baseline，計算每日 Speed Loss

V_d = (V_e - V_m) / V_e × 100%
其中：
  V_e = 各艘船的 Baseline STW（DD後90天平均）
  V_m = 當日修正後的 STW
"""

import pandas as pd
from collections import defaultdict

# ISO 19030 修正係數
REF_WATER_TEMP = 15
REF_DRAFT = 8.0


def wind_resistance_correction(stw, wind_speed):
    """風阻修正"""
    try:
        if pd.isna(wind_speed) or wind_speed <= 0:
            return 0
        return wind_speed * 0.1
    except:
        return 0


def water_temp_correction(water_temp_actual):
    """水溫修正"""
    try:
        if pd.isna(water_temp_actual):
            return 0
        temp_diff = water_temp_actual - REF_WATER_TEMP
        return -temp_diff * 0.02
    except:
        return 0


def seawater_density_correction(water_temp):
    """海水密度修正"""
    try:
        if pd.isna(water_temp):
            return 0
        temp_diff = water_temp - REF_WATER_TEMP
        return -temp_diff * 0.01
    except:
        return 0


def draft_correction(fore_draft, after_draft):
    """吃水修正"""
    try:
        if pd.isna(fore_draft) or pd.isna(after_draft):
            return 0
        avg_draft = (float(fore_draft) + float(after_draft)) / 2
        if avg_draft <= 0:
            return 0
        draft_diff = avg_draft - REF_DRAFT
        return -draft_diff * 0.15
    except:
        return 0


def wave_height_correction(sea_height):
    """波浪修正"""
    try:
        if pd.isna(sea_height) or sea_height == 0:
            return 0
        return -float(sea_height) * 0.05
    except:
        return 0


def calculate_corrected_stw(row):
    """計算修正後的 STW"""
    try:
        stw_raw = float(row.get('SPEED_THROUGH_WATER', 0))
        if stw_raw <= 0:
            return None

        wind_speed = float(row.get('WIND_SPEED', 0)) if pd.notna(row.get('WIND_SPEED')) else 0
        water_temp = float(row.get('SEA_WATER_TEMP', 0)) if pd.notna(row.get('SEA_WATER_TEMP')) else REF_WATER_TEMP
        fore_draft = float(row.get('FORE_DRAFT', 0)) if pd.notna(row.get('FORE_DRAFT')) else REF_DRAFT
        after_draft = float(row.get('AFTER_DRAFT', 0)) if pd.notna(row.get('AFTER_DRAFT')) else REF_DRAFT
        sea_height = float(row.get('SEA_HEIGHT', 0)) if pd.notna(row.get('SEA_HEIGHT')) else 0

        wind_corr = wind_resistance_correction(stw_raw, wind_speed)
        temp_corr = water_temp_correction(water_temp)
        density_corr = seawater_density_correction(water_temp)
        draft_corr = draft_correction(fore_draft, after_draft)
        wave_corr = wave_height_correction(sea_height)

        stw_corrected = stw_raw + wind_corr + temp_corr + density_corr + draft_corr + wave_corr
        return stw_corrected
    except:
        return None


def establish_baselines(df, maint_df, vessel_id):
    """
    為指定船舶建立 Baseline
    使用 DD 後 90 天的平均修正 STW
    """
    vessel_df = df[df['De-identification Name'] == vessel_id].copy()
    vessel_maint = maint_df[maint_df['ship_id'] == vessel_id]

    if len(vessel_df) == 0:
        return None

    # 找 DD 事件
    dd_events = sorted([
        float(m['event_day'])
        for _, m in vessel_maint.iterrows()
        if m['event_type'] == 'DD'
    ])

    if len(dd_events) > 0:
        dd_day = dd_events[0]
        baseline_window = vessel_df[
            (vessel_df['NOON_UTC'] >= dd_day) &
            (vessel_df['NOON_UTC'] <= dd_day + 90)
        ].copy()

        if len(baseline_window) >= 3:
            baseline_window['stw_corrected'] = baseline_window.apply(calculate_corrected_stw, axis=1)
            baseline_stw = baseline_window['stw_corrected'].dropna().mean()
            return baseline_stw

    # 無 DD，用全船平均
    vessel_df['stw_corrected'] = vessel_df.apply(calculate_corrected_stw, axis=1)
    baseline_stw = vessel_df['stw_corrected'].dropna().mean()
    return baseline_stw


def calculate_daily_speed_loss(df, maint_df, vessel_id, baseline_stw):
    """
    計算每日 Speed Loss
    V_d = (V_e - V_m) / V_e × 100%
    """
    vessel_df = df[df['De-identification Name'] == vessel_id].copy()

    if baseline_stw is None or baseline_stw <= 0:
        return []

    results = []

    for _, row in vessel_df.iterrows():
        # 基礎過濾
        wind_scale = float(row.get('WIND_SCALE', 99)) if pd.notna(row.get('WIND_SCALE')) else 99
        hours_full_speed = float(row.get('HOURS_FULL_SPEED', 0)) if pd.notna(row.get('HOURS_FULL_SPEED')) else 0

        if wind_scale > 4 or hours_full_speed < 22:
            continue

        stw_corrected = calculate_corrected_stw(row)
        if stw_corrected is None or stw_corrected <= 0:
            continue

        # 計算 Speed Loss
        speed_loss = (baseline_stw - stw_corrected) / baseline_stw * 100

        results.append({
            'day': float(row.get('NOON_UTC', 0)),
            'voyage': row.get('VOYAGE'),
            'stw_raw': round(float(row.get('SPEED_THROUGH_WATER', 0)), 2) if pd.notna(row.get('SPEED_THROUGH_WATER')) else None,
            'stw_corrected': round(stw_corrected, 2),
            'baseline_stw': round(baseline_stw, 2),
            'speed_loss_pct': round(speed_loss, 2),
            'wind_scale': wind_scale,
            'hours_full_speed': hours_full_speed,
        })

    return sorted(results, key=lambda x: x['day'])
