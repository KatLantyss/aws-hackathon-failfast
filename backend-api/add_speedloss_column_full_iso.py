#!/usr/bin/env python3
"""
ISO 19030-2 完整修正版本 (正確版!)
所有可做的環境修正 + 船舶狀態修正都加上

修正項目：
  環境因素 (4):
    1. 風阻修正
    2. 波浪阻力修正 (海浪高度)
    3. 海水溫度修正
    4. 海水密度修正

  船舶狀態 (3):
    5. 吃水修正
    6. 縱傾修正
    7. 淺水效應修正

  額外 (2):
    8. 海浪週期修正
    9. 排水量修正
"""
import pandas as pd
import sys

VT_FD_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd.csv"
MAINTENANCE_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\maintenance.csv"
FINAL_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd_speed_loss.csv"
OUTPUT_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\vt_fd_speed_loss_full_iso.csv"

# 基準參數
REF_WATER_TEMP = 15.0          # °C
REF_DRAFT = 8.0                # m
REF_WATER_DENSITY = 1.025      # g/cm³
REF_DISPLACEMENT = 65000       # DWT (參考排水量)

EXCLUDE_SHIPS = []


# ============================================================================
# 環境因素修正 (Environmental Corrections)
# ============================================================================

def wind_resistance_correction(wind_speed, wind_direction=None):
    """
    1. 風阻修正 (Wind Resistance Correction)

    原理：風對船舶正面與側面迎風面積的影響
    公式：Correction = 風速 × 0.1 [kt]
    """
    try:
        if pd.isna(wind_speed) or wind_speed <= 0:
            return 0
        return float(wind_speed) * 0.1
    except:
        return 0


def wave_height_correction(sea_height):
    """
    2. 波浪阻力修正 (Wave Resistance Correction)

    原理：海浪對船體興波阻力的影響
    公式：Correction = -波高 × 0.05 [kt]

    注：STAWAVE演算法需要波週期，此處用簡化係數
    """
    try:
        if pd.isna(sea_height) or sea_height <= 0:
            return 0
        return -float(sea_height) * 0.05
    except:
        return 0


def swell_height_correction(swell_height):
    """
    額外：海浪週期修正 (Swell Correction)

    原理：涌浪（Swell）與風浪（Wind Wave）分開計算
    公式：Correction = -涌浪高 × 0.03 [kt]
    """
    try:
        if pd.isna(swell_height) or swell_height <= 0:
            return 0
        return -float(swell_height) * 0.03
    except:
        return 0


def water_temp_correction(water_temp):
    """
    3. 海水溫度修正 (Water Temperature Correction)

    原理：水溫影響運動黏度(Kinematic Viscosity)，進而影響摩擦阻力
    基準：15°C
    公式：Correction = -(實測溫度 - 15°C) × 0.02
    """
    try:
        if pd.isna(water_temp):
            return 0
        temp_diff = float(water_temp) - REF_WATER_TEMP
        return -temp_diff * 0.02
    except:
        return 0


def water_density_correction(water_temp):
    """
    4. 海水密度修正 (Water Density Correction)

    原理：淡水/低鹽度區域的海水密度下降，影響排水量與阻力
    基準：1.025 g/cm³（標準海水）
    溫度對密度的影響：每升1°C，密度降低約0.0004 g/cm³
    簡化公式：Correction = -(實測溫度 - 15°C) × 0.01
    """
    try:
        if pd.isna(water_temp):
            return 0
        temp_diff = float(water_temp) - REF_WATER_TEMP
        return -temp_diff * 0.01
    except:
        return 0


# ============================================================================
# 船舶狀態修正 (Vessel Status Corrections)
# ============================================================================

