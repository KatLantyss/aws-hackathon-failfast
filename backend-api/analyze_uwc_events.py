#!/usr/bin/env python3
"""
深入分析UWC事件為什麼效果不好
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"

REF_WATER_TEMP = 15
REF_DRAFT = 8.0


def wind_resistance_correction(stw, wind_speed, wind_direction):
    try:
        if pd.isna(wind_speed) or wind_speed <= 0:
            return 0
        return wind_speed * 0.1
    except:
        return 0


def water_temp_correction(stw, water_temp_actual, ref_temp=REF_WATER_TEMP):
    try:
        if pd.isna(water_temp_actual):
            return 0
        temp_diff = water_temp_actual - ref_temp
        return -temp_diff * 0.02
    except:
        return 0


def seawater_density_correction(stw, water_temp, cargo_weight=None):
    try:
        if pd.isna(water_temp):
            return 0
        temp_diff = water_temp - REF_WATER_TEMP
        return -temp_diff * 0.01
    except:
        return 0


def draft_correction(stw, fore_draft, after_draft, ref_draft=REF_DRAFT):
    try:
        if pd.isna(fore_draft) or pd.isna(after_draft):
            return 0
        avg_draft = (float(fore_draft) + float(after_draft)) / 2
        if avg_draft <= 0:
            return 0
        draft_diff = avg_draft - ref_draft
        return -draft_diff * 0.15
    except:
        return 0


def wave_height_correction(stw, sea_height):
    try:
        if pd.isna(sea_height) or sea_height == 0:
            return 0
        return -float(sea_height) * 0.05
    except:
        return 0


def calculate_corrected_stw(row):
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

        wind_corr = wind_resistance_correction(stw_raw, wind_speed, wind_dir)
        temp_corr = water_temp_correction(stw_raw, water_temp)
        density_corr = seawater_density_correction(stw_raw, water_temp)
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

    # 基礎過濾
    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    vt_df['stw_raw'] = pd.to_numeric(vt_df['SPEED_THROUGH_WATER'], errors='coerce')
    vt_df['stw_corrected'] = vt_df.apply(calculate_corrected_stw, axis=1)

    vt_df = vt_df[['vessel', 'day', 'stw_raw', 'stw_corrected']].dropna()
    vt_df = vt_df[(vt_df['stw_raw'] > 0) & (vt_df['stw_corrected'] > 0)]
    vt_df = vt_df.sort_values(['vessel', 'day']).reset_index(drop=True)

    print(f"Loaded {len(vt_df)} valid records\n")

    # 收集所有UWC事件
    uwc_events = []

    for vessel in sorted(vt_df['vessel'].unique()):
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        # 计算baseline
        baseline_stw = vessel_df['stw_corrected'].mean()

        # 找所有UWC事件
        for _, maint in vessel_maint.iterrows():
            if maint['event_type'] != 'UWC':
                continue

            event_day = float(maint['event_day'])

            before_w = vessel_df[
                (vessel_df['day'] >= event_day - 30) &
                (vessel_df['day'] < event_day)
            ]
            after_w = vessel_df[
                (vessel_df['day'] > event_day) &
                (vessel_df['day'] <= event_day + 30)
            ]

            if len(before_w) >= 3 and len(after_w) >= 3:
                stw_before = before_w['stw_corrected'].mean()
                stw_after = after_w['stw_corrected'].mean()
                improvement = (stw_after - stw_before) / stw_before * 100

                uwc_events.append({
                    'ship': vessel,
                    'event_day': event_day,
                    'baseline_stw': baseline_stw,
                    'stw_before_30d': stw_before,
                    'stw_after_30d': stw_after,
                    'stw_before_vs_baseline': (stw_before - baseline_stw) / baseline_stw * 100,
                    'stw_after_vs_baseline': (stw_after - baseline_stw) / baseline_stw * 100,
                    'improvement': improvement,
                    'n_before': len(before_w),
                    'n_after': len(after_w),
                })

    uwc_df = pd.DataFrame(uwc_events)

    print("=" * 120)
    print("ALL UWC EVENTS ANALYSIS")
    print("=" * 120)
    print(f"\nTotal UWC events: {len(uwc_df)}")
    print(f"Improved: {(uwc_df['improvement'] > 0).sum()} ({(uwc_df['improvement'] > 0).sum() / len(uwc_df) * 100:.1f}%)")
    print(f"Average improvement: {uwc_df['improvement'].mean():.2f}%\n")

    print(f"{'Ship':<6} {'Day':<6} {'前30日':<8} {'後30日':<8} {'相比基準':<20} {'改善':<8} {'原因分析':<40}")
    print("-" * 120)

    for _, row in uwc_df.iterrows():
        before_baseline = row['stw_before_vs_baseline']
        after_baseline = row['stw_after_vs_baseline']
        improvement = row['improvement']

        # 分析原因
        if improvement > 0:
            reason = "✓ 清洗有效 - 速度改善"
        else:
            # 分析為什麼沒改善
            if before_baseline < -10:
                reason = "船殼髒污嚴重，清洗後仍未回到基準"
            elif before_baseline > 10:
                reason = "清洗前速度就很好，清洗後沒有進一步改善"
            elif after_baseline < before_baseline:
                reason = "清洗後反而變差（可能環境變差）"
            else:
                reason = "清洗效果有限，或短期內看不到改善"

        print(f"{row['ship']:<6} {row['event_day']:>6.0f} {row['stw_before_30d']:>7.2f} {row['stw_after_30d']:>7.2f} "
              f"({before_baseline:+6.2f}% → {after_baseline:+6.2f}%) {improvement:+7.2f}%  {reason:<40}")

    # 統計分析
    print("\n" + "=" * 120)
    print("ROOT CAUSE ANALYSIS")
    print("=" * 120)

    print("\n1. 清洗前的船殼狀況（相比基準）:")
    print(f"   平均: {uwc_df['stw_before_vs_baseline'].mean():+.2f}%")
    print(f"   最差: {uwc_df['stw_before_vs_baseline'].min():+.2f}%")
    print(f"   最好: {uwc_df['stw_before_vs_baseline'].max():+.2f}%")

    print("\n2. 清洗後的船殼狀況（相比基準）:")
    print(f"   平均: {uwc_df['stw_after_vs_baseline'].mean():+.2f}%")
    print(f"   最差: {uwc_df['stw_after_vs_baseline'].min():+.2f}%")
    print(f"   最好: {uwc_df['stw_after_vs_baseline'].max():+.2f}%")

    print("\n3. 清洗效果:")
    improvement_mean = uwc_df['improvement'].mean()
    improved_count = (uwc_df['improvement'] > 0).sum()

    print(f"   平均改善: {improvement_mean:+.2f}%")
    print(f"   改善事件: {improved_count}/{len(uwc_df)}")

    if improvement_mean < 0:
        print("\n❌ 問題：UWC清洗反而導致速度下降")
        print("\n可能原因：")
        print("  1. 清洗前的船已經處於較好狀況（基準以上），清洗邊際效益有限")
        print("  2. 清洗後30天內環境變差（海況、溫度等），掩蓋了清洗效果")
        print("  3. 30天時間窗口太短或太長？")
        print("  4. UWC本身可能只是預防性維護，不像DD那樣有明顯改善")
        print("\n建議：")
        print("  - 嘗試更長的時間窗口（60-90天）看清洗效果是否在後期顯現")
        print("  - 或只看UWC+PP（清洗+拋光）而不是單純UWC")
        print("  - 或考慮UWC可能只在特定條件下（高污染率）才有效")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
