#!/usr/bin/env python3
"""
将daily speed loss数据转换为DynamoDB导入格式（JSON Lines）
"""
import pandas as pd
import json
from datetime import datetime, timedelta

INPUT_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\daily_speedloss.csv"
OUTPUT_JSON_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\daily_speedloss_dynamodb.jsonl"
OUTPUT_CSV_PATH = r"C:\Users\KIRALI~1\AppData\Local\Temp\daily_speedloss_dynamodb.csv"

# 假设day 0 = 2020-01-01（可以根据实际调整）
BASE_DATE = datetime(2020, 1, 1)


def day_to_date(day_number):
    """将day编号转换为日期"""
    try:
        return BASE_DATE + timedelta(days=float(day_number))
    except:
        return BASE_DATE


def main():
    print("Loading daily speed loss data...")
    df = pd.read_csv(INPUT_PATH)

    print("Converting to DynamoDB format...")

    # JSON Lines格式（用于DynamoDB导入）
    json_records = []

    # CSV格式（备用，用于Excel或其他工具）
    csv_records = []

    for _, row in df.iterrows():
        ship = str(row['ship'])
        day = float(row['day'])
        date = day_to_date(day)

        # DynamoDB格式
        pk = f"SHIP#{ship}"
        sk = f"DAY#{int(day):06d}"

        dynamodb_item = {
            "PK": {"S": pk},
            "SK": {"S": sk},
            "day": {"N": str(day)},
            "ship": {"S": ship},
            "date": {"S": date.isoformat()},
            "stw_raw": {"N": str(row['stw_raw'])},
            "stw_corrected": {"N": str(row['stw_corrected'])},
            "baseline_stw": {"N": str(row['baseline_stw'])},
            "speed_loss_pct": {"N": str(row['speed_loss_pct'])},
            "timestamp": {"N": str(int(date.timestamp()))},
        }

        json_records.append(dynamodb_item)

        # CSV格式（用于参考）
        csv_records.append({
            "PK": pk,
            "SK": sk,
            "day": day,
            "ship": ship,
            "date": date.isoformat(),
            "stw_raw": row['stw_raw'],
            "stw_corrected": row['stw_corrected'],
            "baseline_stw": row['baseline_stw'],
            "speed_loss_pct": row['speed_loss_pct'],
            "timestamp": int(date.timestamp()),
        })

    # 写JSON Lines
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        for item in json_records:
            f.write(json.dumps(item) + '\n')

    print(f"Saved JSON Lines format: {OUTPUT_JSON_PATH}")
    print(f"  Total records: {len(json_records)}")

    # 写CSV
    csv_df = pd.DataFrame(csv_records)
    csv_df.to_csv(OUTPUT_CSV_PATH, index=False, encoding='utf-8')
    print(f"Saved CSV format: {OUTPUT_CSV_PATH}")

    # 显示样例
    print("\n" + "=" * 80)
    print("SAMPLE DynamoDB JSON Item:")
    print("=" * 80)
    print(json.dumps(json_records[0], indent=2))

    print("\n" + "=" * 80)
    print("DynamoDB Query Examples:")
    print("=" * 80)
    print("\n1. Query single ship all days:")
    print(f'   PK = "{json_records[0]["PK"]["S"]}"')

    print("\n2. Query single ship specific date range:")
    print(f'   PK = "{json_records[0]["PK"]["S"]}"')
    print(f'   SK BETWEEN "DAY#000100" AND "DAY#000500"')

    print("\n3. Get latest speed loss for all ships:")
    print('   Query GSI with date DESC, limit=1 per ship')

    print("\n" + "=" * 80)
    print("Import to DynamoDB options:")
    print("=" * 80)
    print("\nOption 1 - AWS CLI (batch write):")
    print(f"  aws dynamodb batch-write-item --request-items file://{OUTPUT_JSON_PATH}")

    print("\nOption 2 - AWS Data Pipeline:")
    print(f"  Upload {OUTPUT_CSV_PATH} to S3")
    print("  Use DynamoDB Import from S3")

    print("\nOption 3 - DynamoDB Console:")
    print("  1. Go to DynamoDB console")
    print("  2. Select table ShipSpeedLoss")
    print("  3. Use PartiQL editor to insert items")


if __name__ == '__main__':
    main()