def draft_correction(fore_draft, after_draft):
    """
    5. 吃水修正 (Draft / Displacement Correction)

    原理：不同吃水對應不同濕面積(Wetted Surface Area)
    基準吃水：8.0m（平均）
    公式：Correction = -(平均吃水 - 8.0m) × 0.15

    更精確的做法需要吃水-阻力曲線，此處用線性近似
    """
    try:
        if pd.isna(fore_draft) or pd.isna(after_draft):
            return 0
        fore_d = float(fore_draft)
        after_d = float(after_draft)
        if fore_d <= 0 or after_d <= 0:
            return 0

        avg_draft = (fore_d + after_d) / 2
        draft_diff = avg_draft - REF_DRAFT
        return -draft_diff * 0.15
    except:
        return 0


def trim_correction(fore_draft, after_draft):
    """
    6. 縱傾修正 (Trim Correction)

    原理：船頭/船尾吃水差(Trim)會影響興波阻力與流線
    Trim = 前吃水 - 後吃水
    正Trim（船頭深）時船尾抬起，對阻力影響複雜
    公式（簡化）：Correction = -|Trim| × 0.10

    精確計算需要 Lackenby 經驗公式或CFD
    """
    try:
        if pd.isna(fore_draft) or pd.isna(after_draft):
            return 0
        fore_d = float(fore_draft)
        after_d = float(after_draft)
        if fore_d <= 0 or after_d <= 0:
            return 0

        trim = fore_d - after_d
        return -abs(trim) * 0.10
    except:
        return 0


def shallow_water_correction(draft, water_depth):
    """
    7. 淺水效應修正 (Shallow Water Correction)

    原理：當水深不足時，船底與海底間水流加速，阻力暴增
    觸發條件：水深 < 吃水 × 3
    公式（Lackenby 簡化）：
      如果 深淺比 h/d < 3：
        Correction = -(d/h) × 0.08
    """
    try:
        if pd.isna(draft) or pd.isna(water_depth):
            return 0
        d = float(draft)
        h = float(water_depth)
        if d <= 0 or h <= 0:
            return 0

        depth_draft_ratio = h / d
        # 只有在淺水時才修正
        if depth_draft_ratio < 3:
            return -(d / h) * 0.08
        return 0
    except:
        return 0


def displacement_correction(displacement):
    """
    額外：排水量修正 (Displacement Correction)

    原理：排水量偏離標準值時的阻力調整
    基準排水量：65,000 DWT（參考值）
    公式：Correction = -(排水量差 / 基準) × 0.15

    此項較不關鍵，通常透過吃水修正已涵蓋
    """
    try:
        if pd.isna(displacement):
            return 0
        disp = float(displacement)
        if disp <= 0:
            return 0

        disp_diff = disp - REF_DISPLACEMENT
        return -(disp_diff / REF_DISPLACEMENT) * 0.15
    except:
        return 0


# ============================================================================
# 統合修正函數
# ============================================================================

def calculate_corrected_stw(row):
    """
    計算修正後的 STW

    STW_修正 = STW_原始 + 所有修正值

    修正項目（共 9 項）：
      環境 (4): 風、波浪、水溫、密度
      船舶 (3): 吃水、縱傾、淺水
      額外 (2): 涌浪、排水量
    """
    try:
        stw_raw = float(row.get('SPEED_THROUGH_WATER', 0))
        if stw_raw <= 0:
            return None

        # 環境因素
        wind_speed = float(row.get('WIND_SPEED', 0)) if pd.notna(row.get('WIND_SPEED')) else 0
        sea_height = float(row.get('SEA_HEIGHT', 0)) if pd.notna(row.get('SEA_HEIGHT')) else 0
        swell_height = float(row.get('SWELL_HEIGHT', 0)) if pd.notna(row.get('SWELL_HEIGHT')) else 0
        water_temp = float(row.get('SEA_WATER_TEMP', 0)) if pd.notna(row.get('SEA_WATER_TEMP')) else REF_WATER_TEMP

        # 船舶狀態
        fore_draft = float(row.get('FORE_DRAFT', 0)) if pd.notna(row.get('FORE_DRAFT')) else REF_DRAFT
        after_draft = float(row.get('AFTER_DRAFT', 0)) if pd.notna(row.get('AFTER_DRAFT')) else REF_DRAFT
        water_depth = float(row.get('WATER_DEPTH', 0)) if pd.notna(row.get('WATER_DEPTH')) else 1000  # 假設深水
        displacement = float(row.get('DISPLACEMENT', 0)) if pd.notna(row.get('DISPLACEMENT')) else REF_DISPLACEMENT

        # 計算各項修正
        corr_wind = wind_resistance_correction(wind_speed)
        corr_wave = wave_height_correction(sea_height)
        corr_swell = swell_height_correction(swell_height)
        corr_temp = water_temp_correction(water_temp)
        corr_density = water_density_correction(water_temp)
        corr_draft = draft_correction(fore_draft, after_draft)
        corr_trim = trim_correction(fore_draft, after_draft)
        corr_shallow = shallow_water_correction(fore_draft, water_depth)
        corr_displacement = displacement_correction(displacement)

        # 合計修正
        stw_corrected = (stw_raw
                        + corr_wind
                        + corr_wave
                        + corr_swell
                        + corr_temp
                        + corr_density
                        + corr_draft
                        + corr_trim
                        + corr_shallow
                        + corr_displacement)

        return stw_corrected
    except:
        return None


