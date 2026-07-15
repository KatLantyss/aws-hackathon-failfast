#!/usr/bin/env python3
"""
生成DynamoDB的3種格式：
1. Event-based: 維修事件效果分析
2. Daily: 每日speed loss監控
3. Native: DynamoDB原生格式（可直接批量導入）
"""
import pandas as pd
import json
from datetime import datetime, timedelta
import sys

EVENT_CSV_PATH = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\maintenance_effectiveness_final.csv"
DAILY_CSV_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\daily_speedloss.csv"

OUTPUT_EVENTS_CSV = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\dynamodb_events.csv"
OUTPUT_EVENTS_JSONL = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\dynamodb_events.jsonl"
OUTPUT_DAILY_CSV = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\dynamodb_daily.csv"
OUTPUT_DAILY_JSONL = r"C:\Users\KiraLiou(劉容綺)\ym-hackthon\backend-api\dynamodb_daily.jsonl"

# 基準日期（day 0 = 2020-01-01）
BASE_DATE = datetime(2020, 1, 1)


def day_to_date(day_number):
    try:
        return BASE_DATE + timedelta(days=float(day_number))
    except:
        return BASE_DATE


def format_dynamodb_item(item_dict):
    """將Python dict轉換為DynamoDB JSON格式"""
    dynamodb_item = {}
    for key, value in item_dict.items():
        if isinstance(value, str):
            dynamodb_item[key] = {"S": value}
        elif isinstance(value, (int, float)):
            dynamodb_item[key] = {"N": str(value)}
        elif isinstance(value, bool):
            dynamodb_item[key] = {"BOOL": value}
        elif value is None:
            dynamodb_item[key] = {"NULL": True}
    return dynamodb_item


