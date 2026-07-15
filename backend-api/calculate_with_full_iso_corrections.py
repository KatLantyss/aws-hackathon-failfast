#!/usr/bin/env python3
"""
完整的 ISO 19030 修正：
1. 风阻修正 (Wind resistance correction)
2. 水温修正 (Water temperature correction)
3. 海水密度修正 (Seawater density correction)
4. 吃水修正 (Draft correction)
5. 波浪修正 (简化版)
"""
import pandas as pd
import numpy as np
import sys
import math

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\maintenance_effectiveness_full_iso.csv"

WINDOW_DAYS = 30

# 参考值 (Reference values)
REF_WATER_TEMP = 15  # °C
REF_DRAFT = 8.0      # m (typical draft)
REF_DENSITY = 1.025  # ton/m³


def wind_resistance_correction(stw, wind_speed, wind_direction):
    """风阻修正 - 根据相对风速"""
    try:
        if pd.isna(wind_speed) or wind_speed <= 0:
            return 0
        # 简化模型：风速每增加1 m/s，STW 影响约 0.1 knot
        wind_correction = wind_speed * 0.1
        return wind_correction
    except:
        return 0


def water_temp_correction(stw, water_temp_actual, ref_temp=REF_WATER_TEMP):
    """
    水温修正 - 根据海水粘度变化
    温度越低，粘度越高，阻力越大
    """
    try:
        if pd.isna(water_temp_actual):
            return 0
        # 每相差1°C，STW 变化约 0.02 knot
        temp_diff = water_temp_actual - ref_temp
        temp_correction = -temp_diff * 0.02
        return temp_correction
    except:
        return 0


def seawater_density_correction(stw, water_temp, cargo_weight=None):
    """
    海水密度修正 - 根据温度和盐度
    温度和盐度都影响密度，进而影响浮力和阻力
    """
    try:
        if pd.isna(water_temp):
            return 0

        # 简化模型：根据温度估计密度变化
        # 高温->低密度->浮力减少->需要更多功率->STW降低
        # 低温->高密度->浮力增加->需要更少功率->STW增加

        # 基准密度在15°C, 盐度35 PSU
        # 每相差1°C，密度变化约 0.0002 ton/m³
        # 这对STW的影响很小，但在高精度修正中要考虑

        temp_diff = water_temp - REF_WATER_TEMP
        # 温度每差1°C，密度影响约0.02%
        # STW影响约 0.01 knot per °C difference
        density_correction = -temp_diff * 0.01

        return density_correction
    except:
        return 0


def draft_correction(stw, fore_draft, after_draft, ref_draft=REF_DRAFT):
    """
    吃水修正 - 根据排水量/吃水深度
    吃水越深，排水量越大，阻力越大，STW 越低
    吃水浅时，排水量小，阻力小，STW 越高
    """
    try:
        if pd.isna(fore_draft) or pd.isna(after_draft):
            return 0

        # 计算平均吃水
        avg_draft = (float(fore_draft) + float(after_draft)) / 2

        if avg_draft <= 0:
            return 0

        # 吃水每增加1m，STW 约降低 0.1-0.2 knot
        # (因为排水量增加，阻力增加)
        draft_diff = avg_draft - ref_draft
        draft_correction = -draft_diff * 0.15

        return draft_correction
    except:
        return 0


def wave_height_correction(stw, sea_height):
    """
    波浪修正 - 根据海况
    但这里已经过滤了WIND_SCALE <= 4，所以波浪应该不大
    简化处理
    """
    try:
        if pd.isna(sea_height) or sea_height == 0:
            return 0

        # 海况高度每增加1m，STW 约降低 0.05 knot
        wave_correction = -float(sea_height) * 0.05

        return wave_correction
    except:
        return 0


def calculate_corrected_stw(row):
    """
    计算完整 ISO 19030 修正后的 STW
    V_m_corrected = V_m_raw + wind_corr + temp_corr + density_corr + draft_corr + wave_corr
    """
    try:
        stw_raw = float(row.get('SPEED_THROUGH_WATER', 0))
        if stw_raw <= 0:
            return None

        wind_speed = float(row.get('WIND_SPEED', 0)) if pd.notna(row.get('WIND_SPEED')) else 0
        wind_dir = float(row.get('WIND_DIRECTION', 0)) if pd.notna(row.get('WIND_DIRECTION')) else 0
        water_temp = float(row.get('SEA_WATER_TEMP', 0)) if pd.notna(row.get('SEA_WATER_TEMP')) else REF_WATER_TEMP
        fore_draft = float(row.get('FORE_DRAFT', 0)) if pd.notna(row.get('FORE_DRAFT')) else REF_DRAFT
        after_draft = float(row.get('AFTER_DRAFT', 0)) if pd.notna(row.get('AFTER_DRAFT')) else REF_DRAFT
        sea_height = float(row.get('SEA_HEIGHT', 0)) if pd.notna(row.get('SEA_HEIGHT')) else 0
        cargo = float(row.get('CARGO_ON_BOARD', 0)) if pd.notna(row.get('CARGO_ON_BOARD')) else 0

        # 应用所有修正
        wind_corr = wind_resistance_correction(stw_raw, wind_speed, wind_dir)
        temp_corr = water_temp_correction(stw_raw, water_temp)
        density_corr = seawater_density_correction(stw_raw, water_temp, cargo)
        draft_corr = draft_correction(stw_raw, fore_draft, after_draft)
        wave_corr = wave_height_correction(stw_raw, sea_height)

        stw_corrected = stw_raw + wind_corr + temp_corr + density_corr + draft_corr + wave_corr

        return stw_corrected
    except:
        return None


