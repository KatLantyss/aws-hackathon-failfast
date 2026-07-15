#!/usr/bin/env python3
"""
预计算 Speed Loss Timeline 并存储到 DynamoDB。

队友可以直接查询 DynamoDB 获取预计算的 speed loss 数据，无需实时计算。
"""
import json
import boto3
import os
from handler import get_speed_loss
from typing import Any

# DynamoDB 配置
REGION = os.getenv('AWS_REGION', 'us-east-1')
SPEED_LOSS_TABLE = 'ship-analysis-dev-speed-loss-timeline'

# 所有 vessel IDs
VESSELS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12',
           'S21', 'S22', 'S23']

dynamodb = boto3.resource('dynamodb', region_name=REGION)


def ensure_table_exists():
    """确保 DynamoDB 表存在，如不存在则创建。"""
    dynamodb_client = boto3.client('dynamodb', region_name=REGION)

    try:
        dynamodb_client.describe_table(TableName=SPEED_LOSS_TABLE)
        print(f"✅ Table {SPEED_LOSS_TABLE} 已存在")
    except dynamodb_client.exceptions.ResourceNotFoundException:
        print(f"▶ 创建表 {SPEED_LOSS_TABLE}...")
        dynamodb_client.create_table(
            TableName=SPEED_LOSS_TABLE,
            KeySchema=[
                {'AttributeName': 'vessel_id', 'KeyType': 'HASH'},
                {'AttributeName': 'computed_at', 'KeyType': 'RANGE'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'vessel_id', 'AttributeType': 'S'},
                {'AttributeName': 'computed_at', 'AttributeType': 'S'},
            ],
            BillingMode='PAY_PER_REQUEST',
        )
        print(f"✅ 表已创建")
        dynamodb_client.get_waiter('table_exists').wait(TableName=SPEED_LOSS_TABLE)


def precompute_vessel(vessel_id: str):
    """预计算单个 vessel 的 speed loss 数据。"""
    print(f"\n▶ 预计算 {vessel_id}...", end=' ', flush=True)

    try:
        # 调用后端的 get_speed_loss 函数
        # 构造一个模拟的 event 对象
        event = {
            'pathParameters': {'vessel_id': vessel_id},
            'queryStringParameters': None,
        }
        response = get_speed_loss(vessel_id, event)

        if response.get('statusCode') != 200:
            print(f"❌ 状态码: {response.get('statusCode')}")
            return

        body = json.loads(response['body'])

        # 提取关键数据
        speed_loss_data = {
            'vessel_id': vessel_id,
            'computed_at': body.get('method', ''),
            'foc_timeline': body.get('foc_timeline', []),
            'stw_timeline': body.get('stw_timeline', []),
            'foc_summary': body.get('foc_summary', {}),
            'stw_summary': body.get('stw_summary', {}),
            'maintenance_cycles': body.get('maintenance_cycles', []),
        }

        # 写入 DynamoDB
        table = dynamodb.Table(SPEED_LOSS_TABLE)
        from datetime import datetime
        now = datetime.utcnow().isoformat()

        table.put_item(
            Item={
                'vessel_id': vessel_id,
                'computed_at': now,
                'data': json.dumps(speed_loss_data),
                'foc_records': len(speed_loss_data['foc_timeline']),
                'stw_records': len(speed_loss_data['stw_timeline']),
            }
        )

        print(f"✅ {len(speed_loss_data['foc_timeline'])} FOC records, {len(speed_loss_data['stw_timeline'])} STW records")

    except Exception as e:
        print(f"❌ {str(e)}")


def main():
    """主流程：预计算所有 vessel 的 speed loss。"""
    print("=" * 60)
    print("Speed Loss Timeline 预计算")
    print("=" * 60)

    # 确保表存在
    ensure_table_exists()

    # 预计算每个 vessel
    print(f"\n预计算 {len(VESSELS)} 个 vessels...")
    for vessel_id in VESSELS:
        precompute_vessel(vessel_id)

    print("\n" + "=" * 60)
    print("✅ 预计算完成！")
    print(f"   数据已存储到: {SPEED_LOSS_TABLE}")
    print("=" * 60)


if __name__ == '__main__':
    main()
