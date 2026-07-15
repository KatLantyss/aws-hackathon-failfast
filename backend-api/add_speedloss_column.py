#!/usr/bin/env python3
"""
為 vt_fd_speed_loss.csv 加上 speed_loss 欄位

每艘船各自的 Baseline（DD後90天的平均 STW）
然後計算 speed_loss = (baseline - stw_corrected) / baseline × 100%
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd_speed_loss.csv"
TEMP_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\vt_fd_speed_loss_temp.csv"
OUTPUT_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd_speed_loss.csv"

REF_WATER_TEMP = 15
REF_DRAFT = 8.0

MAINTENANCE_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
EXCLUDE_SHIPS = []  # 全部計算，包括S21


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
    df = pd.read_csv(VT_FD_PATH)
    maint_df = pd.read_csv(MAINTENANCE_PATH)

    print(f"Loaded {len(df)} records from vt_fd_speed_loss.csv\n")

    # 重命名列
    df.rename(columns={'De-identification Name': 'vessel', 'NOON_UTC': 'day'}, inplace=True)

    # 基礎過濾
    df['wind_scale'] = pd.to_numeric(df['WIND_SCALE'], errors='coerce')
    df['hours_full_speed'] = pd.to_numeric(df['HOURS_FULL_SPEED'], errors='coerce')

    # 計算修正STW
    df['stw_raw'] = pd.to_numeric(df['SPEED_THROUGH_WATER'], errors='coerce')
    df['stw_corrected'] = df.apply(calculate_corrected_stw, axis=1)

    # ========== 為每艘船建立Baseline ==========
    print("=" * 80)
    print("ESTABLISHING BASELINE FOR EACH SHIP (各自Baseline)")
    print("=" * 80)
    print()

    baselines = {}

    for vessel in sorted(df['vessel'].unique()):
        if vessel in EXCLUDE_SHIPS:
            print(f"{vessel}: ❌ 排除（數據品質問題）")
            continue

        vessel_df = df[df['vessel'] == vessel].sort_values('day')
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        # 找DD事件
        dd_events = sorted([
            float(m['event_day'])
            for _, m in vessel_maint.iterrows()
            if m['event_type'] == 'DD'
        ])

        if len(dd_events) > 0:
            dd_day = dd_events[0]
            baseline_window = vessel_df[
                (vessel_df['day'] >= dd_day) &
                (vessel_df['day'] <= dd_day + 90)
            ]

            if len(baseline_window) >= 3:
                baseline_stw = baseline_window['stw_corrected'].dropna().mean()
                baselines[vessel] = baseline_stw
                print(f"✓ {vessel}: baseline={baseline_stw:.2f}kt (DD day {dd_day:.0f}, {len(baseline_window)} records)")
            else:
                # 用全船平均
                baseline_stw = vessel_df['stw_corrected'].dropna().mean()
                baselines[vessel] = baseline_stw
                print(f"⚠️  {vessel}: baseline={baseline_stw:.2f}kt (全船平均，DD數據不足)")
        else:
            # 無DD，用全船平均
            baseline_stw = vessel_df['stw_corrected'].dropna().mean()
            baselines[vessel] = baseline_stw
            print(f"⚠️  {vessel}: baseline={baseline_stw:.2f}kt (無DD事件，全船平均)")

    print(f"\n✓ Established baselines for {len(baselines)} ships\n")

    # ========== 計算Speed Loss ==========
    print("=" * 80)
    print("CALCULATING SPEED LOSS FOR EACH RECORD")
    print("=" * 80)
    print()

    def calculate_speed_loss(row):
        vessel = row['vessel']
        stw_corrected = row['stw_corrected']

        # 穩態航行過濾：只對平靜航行計算 speed_loss
        wind_scale = row['wind_scale']
        hours_full_speed = row['hours_full_speed']

        # 恶劣天气或非全速航行 → speed_loss = None
        if wind_scale > 4 or hours_full_speed < 22:
            return None

        if vessel not in baselines or pd.isna(stw_corrected):
            return None

        baseline = baselines[vessel]
        if baseline <= 0:
            return None

        speed_loss = (baseline - stw_corrected) / baseline * 100
        return round(speed_loss, 2)

    df['speed_loss'] = df.apply(calculate_speed_loss, axis=1)

    # 添加 row_index（原始 vt_fd.csv 中的絕對行號）
    df['row_index'] = df.index

    # 移除臨時列
    df_output = df.drop(columns=['stw_raw', 'stw_corrected', 'wind_scale', 'hours_full_speed'])

    # 恢復原始列名
    df_output.rename(columns={'vessel': 'De-identification Name', 'day': 'NOON_UTC'}, inplace=True)

    # 先保存到臨時檔案，再覆蓋原檔案
    import shutil
    df_output.to_csv(TEMP_PATH, index=False, encoding='utf-8')
    shutil.move(TEMP_PATH, OUTPUT_PATH)
    print(f"✓ Saved to {OUTPUT_PATH}")

    # 統計
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)

    valid_records = df_output['speed_loss'].notna().sum()
    print(f"\nTotal records with speed_loss: {valid_records}")

    if valid_records > 0:
        print(f"Speed Loss range: {df_output['speed_loss'].min():.2f}% to {df_output['speed_loss'].max():.2f}%")
        print(f"Mean speed loss: {df_output['speed_loss'].mean():.2f}%")
        print(f"Median speed loss: {df_output['speed_loss'].median():.2f}%")

        print("\nBy ship:")
        for ship in sorted(df_output[df_output['speed_loss'].notna()]['De-identification Name'].unique()):
            ship_data = df_output[df_output['De-identification Name'] == ship]['speed_loss']
            print(f"  {ship}: avg={ship_data.mean():.2f}%, range={ship_data.min():.2f}%~{ship_data.max():.2f}% ({ship_data.notna().sum()} records)")

    print("\n✓ Done! speed_loss 欄位已添加")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
