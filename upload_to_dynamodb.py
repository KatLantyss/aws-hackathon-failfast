#!/usr/bin/env python3
"""
上傳 CSV 數據到 DynamoDB（扁平化格式）
每個 CSV 欄位直接成為 DynamoDB attribute
"""
import boto3
import pandas as pd
from decimal import Decimal, InvalidOperation
import sys

AWS_REGION = 'us-east-1'
VESSEL_TABLE  = 'ship-analysis-dev-vessel-data'
MAINT_TABLE   = 'ship-analysis-dev-maintenance-events'
VESSEL_CSV    = '/Users/yinlchen/Workspace/aws-ai-hackathon/backend/hackathon-data/vt_fd_speed_loss.csv'
MAINT_CSV     = '/Users/yinlchen/Workspace/aws-ai-hackathon/backend/hackathon-data/maintenance.csv'


def to_ddb(value):
    """把 Python 值轉成 DynamoDB 支援的型別（Decimal 或 str），None 回 None"""
    if value is None:
        return None
    try:
        import math
        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:
        pass

    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    s = str(value).strip()
    return s if s else None


def delete_all_items(ddb_resource, table_name, pk, sk):
    """清空 DynamoDB table（scan + batch delete）"""
    table = ddb_resource.Table(table_name)
    print(f'  🗑  清空 {table_name} ...')
    count = 0
    scan_kwargs = {'ProjectionExpression': f'{pk}, {sk}'}
    while True:
        resp = table.scan(**scan_kwargs)
        items = resp.get('Items', [])
        if not items:
            break
        with table.batch_writer() as bw:
            for item in items:
                bw.delete_item(Key={pk: item[pk], sk: item[sk]})
        count += len(items)
        if 'LastEvaluatedKey' not in resp:
            break
        scan_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']
    print(f'     刪除 {count} 筆舊資料')


def upload_vessel(ddb_resource, csv_path):
    table = ddb_resource.Table(VESSEL_TABLE)
    df = pd.read_csv(csv_path, low_memory=False)
    print(f'\n📤  上傳 vessel 數據：{len(df)} 筆')

    with table.batch_writer() as bw:
        for idx, row in df.iterrows():
            vessel_id  = str(row['De-identification Name']).strip()
            noon_day   = int(row['NOON_UTC'])        # 相對天數 0‑1825
            voyage     = int(row['VOYAGE'])

            # partition key: vessel_id
            # sort key: NOON_UTC (天數) + row index 確保唯一
            sort_key = f'{noon_day:04d}#{idx}'

            item = {
                'vessel_id':  vessel_id,
                'sort_key':   sort_key,
                'NOON_UTC':   Decimal(noon_day),
                'VOYAGE':     Decimal(voyage),
                'row_index':  Decimal(idx),
            }

            # 把其餘欄位全部扁平化加入
            for col in df.columns:
                if col in ('De-identification Name', 'NOON_UTC', 'VOYAGE'):
                    continue
                v = to_ddb(row[col])
                if v is not None:
                    item[col] = v

            bw.put_item(Item=item)

            if (idx + 1) % 2000 == 0:
                print(f'   已處理 {idx + 1} / {len(df)} ...')

    print(f'✅  vessel 上傳完成')


def upload_maintenance(ddb_resource, csv_path):
    table = ddb_resource.Table(MAINT_TABLE)
    df = pd.read_csv(csv_path)
    print(f'\n📤  上傳 maintenance 數據：{len(df)} 筆')

    with table.batch_writer() as bw:
        for idx, row in df.iterrows():
            vessel_id  = str(row['ship_id']).strip()
            event_day  = int(row['event_day'])
            event_type = str(row['event_type']).strip()

            sort_key = f'{event_day:04d}#{event_type}#{idx}'

            item = {
                'vessel_id':  vessel_id,
                'sort_key':   sort_key,
                'event_day':  Decimal(event_day),
                'event_type': event_type,
                'row_index':  Decimal(idx),
            }

            for col in df.columns:
                if col in ('ship_id', 'event_day', 'event_type'):
                    continue
                v = to_ddb(row[col])
                if v is not None:
                    item[col] = v

            bw.put_item(Item=item)

    print(f'✅  maintenance 上傳完成')


def recreate_table(client, table_name, pk, sk):
    """刪除並重建 table（確保 schema 正確）"""
    try:
        client.delete_table(TableName=table_name)
        print(f'  ⏳ 等待 {table_name} 刪除...')
        client.get_waiter('table_not_exists').wait(TableName=table_name)
        print(f'  ✓ 已刪除')
    except client.exceptions.ResourceNotFoundException:
        pass

    client.create_table(
        TableName=table_name,
        KeySchema=[
            {'AttributeName': pk, 'KeyType': 'HASH'},
            {'AttributeName': sk, 'KeyType': 'RANGE'},
        ],
        AttributeDefinitions=[
            {'AttributeName': pk, 'AttributeType': 'S'},
            {'AttributeName': sk, 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST',
        Tags=[
            {'Key': 'Project',    'Value': 'ship-analysis'},
            {'Key': 'Hackathon',  'Value': 'YangMing-AI-2026'},
        ]
    )
    print(f'  ⏳ 等待 {table_name} 建立...')
    client.get_waiter('table_exists').wait(TableName=table_name)
    print(f'  ✅ {table_name} 已就緒')


def main():
    vessel_only = '--vessel-only' in sys.argv

    print('=' * 60)
    print('📊  CSV → DynamoDB（扁平化格式）')
    print('=' * 60)

    ddb_client   = boto3.client('dynamodb', region_name=AWS_REGION)
    ddb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)

    # 確認憑證
    sts = boto3.client('sts', region_name=AWS_REGION)
    print('Account:', sts.get_caller_identity()['Account'])

    # 重建 vessel table（sort key 換成 sort_key）
    print(f'\n🔧  重建 DynamoDB tables...')
    recreate_table(ddb_client, VESSEL_TABLE, 'vessel_id', 'sort_key')
    if not vessel_only:
        recreate_table(ddb_client, MAINT_TABLE, 'vessel_id', 'sort_key')

    # 上傳
    upload_vessel(ddb_resource, VESSEL_CSV)
    if not vessel_only:
        upload_maintenance(ddb_resource, MAINT_CSV)

    print('\n' + '=' * 60)
    print('✅  全部完成！')
    print(f'   vessel table   : {VESSEL_TABLE}')
    if not vessel_only:
        print(f'   maintenance table: {MAINT_TABLE}')
    print(f'   https://console.aws.amazon.com/dynamodbv2/home?region={AWS_REGION}#tables')
    print('=' * 60)


if __name__ == '__main__':
    main()