def main():
    print("=" * 100)
    print("GENERATING DYNAMODB FORMATS")
    print("=" * 100)

    # ========== 1. EVENT-BASED FORMAT ==========
    print("\n【1. EVENT-BASED FORMAT】")
    print("-" * 100)

    event_df = pd.read_csv(EVENT_CSV_PATH)

    # 準備CSV版本
    event_csv_data = []
    for _, row in event_df.iterrows():
        date = day_to_date(row['event_day'])
        event_csv_data.append({
            'PK': f"SHIP#{row['ship']}",
            'SK': f"MAINT#{row['event_day']:.0f}",
            'ship': row['ship'],
            'event_day': row['event_day'],
            'event_date': date.isoformat(),
            'event_type': row['event_type'],
            'window_days': row['window_days'],
            'stw_before': row['stw_before'],
            'stw_after': row['stw_after'],
            'improvement_pct': row['improvement_pct'],
            'n_before': row['n_before'],
            'n_after': row['n_after'],
            'improved': 'Y' if row['improvement_pct'] > 0 else 'N',
            'timestamp': int(date.timestamp()),
        })

    event_csv_df = pd.DataFrame(event_csv_data)
    event_csv_df.to_csv(OUTPUT_EVENTS_CSV, index=False, encoding='utf-8')
    print(f"✓ Saved: {OUTPUT_EVENTS_CSV}")

    # 準備JSONL版本（DynamoDB批量導入格式）
    with open(OUTPUT_EVENTS_JSONL, 'w', encoding='utf-8') as f:
        for row in event_csv_data:
            dynamodb_item = format_dynamodb_item(row)
            f.write(json.dumps(dynamodb_item) + '\n')

    print(f"✓ Saved: {OUTPUT_EVENTS_JSONL}")

    # ========== 2. DAILY FORMAT ==========
    print("\n【2. DAILY SPEED LOSS FORMAT】")
    print("-" * 100)

    daily_df = pd.read_csv(DAILY_CSV_PATH)

    # 準備CSV版本
    daily_csv_data = []
    for _, row in daily_df.iterrows():
        date = day_to_date(row['day'])
        daily_csv_data.append({
            'PK': f"SHIP#{row['ship']}",
            'SK': f"DAY#{row['day']:.0f}",
            'ship': row['ship'],
            'day': row['day'],
            'date': date.isoformat(),
            'stw_raw': row['stw_raw'],
            'stw_corrected': row['stw_corrected'],
            'baseline_stw': row['baseline_stw'],
            'speed_loss_pct': row['speed_loss_pct'],
            'timestamp': int(date.timestamp()),
        })

    daily_csv_df = pd.DataFrame(daily_csv_data)
    daily_csv_df.to_csv(OUTPUT_DAILY_CSV, index=False, encoding='utf-8')
    print(f"✓ Saved: {OUTPUT_DAILY_CSV}")

    # 準備JSONL版本
    with open(OUTPUT_DAILY_JSONL, 'w', encoding='utf-8') as f:
        for row in daily_csv_data:
            dynamodb_item = format_dynamodb_item(row)
            f.write(json.dumps(dynamodb_item) + '\n')

    print(f"✓ Saved: {OUTPUT_DAILY_JSONL}")

    # ========== SUMMARY ==========
    print("\n" + "=" * 100)
    print("DYNAMODB TABLE SCHEMA RECOMMENDATION")
    print("=" * 100)

    print("\nTable 1: ShipMaintenanceEvents")
    print("""
      Primary Key:
        PK: "SHIP#{ship_id}"         (Partition Key)
        SK: "MAINT#{day_number}"     (Sort Key)

      Attributes:
        - ship: string
        - event_date: string (ISO 8601)
        - event_type: string (DD, UWC, UWC+PP, PP, UWI+PP, UWI)
        - window_days: number
        - stw_before, stw_after: number
        - improvement_pct: number
        - improved: string (Y/N)
        - timestamp: number

      GSI: event_type-timestamp-index
        PK: event_type
        SK: timestamp
        (用於查詢特定維修類型的所有事件)

      Queries:
        - 查單艘船所有維修事件
        - 查單艘船某時間範圍的維修
        - 按維修類型統計效果
    """)

    print("\nTable 2: ShipDailySpeedLoss")
    print("""
      Primary Key:
        PK: "SHIP#{ship_id}"         (Partition Key)
        SK: "DAY#{day_number}"       (Sort Key)

      Attributes:
        - ship: string
        - date: string (ISO 8601)
        - stw_raw, stw_corrected: number
        - baseline_stw: number
        - speed_loss_pct: number
        - timestamp: number

      GSI: latest-speed-loss
        PK: "LATEST"
        SK: timestamp
        (用於實時查詢最新速度損失)

      Queries:
        - 查單艘船的每日speed loss趨勢
        - 查單艘船某時間範圍的speed loss
        - 實時查詢所有船的最新speed loss
    """)

    print("\n" + "=" * 100)
    print("IMPORT TO DYNAMODB - Multiple Options")
    print("=" * 100)

    print("""
1️⃣  AWS CLI (Batch Write):
    aws dynamodb batch-write-item \\
      --request-items file://dynamodb_events.jsonl \\
      --region ap-northeast-1

2️⃣  AWS Data Pipeline (S3 → DynamoDB):
    1. Upload CSV to S3
    2. Go to DynamoDB Console
    3. Select table → Import from S3
    4. Specify CSV file path

3️⃣  DynamoDB Console (PartiQL):
    1. Go to DynamoDB Console
    2. Select table → PartiQL editor
    3. Use INSERT statements from JSON

4️⃣  AWS SDK (Python/Node/Java):
    import boto3
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('ShipMaintenanceEvents')

    with open('dynamodb_events.jsonl') as f:
        for line in f:
            item = json.loads(line)
            table.put_item(Item=item)

5️⃣  Recommended: AWS Data Exchange Pipeline
    - Upload JSONL to S3
    - Create Lambda function for batch processing
    - Use DynamoDB Streams for real-time updates
    """)

    print("\n" + "=" * 100)
    print("FILES GENERATED")
    print("=" * 100)
    print(f"\nEvent-based (for maintenance analysis):")
    print(f"  CSV:  {OUTPUT_EVENTS_CSV}")
    print(f"  JSONL: {OUTPUT_EVENTS_JSONL}")
    print(f"  Records: {len(event_csv_data)}")

    print(f"\nDaily (for real-time monitoring):")
    print(f"  CSV:  {OUTPUT_DAILY_CSV}")
    print(f"  JSONL: {OUTPUT_DAILY_JSONL}")
    print(f"  Records: {len(daily_csv_data)}")

    print(f"\n✓ All files ready for DynamoDB import!")


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    main()
