#!/usr/bin/env python3
"""
从 CSV 文件计算维修效果数据（含 RPM 正规化改善）并存到 DynamoDB。

使用新的 RPM 参数：±10 RPM, 1+ 数据点
数据来源：vt_fd.csv 和 maintenance.csv
"""
import pandas as pd
import boto3
import os
from datetime import datetime
from statistics import mean

REGION = os.getenv('AWS_REGION', 'us-east-1')
MAINT_TABLE = 'ship-analysis-dev-maintenance-effectiveness'

# RPM 参数（新的放宽版本）
RPM_TOLERANCE = 10
MIN_POINTS = 1
WINDOW_DAYS = 30

# 文件路径
VT_FD_PATH = "C:\\Users\\KiraLiou(劉容綺)\\ym-hackthon\\yangming-aws-summit-hackathon\\vt_fd.csv"
MAINT_PATH = "C:\\Users\\KiraLiou(劉容綺)\\ym-hackthon\\yangming-aws-summit-hackathon\\maintenance.csv"

dynamodb = boto3.resource('dynamodb', region_name=REGION)


def ensure_table_exists():
    """创建表（如不存在）。"""
    dynamodb_client = boto3.client('dynamodb', region_name=REGION)
    try:
        dynamodb_client.describe_table(TableName=MAINT_TABLE)
        print(f"Table {MAINT_TABLE} exists")
    except dynamodb_client.exceptions.ResourceNotFoundException:
        print(f"Creating table {MAINT_TABLE}...")
        dynamodb_client.create_table(
            TableName=MAINT_TABLE,
            KeySchema=[
                {'AttributeName': 'vessel_id', 'KeyType': 'HASH'},
                {'AttributeName': 'event_id', 'KeyType': 'RANGE'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'vessel_id', 'AttributeType': 'S'},
                {'AttributeName': 'event_id', 'AttributeType': 'S'},
            ],
            BillingMode='PAY_PER_REQUEST',
        )
        dynamodb_client.get_waiter('table_exists').wait(TableName=MAINT_TABLE)
        print(f"Table created")


def calc_rpm_normalized(timeline_df, event_day, vessel=None, debug=False):
    """计算 RPM 正规化改善 %，验证 RPM 范围内数据的有效性。"""
    before = timeline_df[(timeline_df['day'] >= event_day - WINDOW_DAYS) &
                         (timeline_df['day'] < event_day)]
    after = timeline_df[(timeline_df['day'] > event_day) &
                        (timeline_df['day'] <= event_day + WINDOW_DAYS)]

    if len(before) < 3 or len(after) < 3:
        return None, None

    try:
        rpm_after_avg = after['rpm'].mean()

        before_in_range = before[abs(before['rpm'] - rpm_after_avg) <= RPM_TOLERANCE]
        after_in_range = after[abs(after['rpm'] - rpm_after_avg) <= RPM_TOLERANCE]

        if len(before_in_range) < MIN_POINTS or len(after_in_range) < MIN_POINTS:
            return None, None

        foc_before = before_in_range['foc'].mean()
        foc_after = after_in_range['foc'].mean()
        rpm_before_avg = before_in_range['rpm'].mean()
        rpm_after_avg_actual = after_in_range['rpm'].mean()

        if foc_before <= 0 or foc_after <= 0:
            return None, None

        improvement = ((foc_before - foc_after) / foc_before) * 100

        # 验证数据质量
        if debug and vessel:
            print(f"  Day {event_day}: before_pts={len(before_in_range)}, after_pts={len(after_in_range)}, "
                  f"rpm_before={rpm_before_avg:.0f}, rpm_after={rpm_after_avg_actual:.0f}, "
                  f"foc_before={foc_before:.2f}, foc_after={foc_after:.2f}, improvement={improvement:.1f}%")

        return round(improvement, 1), {
            'before_pts': len(before_in_range),
            'after_pts': len(after_in_range),
            'rpm_range': (rpm_before_avg, rpm_after_avg_actual),
            'foc_range': (foc_before, foc_after),
        }
    except Exception as e:
        if debug:
            print(f"  Error: {e}")
        return None, None


def main():
    print("=" * 70)
    print("Calculating maintenance effectiveness from CSV")
    print("RPM params: ±10 RPM, 1+ points per side")
    print("=" * 70)

    ensure_table_exists()

    # 读取数据
    print("\nLoading vt_fd.csv...")
    vt_df = pd.read_csv(VT_FD_PATH)
    vt_df.rename(columns={'De-identification Name': 'vessel', 'NOON_UTC': 'day',
                          'ME_AVG_RPM': 'rpm', 'ME_FULLSPEED_CONSUMP_VLSFO': 'foc'},
                 inplace=True)
    vt_df = vt_df[['vessel', 'day', 'rpm', 'foc']].dropna()
    print(f"Loaded {len(vt_df)} records")

    print("\nLoading maintenance.csv...")
    maint_df = pd.read_csv(MAINT_PATH)
    print(f"Loaded {len(maint_df)} events")

    # 按船舶分组处理
    print("\nCalculating maintenance effectiveness...")
    table = dynamodb.Table(MAINT_TABLE)
    now = datetime.utcnow().isoformat()

    total_events = 0
    total_with_rpm_norm = 0

    for vessel in vt_df['vessel'].unique():
        vessel_timeline = vt_df[vt_df['vessel'] == vessel].copy()
        vessel_maint = maint_df[maint_df['ship_id'] == vessel]

        print(f"\n  {vessel}: {len(vessel_maint)} events")
        for _, maint in vessel_maint.iterrows():
            day = float(maint['event_day'])
            event_type = maint['event_type']

            # 计算 RPM 正规化改善
            rpm_norm, debug_info = calc_rpm_normalized(vessel_timeline, day, vessel=vessel, debug=True)

            item = {
                'vessel_id': vessel,
                'event_id': f"{day}_{event_type}",
                'day': float(day),
                'event_type': event_type,
                'rpm_normalized_improvement_pct': rpm_norm,
                'debug_info': debug_info,
                'computed_at': now,
            }

            table.put_item(Item=item)
            total_events += 1
            if rpm_norm is not None:
                total_with_rpm_norm += 1

    print("\n" + "=" * 70)
    print(f"✅ Completed!")
    print(f"   Total events: {total_events}")
    print(f"   Events with RPM-normalized improvement: {total_with_rpm_norm}")
    print(f"   Coverage: {100*total_with_rpm_norm/total_events:.1f}%")
    print(f"   Table: {MAINT_TABLE}")
    print("=" * 70)


if __name__ == '__main__':
    main()
