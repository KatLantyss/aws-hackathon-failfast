#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 vt_fd_speed_loss.csv 的 speed_loss 欄位補回 DynamoDB
表: ship-analysis-dev-vessel-data
PK: vessel_id
SK: sort_key — 沿用資料表既有的 row，用 UpdateItem 只新增 speed_loss 屬性，
    不會另外 PutItem 出新的 row。

vt_fd.csv（原始匯入來源）跟 vt_fd_speed_loss.csv 是同一批資料、逐行對齊，只是
多了 speed_loss 這一欄。既有 row 身上都有 row_index 屬性，其值就是它在
vt_fd.csv 裡的絕對（全檔案，不分船）行號 —— 用這個當 join key 是精確比對，
不需要用 NOON_UTC+VOYAGE 去猜（同一天同一 voyage 可能有多筆既有 row）。
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# 從環境變數讀取 AWS 配置
REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
TABLE_NAME = 'ship-analysis-dev-vessel-data'

# 初始化 DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

def read_csv(filepath):
    """讀取 CSV 文件"""
    print(f"Reading {filepath}...")
    df = pd.read_csv(filepath, low_memory=False)
    print(f"Loaded {len(df)} records")
    return df

def fetch_existing_rows_by_row_index(vessel_id):
    """抓出某艘船所有既有的 row（排除之前誤植的 day#...#voyage#... 格式），
    回傳 {row_index(int): sort_key} 供精確比對。"""
    items = []
    kwargs = dict(KeyConditionExpression=Key('vessel_id').eq(vessel_id))
    while True:
        r = table.query(**kwargs)
        items.extend(r['Items'])
        if 'LastEvaluatedKey' not in r:
            break
        kwargs['ExclusiveStartKey'] = r['LastEvaluatedKey']
    return {
        int(it['row_index']): it['sort_key']
        for it in items
        if not it.get('sort_key', '').startswith('day#') and 'row_index' in it
    }

def update_speed_loss(vessel_id, sort_key, speed_loss):
    table.update_item(
        Key={'vessel_id': vessel_id, 'sort_key': sort_key},
        UpdateExpression='SET speed_loss = :v',
        ExpressionAttributeValues={':v': Decimal(str(round(speed_loss, 2)))},
    )

def main():
    csv_path = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\yangming-aws-summit-hackathon\vt_fd_speed_loss.csv"

    print("=" * 80)
    print("DynamoDB speed_loss backfill: vt_fd_speed_loss.csv")
    print("=" * 80)
    print(f"Table: {TABLE_NAME}")
    print(f"Region: {REGION}")
    print(f"CSV: {csv_path}\n")

    # Absolute row index (0-based, matches vt_fd.csv's row_index attribute)
    # must be captured BEFORE any filtering, or the index would shift.
    df = read_csv(csv_path)
    df['_abs_row_index'] = df.index
    df = df[df['speed_loss'].notna()]
    print(f"Rows with a speed_loss value: {len(df)}\n")

    updated = 0
    skipped_no_match = 0
    row_index_cache = {}  # vessel_id -> {row_index: sort_key}

    for _, row in df.iterrows():
        vessel_id = str(row.get('De-identification Name', '')).strip()
        abs_row_index = int(row['_abs_row_index'])
        speed_loss = float(row['speed_loss'])

        if vessel_id not in row_index_cache:
            row_index_cache[vessel_id] = fetch_existing_rows_by_row_index(vessel_id)
        sort_key = row_index_cache[vessel_id].get(abs_row_index)

        if sort_key is None:
            skipped_no_match += 1
            continue

        update_speed_loss(vessel_id, sort_key, speed_loss)
        updated += 1
        if updated % 500 == 0:
            print(f"  ...{updated} rows updated so far")

    print(f"\n✓ Updated {updated} existing rows with speed_loss")
    print(f"✗ Skipped {skipped_no_match} CSV rows with no matching existing row (by row_index)")

if __name__ == '__main__':
    main()
