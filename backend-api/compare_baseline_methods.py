#!/usr/bin/env python3
"""
对比三种 baseline 定义方法的效果
方案 A: DD 后 7-14 天的最低 FOC
方案 B: 历史最低 FOC 作为绝对基准
方案 C: Rolling baseline（过去 60 天最低 FOC）
"""
import pandas as pd
import sys
from collections import defaultdict

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"

WINDOW_DAYS = 60
MIN_DATA_POINTS = 5
HULL_CLEAN_TYPES = {'DD', 'UWC', 'UWC+PP'}

# FOC标准化常数
LCV_VLSFO = 40.2
FUEL_COLS = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}


def calc_daily_foc(row):
    """标准化 FOC"""
    hfs = float(row.get('HOURS_FULL_SPEED', 0))
    if hfs < 22:
        return None

    best_col = None
    best_val = 0
    for col, lcv in FUEL_COLS.items():
        try:
            v = float(row.get(col, 0))
            if v > best_val:
                best_val = v
                best_col = col
        except:
            pass

    if best_col is None or best_val <= 0:
        return None

    lcv = FUEL_COLS[best_col]
    vlsfo_equiv = best_val * lcv / LCV_VLSFO
    daily_foc = vlsfo_equiv / hfs * 24.0
    return daily_foc


def analyze_method(vessel_df, vessel_maint, method_name):
    """分析一个方法"""
    results = []

    if method_name == "A":
        # 方案 A: DD 后 7-14 天的最低 FOC
        baselines = {}
        dd_events = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] in HULL_CLEAN_TYPES
        ])

        for dd_day in dd_events:
            baseline_window = vessel_df[
                (vessel_df['day'] > dd_day) &
                (vessel_df['day'] >= dd_day + 7) &
                (vessel_df['day'] <= dd_day + 14)
            ]
            if len(baseline_window) >= 3:
                baseline_foc = baseline_window['foc'].min()
                baselines[dd_day] = baseline_foc

        def get_baseline_a(day):
            recent_dd = None
            for dd in sorted(baselines.keys()):
                if dd <= day:
                    recent_dd = dd
            return baselines.get(recent_dd)

        vessel_df['baseline_foc'] = vessel_df['day'].apply(get_baseline_a)

    elif method_name == "B":
        # 方案 B: 历史最低 FOC 作为绝对基准
        global_min = vessel_df['foc'].min()
        vessel_df['baseline_foc'] = global_min

    elif method_name == "C":
        # 方案 C: Rolling baseline（过去 60 天最低 FOC）
        def rolling_min(day):
            window = vessel_df[(vessel_df['day'] >= day - 60) & (vessel_df['day'] <= day)]
            return window['foc'].min() if len(window) > 0 else None

        vessel_df['baseline_foc'] = vessel_df['day'].apply(rolling_min)

    # 计算 speed loss
    vessel_df['speed_loss_pct'] = vessel_df.apply(
        lambda r: max(0.0, (r['foc'] - r['baseline_foc']) / r['baseline_foc'] * 100)
        if r['baseline_foc'] and r['baseline_foc'] > 0 else None,
        axis=1
    )

    # 对每个维修事件计算
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

        if len(before_w) >= MIN_DATA_POINTS and len(after_w) >= MIN_DATA_POINTS:
            sl_before = before_w['speed_loss_pct'].mean()
            sl_after = after_w['speed_loss_pct'].mean()
            sl_drop = sl_before - sl_after
        else:
            sl_before = None
            sl_after = None
            sl_drop = None

        if sl_drop is not None:
            results.append({
                'event_type': event_type,
                'sl_drop': sl_drop,
                'improved': sl_drop > 0,
            })

    return results


