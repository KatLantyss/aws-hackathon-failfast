#!/usr/bin/env python3
"""
ISO 19030 Speed Loss 计算（基于 STW - Speed Through Water）
V_d = (V_m - V_e) / V_e × 100%

其中：
- V_e：预期船速（DD 后 7-14 天的平均 STW）
- V_m：实测船速（后续的 STW）
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
OUTPUT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\speed_loss_stw.csv"

BASELINE_START = 7      # DD 后 7 天开始
BASELINE_END = 14       # DD 后 14 天结束
WINDOW_DAYS = 45        # 维修前后各 45 天（中间值）
MIN_DATA_POINTS = 3     # 回到 3
HULL_CLEAN_TYPES = {'DD', 'UWC', 'UWC+PP'}


def main():
    print("Loading data...")
    maint_df = pd.read_csv(MAINT_PATH)
    vt_df = pd.read_csv(VT_FD_PATH, low_memory=False)

    # 准备数据
    vt_df.rename(columns={
        'De-identification Name': 'vessel',
        'NOON_UTC': 'day',
        'SPEED_THROUGH_WATER': 'stw',
    }, inplace=True)

    # 过滤：风力 <= 4, HOURS >= 22
    vt_df['wind_scale'] = pd.to_numeric(vt_df['WIND_SCALE'], errors='coerce')
    vt_df['hours_full_speed'] = pd.to_numeric(vt_df['HOURS_FULL_SPEED'], errors='coerce')
    vt_df = vt_df[(vt_df['wind_scale'] <= 4) & (vt_df['hours_full_speed'] >= 22)]

    vt_df['stw'] = pd.to_numeric(vt_df['stw'], errors='coerce')
    vt_df = vt_df[['vessel', 'day', 'stw']].dropna()
    vt_df = vt_df[(vt_df['stw'] > 0)]

    print(f"Loaded {len(vt_df)} valid STW records\n")

    # 计算每个维修事件的 Speed Loss
    results = []

    for vessel in sorted(vt_df['vessel'].unique()):
        print(f"{vessel}:")
        vessel_df = vt_df[vt_df['vessel'] == vessel].sort_values('day').reset_index(drop=True)
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        # 找 DD 事件作为基准
        dd_events = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] in HULL_CLEAN_TYPES
        ])

        # 为每个 DD 建立基准
        baselines = {}
        for dd_day in dd_events:
            baseline_window = vessel_df[
                (vessel_df['day'] > dd_day) &
                (vessel_df['day'] >= dd_day + BASELINE_START) &
                (vessel_df['day'] <= dd_day + BASELINE_END)
            ]

            if len(baseline_window) >= MIN_DATA_POINTS:
                baseline_stw = baseline_window['stw'].mean()
                baselines[dd_day] = baseline_stw
                print(f"  DD Day {dd_day:.0f}: V_e (baseline STW) = {baseline_stw:.2f} knots from {len(baseline_window)} records")

        # 对每个维修事件计算 Speed Loss
        for _, maint in vessel_maint.iterrows():
            event_day = float(maint['event_day'])
            event_type = maint['event_type']

            # 找最近的 DD 作为基准
            recent_dd = None
            for dd in sorted(baselines.keys()):
                if dd <= event_day:
                    recent_dd = dd

            if recent_dd is None:
                continue

            v_e = baselines[recent_dd]

            # 前后 30 天窗口
            before_w = vessel_df[
                (vessel_df['day'] >= event_day - WINDOW_DAYS) &
                (vessel_df['day'] < event_day)
            ]
            after_w = vessel_df[
                (vessel_df['day'] > event_day) &
                (vessel_df['day'] <= event_day + WINDOW_DAYS)
            ]

            # 计算 Speed Loss
            if len(before_w) >= MIN_DATA_POINTS and len(after_w) >= MIN_DATA_POINTS:
                stw_before = before_w['stw'].mean()
                stw_after = after_w['stw'].mean()

                sl_before = (stw_before - v_e) / v_e * 100
                sl_after = (stw_after - v_e) / v_e * 100
                sl_drop = sl_before - sl_after

                results.append({
                    'ship': vessel,
                    'event_day': event_day,
                    'event_type': event_type,
                    'baseline_stw': round(v_e, 2),
                    'stw_before_30d': round(stw_before, 2),
                    'stw_after_30d': round(stw_after, 2),
                    'sl_before_30d': round(sl_before, 2),
                    'sl_after_30d': round(sl_after, 2),
                    'sl_drop': round(sl_drop, 2),
                    'n_before': len(before_w),
                    'n_after': len(after_w),
                })

                indicator = "✓" if sl_drop > 0 else "✗"
                print(f"  Day {event_day:6.0f} {event_type:8s}: SL_before={sl_before:7.2f}%, SL_after={sl_after:7.2f}%, drop={sl_drop:7.2f}% {indicator}")

    # 输出 CSV
    output_df = pd.DataFrame(results)
    output_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")

    # 验证结果
    print("\n" + "=" * 80)
    print("VALIDATION: Does maintenance reduce Speed Loss?")
    print("=" * 80)

    valid_df = output_df[output_df['sl_drop'].notna()]
    if len(valid_df) > 0:
        improved = (valid_df['sl_drop'] > 0).sum()
        total = len(valid_df)
        improvement_rate = improved / total * 100
        avg_sl_drop = valid_df['sl_drop'].mean()

        print(f"Total maintenance events: {total}")
        print(f"Events with SL improvement (drop > 0): {improved} ({improvement_rate:.1f}%)")
        print(f"Average SL drop: {avg_sl_drop:.2f}%\n")

        print("By maintenance type:")
        for mtype in ['DD', 'UWC+PP', 'UWC', 'PP', 'UWI+PP', 'UWI']:
            group = valid_df[valid_df['event_type'] == mtype]
            if len(group) == 0:
                continue

            improved_type = (group['sl_drop'] > 0).sum()
            total_type = len(group)
            avg_sl = group['sl_drop'].mean()
            rate = improved_type / total_type * 100 if total_type > 0 else 0

            print(f"  {mtype:8s}: {improved_type:2d}/{total_type:2d} ({rate:5.1f}%) avg_SL_drop={avg_sl:6.2f}%")

        print("\n" + "=" * 80)
        print("Expected hierarchy (from best to worst):")
        print("  DD        should have highest SL improvement (>50%)")
        print("  UWC+PP    should have high improvement (>40%)")
        print("  UWC       should have medium improvement (>20%)")
        print("  PP        should have modest improvement (>10%)")
        print("  UWI+PP    should have small improvement (>5%)")
        print("  UWI       should have minimal improvement (~0%, just inspection)")
        print("=" * 80)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