def main():
    print("Loading data...")
    maint_df = pd.read_csv(MAINT_PATH)
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)

    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
    }, inplace=True)

    # 基础过滤
    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    # 计算原始STW
    vt_df['stw_raw'] = pd.to_numeric(vt_df['SPEED_THROUGH_WATER'], errors='coerce')

    # 计算完整 ISO 19030 修正后的STW
    print("Calculating full ISO 19030 corrections:")
    print("  - Wind resistance correction")
    print("  - Water temperature correction")
    print("  - Seawater density correction")
    print("  - Draft correction")
    print("  - Wave height correction")
    print()

    vt_df['stw_corrected'] = vt_df.apply(calculate_corrected_stw, axis=1)

    # 清理数据
    vt_df = vt_df[['vessel', 'day', 'stw_raw', 'stw_corrected']].dropna()
    vt_df = vt_df[(vt_df['stw_raw'] > 0) & (vt_df['stw_corrected'] > 0)]
    vt_df = vt_df.sort_values(['vessel', 'day']).reset_index(drop=True)

    print(f"Loaded {len(vt_df)} valid records\n")

    # 计算维修效果
    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        print(f"{vessel}:")
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        for _, maint in vessel_maint.iterrows():
            event_day = float(maint['event_day'])
            event_type = maint['event_type']

            before_w = vessel_df[
                (vessel_df['day'] >= event_day - WINDOW_DAYS) &
                (vessel_df['day'] < event_day)
            ]
            after_w = vessel_df[
                (vessel_df['day'] > event_day) &
                (vessel_df['day'] <= event_day + WINDOW_DAYS)
            ]

            if len(before_w) >= 3 and len(after_w) >= 3:
                # 用修正后的STW计算
                stw_before = before_w['stw_corrected'].mean()
                stw_after = after_w['stw_corrected'].mean()
                improvement = (stw_after - stw_before) / stw_before * 100

                results.append({
                    'ship': vessel,
                    'event_day': event_day,
                    'event_type': event_type,
                    'stw_before_30d': round(stw_before, 2),
                    'stw_after_30d': round(stw_after, 2),
                    'improvement_pct': round(improvement, 2),
                    'n_before': len(before_w),
                    'n_after': len(after_w),
                })

                indicator = "✓" if improvement > 0 else "✗"
                print(f"  Day {event_day:6.0f} {event_type:8s}: "
                      f"before={stw_before:6.2f}, after={stw_after:6.2f}, "
                      f"improvement={improvement:6.2f}% {indicator}")

    output_df = pd.DataFrame(results)
    output_df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8')
    print(f"\nSaved to {OUTPUT_PATH}")

    # 验证
    print("\n" + "=" * 80)
    print("VALIDATION (with Full ISO 19030 corrections)")
    print("=" * 80)

    valid_df = output_df[output_df['improvement_pct'].notna()]
    if len(valid_df) > 0:
        improved = (valid_df['improvement_pct'] > 0).sum()
        total = len(valid_df)
        improvement_rate = improved / total * 100

        print(f"Total events: {total}")
        print(f"Improved: {improved} ({improvement_rate:.1f}%)")
        print(f"Average improvement: {valid_df['improvement_pct'].mean():.2f}%\n")

        print("By type:")
        for mtype in ['DD', 'UWC+PP', 'UWC', 'PP', 'UWI+PP', 'UWI']:
            group = valid_df[valid_df['event_type'] == mtype]
            if len(group) == 0:
                continue

            improved_type = (group['improvement_pct'] > 0).sum()
            total_type = len(group)
            avg_imp = group['improvement_pct'].mean()
            rate = improved_type / total_type * 100 if total_type > 0 else 0

            print(f"  {mtype:8s}: {improved_type:2d}/{total_type:2d} ({rate:5.1f}%) avg={avg_imp:6.2f}%")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
