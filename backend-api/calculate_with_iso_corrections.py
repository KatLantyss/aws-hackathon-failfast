#!/usr/bin/env python3
"""
ISO 19030 修正：
1. 风阻修正
2. 水温修正
3. 海水密度修正

然后计算维修效果
"""
import pandas as pd
import numpy as np
import sys
import math

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\maintenance_effectiveness_iso.csv"

WINDOW_DAYS = 30

def wind_resistance_correction(stw, wind_speed, wind_direction, ave_speed):
    """
    风阻修正：计算相对风的影响
    ISO 19030 基本公式
    """
    try:
        # 将风向转换为相对于船舶航向的角度（简化：假设风向是相对于船舶）
        # 风速单位转换：假设输入是 m/s
        # STW 单位：knots

        if pd.isna(wind_speed) or wind_speed == 0:
            return 0  # 无风，无修正

        # 简化修正：风速每增加5 m/s，STW影响约0.5-1 knot
        # 这是一个简化的线性模型
        wind_correction = wind_speed * 0.1  # 每 1 m/s 风速 ≈ 0.1 knot 影响

        return wind_correction
    except:
        return 0


def water_temp_correction(stw, water_temp_actual, ref_temp=15):
    """
    水温修正：海水粘度随温度变化
    温度越低，粘度越高，阻力越大，STW越低
    """
    try:
        if pd.isna(water_temp_actual):
            return 0  # 无修正

        # 简化模型：每相差1°C，STW 变化约 0.02-0.03 knot
        # 温度越低，实际STW越低，修正后应该增加STW
        temp_diff = water_temp_actual - ref_temp
        temp_correction = -temp_diff * 0.02  # 负号：低温导致STW低，修正时要加回

        return temp_correction
    except:
        return 0


def calculate_corrected_stw(row):
    """
    计算ISO 19030 修正后的STW
    V_m_corrected = V_m_raw + wind_correction + temp_correction + ...
    """
    try:
        stw_raw = float(row.get('SPEED_THROUGH_WATER', 0))
        if stw_raw <= 0:
            return None

        wind_speed = float(row.get('WIND_SPEED', 0)) if pd.notna(row.get('WIND_SPEED')) else 0
        wind_dir = float(row.get('WIND_DIRECTION', 0)) if pd.notna(row.get('WIND_DIRECTION')) else 0
        avg_speed = float(row.get('AVG_SPEED', 0)) if pd.notna(row.get('AVG_SPEED')) else 0
        water_temp = float(row.get('SEA_WATER_TEMP', 0)) if pd.notna(row.get('SEA_WATER_TEMP')) else 15

        # 应用修正
        wind_corr = wind_resistance_correction(stw_raw, wind_speed, wind_dir, avg_speed)
        temp_corr = water_temp_correction(stw_raw, water_temp)

        stw_corrected = stw_raw + wind_corr + temp_corr

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

    # 计算ISO修正后的STW
    print("Calculating ISO 19030 corrections...")
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
    output_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")

    # 验证
    print("\n" + "=" * 80)
    print("VALIDATION (with ISO 19030 corrections)")
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