def main():
    print("Loading data...")
    maint_df = pd.read_csv(MAINT_PATH)
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)

    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
        'ME_AVG_RPM': 'rpm',
    }, inplace=True)

    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    vt_df['foc'] = vt_df.apply(calc_daily_foc, axis=1)
    vt_df['rpm'] = pd.to_numeric(vt_df['rpm'], errors='coerce')

    vt_df = vt_df[['vessel', 'day', 'rpm', 'foc']].dropna()
    vt_df = vt_df[(vt_df['foc'] > 0) & (vt_df['rpm'] > 0)]

    print(f"Loaded {len(vt_df)} records\n")

    # 对三个方案进行分析
    all_results = {
        'A': [],
        'B': [],
        'C': [],
    }

    for vessel in sorted(vt_df['vessel'].unique()):
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day').reset_index(drop=True)
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        for method in ['A', 'B', 'C']:
            results = analyze_method(vessel_df.copy(), vessel_maint, method)
            all_results[method].extend(results)

    # 对比结果
    print("=" * 80)
    print("COMPARISON OF THREE BASELINE METHODS")
    print("=" * 80)

    methods_info = {
        'A': 'DD 后 7-14 天最低 FOC',
        'B': '历史最低 FOC',
        'C': 'Rolling 60 天最低 FOC',
    }

    for method in ['A', 'B', 'C']:
        print(f"\n【方案 {method}】{methods_info[method]}")
        print("-" * 80)

        results_df = pd.DataFrame(all_results[method])
        if len(results_df) == 0:
            print("No valid data")
            continue

        print(f"\nOverall: {(results_df['improved'].sum())}/{len(results_df)} ({results_df['improved'].mean()*100:.1f}%) improvement")
        print(f"Average SL drop: {results_df['sl_drop'].mean():.2f}%\n")

        print("By maintenance type:")
        for mtype in ['DD', 'UWC+PP', 'UWC', 'PP', 'UWI+PP', 'UWI']:
            group = results_df[results_df['event_type'] == mtype]
            if len(group) == 0:
                continue

            improved = group['improved'].sum()
            total = len(group)
            avg_drop = group['sl_drop'].mean()
            rate = improved / total * 100

            print(f"  {mtype:8s}: {improved:2d}/{total:2d} ({rate:5.1f}%) avg_drop={avg_drop:6.2f}%")

    # 最终评分
    print("\n" + "=" * 80)
    print("EVALUATION")
    print("=" * 80)

    scores = {}
    for method in ['A', 'B', 'C']:
        results_df = pd.DataFrame(all_results[method])

        # 计分标准：
        # 1. UWI 应该接近 0%（仅检查）
        # 2. DD 应该 > 50%（最彻底维修）
        # 3. UWI < PP < UWC < UWC+PP < DD（梯度）

        uwi_group = results_df[results_df['event_type'] == 'UWI']
        dd_group = results_df[results_df['event_type'] == 'DD']

        uwi_avg = uwi_group['sl_drop'].mean() if len(uwi_group) > 0 else 0
        dd_rate = (dd_group['improved'].sum() / len(dd_group) * 100) if len(dd_group) > 0 else 0

        # 评分：UWI 应该低，DD 应该高
        score = (100 - abs(uwi_avg)) * 0.5 + dd_rate * 0.5
        scores[method] = {
            'uwi_avg': uwi_avg,
            'dd_rate': dd_rate,
            'overall_improvement': results_df['improved'].mean() * 100,
            'score': score,
        }

    for method in ['A', 'B', 'C']:
        s = scores[method]
        print(f"\n方案 {method}:")
        print(f"  UWI 平均 drop: {s['uwi_avg']:6.2f}% (target: ~0%)")
        print(f"  DD 改善率: {s['dd_rate']:6.1f}% (target: >80%)")
        print(f"  整体改善率: {s['overall_improvement']:6.1f}%")
        print(f"  评分: {s['score']:.1f}/100")

    best = max(scores.items(), key=lambda x: x[1]['score'])
    print(f"\n✓ 推荐方案: {best[0]} (评分 {best[1]['score']:.1f})")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