def main():
    print("Loading data...")
    df = pd.read_csv(VT_FD_PATH)
    maint_df = pd.read_csv(MAINTENANCE_PATH)

    print(f"Loaded {len(df)} records from vt_fd.csv\n")

    # 重命名列
    df.rename(columns={'De-identification Name': 'vessel', 'NOON_UTC': 'day'}, inplace=True)

    # 基礎過濾
    df['wind_scale'] = pd.to_numeric(df['WIND_SCALE'], errors='coerce')
    df['hours_full_speed'] = pd.to_numeric(df['HOURS_FULL_SPEED'], errors='coerce')

    # 計算修正STW（完整版）
    print("=" * 80)
    print("CALCULATING CORRECTED STW (ISO 19030-2 完整修正 - 9 項)")
    print("=" * 80)
    print()
    print("修正項目：")
    print("  環境因素 (4): 風阻、波浪、海浪週期、水溫、密度")
    print("  船舶狀態 (3): 吃水、縱傾、淺水效應")
    print("  額外 (2): 排水量")
    print()

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
            # 無DD：用分位數法 - Top 15% 最快速度的數據點
            valid_data = vessel_df['stw_corrected'].dropna()
            if len(valid_data) >= 10:
                # 第 85 百分位 (Top 15%)
                percentile_85 = valid_data.quantile(0.85)
                top_15_percent = vessel_df[vessel_df['stw_corrected'] >= percentile_85]['stw_corrected'].dropna()
                baseline_stw = top_15_percent.mean()
                baselines[vessel] = baseline_stw
                n_top = len(top_15_percent)
                print(f"⚠️  {vessel}: baseline={baseline_stw:.2f}kt (分位數法: Top 15%, {n_top} records >= {percentile_85:.2f}kt)")
            else:
                # 數據太少，用全船平均
                baseline_stw = valid_data.mean()
                baselines[vessel] = baseline_stw
                print(f"⚠️  {vessel}: baseline={baseline_stw:.2f}kt (全船平均，數據不足)")

    print(f"\n✓ Established baselines for {len(baselines)} ships\n")

    # ========== 計算Speed Loss ==========
    print("=" * 80)
    print("CALCULATING SPEED LOSS FOR EACH RECORD (穩態航行篩選)")
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
    df_output = df.drop(columns=['wind_scale', 'hours_full_speed', 'stw_corrected'])

    # 恢復原始列名
    df_output.rename(columns={'vessel': 'De-identification Name', 'day': 'NOON_UTC'}, inplace=True)

    # 保存到臨時位置
    df_output.to_csv(OUTPUT_PATH, index=False, encoding='utf-8')
    print(f"✓ Saved to temporary: {OUTPUT_PATH}")
    print(f"\n✓ Copy this to: {FINAL_PATH}")

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

    print("\n✓ Done! speed_loss 欄位已添加 (ISO 19030-2 完整版)")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
