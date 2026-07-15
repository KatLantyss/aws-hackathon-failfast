#!/usr/bin/env python3
"""
预计算维修效果数据（含 RPM 正规化改善）并存储到 DynamoDB。

使用新的 RPM 参数：
  - RPM 容差：±10 RPM（vs 旧的 ±5）
  - 最小数据点：1+ 每侧（vs 旧的 2+）

结果存到 DynamoDB，前端直接读取（无需实时计算）。
"""
import json
import boto3
import os
from handler import get_speed_loss, query_maintenance
from datetime import datetime
from statistics import mean
from typing import Optional

REGION = os.getenv('AWS_REGION', 'us-east-1')
MAINT_EFFECTIVENESS_TABLE = 'ship-analysis-dev-maintenance-effectiveness'

VESSELS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12',
           'S21', 'S22', 'S23']

dynamodb = boto3.resource('dynamodb', region_name=REGION)

# RPM 参数（新的放宽版本）
RPM_TOLERANCE = 10  # ±10 RPM
MIN_POINTS = 1      # 至少 1+ 数据点


def ensure_table_exists():
    """创建 DynamoDB 表（如不存在）。"""
    dynamodb_client = boto3.client('dynamodb', region_name=REGION)

    try:
        dynamodb_client.describe_table(TableName=MAINT_EFFECTIVENESS_TABLE)
        print(f"✅ Table {MAINT_EFFECTIVENESS_TABLE} 已存在")
    except dynamodb_client.exceptions.ResourceNotFoundException:
        print(f"▶ 创建表 {MAINT_EFFECTIVENESS_TABLE}...")
        dynamodb_client.create_table(
            TableName=MAINT_EFFECTIVENESS_TABLE,
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
        print(f"✅ 表已创建")
        dynamodb_client.get_waiter('table_exists').wait(TableName=MAINT_EFFECTIVENESS_TABLE)


def calc_rpm_normalized(
    foc_timeline: list,
    maint_event: dict,
    window_days: int = 30
) -> Optional[float]:
    """计算 RPM 正规化改善 %。"""
    day = maint_event.get('event_day', 0)

    before = [p for p in foc_timeline if day - window_days <= p['noon_day'] < day]
    after = [p for p in foc_timeline if day < p['noon_day'] <= day + window_days]

    if len(before) < 3 or len(after) < 3 or not after:
        return None

    try:
        rpm_after_avg = mean([p['rpm'] for p in after if p.get('rpm')])
    except:
        return None

    before_in_range = [
        p for p in before
        if 'rpm' in p and abs(p['rpm'] - rpm_after_avg) <= RPM_TOLERANCE
    ]
    after_in_range = [
        p for p in after
        if 'rpm' in p and abs(p['rpm'] - rpm_after_avg) <= RPM_TOLERANCE
    ]

    if len(before_in_range) < MIN_POINTS or len(after_in_range) < MIN_POINTS:
        return None

    try:
        foc_before = mean([p['daily_foc_vlsfo'] for p in before_in_range])
        foc_after = mean([p['daily_foc_vlsfo'] for p in after_in_range])

        if foc_before <= 0:
            return None

        return round(((foc_before - foc_after) / foc_before) * 100, 1)
    except:
        return None


def precompute_vessel(vessel_id: str):
    """预计算单个船舶的维修效果数据。"""
    print(f"\n▶ {vessel_id}...", end=' ', flush=True)

    try:
        # 获取 speed loss 数据
        event = {
            'pathParameters': {'vessel_id': vessel_id},
            'queryStringParameters': None,
        }
        response = get_speed_loss(vessel_id, event)

        if response.get('statusCode') != 200:
            print(f"❌")
            return

        body = json.loads(response['body'])
        foc_timeline = body.get('foc_timeline', [])

        # 获取维修事件
        maint_events = query_maintenance(vessel_id)

        # 计算每个维修事件的效果
        table = dynamodb.Table(MAINT_EFFECTIVENESS_TABLE)
        now = datetime.utcnow().isoformat()
        success_count = 0

        for maint in maint_events:
            day = maint.get('event_day', 0)
            event_type = maint.get('event_type', 'Unknown')

            # 计算 RPM 正规化改善
            rpm_norm = calc_rpm_normalized(foc_timeline, maint)

            item = {
                'vessel_id': vessel_id,
                'event_id': f"{day}_{event_type}",
                'day': float(day),
                'event_type': event_type,
                'rpm_normalized_improvement_pct': rpm_norm,
                'computed_at': now,
            }

            table.put_item(Item=item)
            success_count += 1

        print(f"✅ {success_count} events")

    except Exception as e:
        print(f"❌ {str(e)}")


def main():
    print("=" * 70)
    print("预计算维修效果（RPM正规化：±10 RPM, 1+ 数据点）")
    print("=" * 70)

    ensure_table_exists()

    print(f"\n计算 {len(VESSELS)} 个船舶...")
    for vessel_id in VESSELS:
        precompute_vessel(vessel_id)

    print("\n" + "=" * 70)
    print("✅ 完成！数据已存储到 DynamoDB")
    print(f"   表：{MAINT_EFFECTIVENESS_TABLE}")
    print("=" * 70)


if __name__ == '__main__':
    main()
