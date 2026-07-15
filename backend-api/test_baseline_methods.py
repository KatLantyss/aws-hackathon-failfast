#!/usr/bin/env python3
"""
測試不同的baseline定義方式對維修效果的影響
特別關注為什麼UWC反而下降
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


def analyze_with_baseline(vt_df, maint_df, baseline_method_name, baseline_method_func):
    """用特定baseline方法分析維修效果"""
    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        # 計算baseline
        baseline_stw = baseline_method_func(vessel_df, vessel_maint)

        if baseline_stw is None:
            continue

        # 分析每個維修事件
        for _, maint in vessel_maint.iterrows():
            event_day = float(maint['event_day'])
            event_type = maint['event_type']

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

                # 計算相對改善
                improvement = (stw_after - stw_before) / stw_before * 100

                results.append({
                    'event_type': event_type,
                    'improvement': improvement,
                    'improved': improvement > 0,
                })

    return pd.DataFrame(results)


# 不同的baseline定義方法
def baseline_dd_plus_7_14(vessel_df, vessel_maint):
    """DD後7-14天"""
    dd_events = [float(m['event_day']) for _, m in vessel_maint.iterrows() if m['event_type'] == 'DD']
    if len(dd_events) > 0:
        earliest_dd = sorted(dd_events)[0]
        baseline_window = vessel_df[
            (vessel_df['day'] > earliest_dd + 7) &
            (vessel_df['day'] <= earliest_dd + 14)
        ]
        if len(baseline_window) >= 3:
            return baseline_window['stw_corrected'].mean()
    return None


def baseline_before_60_days(vessel_df, vessel_maint):
    """每個事件前60天的平均"""
    min_day = vessel_df['day'].min()
    baseline_window = vessel_df[vessel_df['day'] >= min_day]
    if len(baseline_window) >= 3:
        return baseline_window['stw_corrected'].mean()
    return None


def baseline_overall_mean(vessel_df, vessel_maint):
    """整個船的平均"""
    if len(vessel_df) >= 3:
        return vessel_df['stw_corrected'].mean()
    return None


def baseline_before_90_days(vessel_df, vessel_maint):
    """全船前90天平均（假設開始時最乾淨）"""
    early_window = vessel_df[vessel_df['day'] <= 90]
    if len(early_window) >= 3:
        return early_window['stw_corrected'].mean()
    return None


def baseline_percentile_90(vessel_df, vessel_maint):
    """歷史90分位數（代表較好狀況）"""
    if len(vessel_df) >= 3:
        return vessel_df['stw_corrected'].quantile(0.9)
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

    # 測試不同的baseline方法
    baseline_methods = [
        ("DD後7-14天", baseline_dd_plus_7_14),
        ("全船平均", baseline_overall_mean),
        ("早期90天平均", baseline_before_90_days),
        ("90分位數（代表較好狀況）", baseline_percentile_90),
    ]

    print("=" * 100)
    print("BASELINE METHODS COMPARISON - Focus on UWC effectiveness")
    print("=" * 100)

    results_summary = {}

    for method_name, method_func in baseline_methods:
        print(f"\n【{method_name}】")
        print("-" * 100)

        result_df = analyze_with_baseline(vt_df, maint_df, method_name, method_func)

        if len(result_df) > 0:
            results_summary[method_name] = result_df

            # 總體結果
            improved = result_df['improved'].sum()
            total = len(result_df)
            rate = improved / total * 100
            avg_imp = result_df['improvement'].mean()

            print(f"Total: {total}, Improved: {improved} ({rate:.1f}%), Avg: {avg_imp:.2f}%\n")

            # 按維修類型分析
            for mtype in ['DD', 'UWC+PP', 'UWC', 'PP', 'UWI+PP', 'UWI']:
                group = result_df[result_df['event_type'] == mtype]
                if len(group) > 0:
                    impr = group['improved'].sum()
                    tot = len(group)
                    rate_type = impr / tot * 100
                    avg_type = group['improvement'].mean()
                    print(f"  {mtype:8s}: {impr:2d}/{tot:2d} ({rate_type:5.1f}%) avg={avg_type:+6.2f}%")

    # 重點關注UWC
    print("\n" + "=" * 100)
    print("FOCUS: UWC Performance Across Baseline Methods")
    print("=" * 100)

    uwc_data = {}
    for method_name, result_df in results_summary.items():
        uwc_group = result_df[result_df['event_type'] == 'UWC']
        if len(uwc_group) > 0:
            impr = uwc_group['improved'].sum()
            tot = len(uwc_group)
            rate = impr / tot * 100
            avg = uwc_group['improvement'].mean()
            uwc_data[method_name] = {'rate': rate, 'avg': avg, 'n': tot}

    print("\nUWC結果對比：")
    print(f"{'方法':<30} {'改善數/總數':<15} {'改善率':<12} {'平均改善':<15}")
    print("-" * 100)
    for method_name in sorted(uwc_data.keys(), key=lambda x: uwc_data[x]['avg'], reverse=True):
        data = uwc_data[method_name]
        improved = sum([1 for v in results_summary[method_name][results_summary[method_name]['event_type']=='UWC']['improvement'] if v > 0])
        print(f"{method_name:<30} {improved:2d}/{data['n']:<13d} {data['rate']:>6.1f}%       {data['avg']:>+7.2f}%")

    print("\n建議：最合理的baseline是 ", max(uwc_data.keys(), key=lambda x: uwc_data[x]['avg']))


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
