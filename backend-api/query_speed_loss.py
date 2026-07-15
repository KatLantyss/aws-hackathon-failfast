#!/usr/bin/env python3
"""
查询预计算的 Speed Loss 数据。

用法：
  python query_speed_loss.py S11        # 查询 S11 的最新 speed loss 数据
  python query_speed_loss.py --list     # 列出所有 vessel 的预计算时间
"""
import json
import boto3
import sys
import os
from datetime import datetime

REGION = os.getenv('AWS_REGION', 'us-east-1')
SPEED_LOSS_TABLE = 'ship-analysis-dev-speed-loss-timeline'

dynamodb = boto3.resource('dynamodb', region_name=REGION)


def list_all_vessels():
    """列出所有预计算过的 vessel。"""
    table = dynamodb.Table(SPEED_LOSS_TABLE)

    print("预计算的 Vessels:")
    print("-" * 70)
    print(f"{'Vessel':<10} {'计算时间':<25} {'FOC Records':<15} {'STW Records':<15}")
    print("-" * 70)

    try:
        response = table.scan()
        items = response.get('Items', [])

        for item in sorted(items, key=lambda x: x['vessel_id']):
            print(f"{item['vessel_id']:<10} {item.get('computed_at', 'N/A'):<25} {item.get('foc_records', 0):<15} {item.get('stw_records', 0):<15}")

        print("-" * 70)
        print(f"Total: {len(items)} vessels")
    except Exception as e:
        print(f"❌ Error: {e}")


def get_vessel_speed_loss(vessel_id: str):
    """获取单个 vessel 的 speed loss 数据。"""
    table = dynamodb.Table(SPEED_LOSS_TABLE)

    try:
        # 查询该 vessel 的所有记录，按时间排序（最新的在前）
        response = table.query(
            KeyConditionExpression='vessel_id = :vid',
            ExpressionAttributeValues={':vid': vessel_id},
            ScanIndexForward=False,  # 降序（最新的在前）
            Limit=1  # 只需要最新的
        )

        items = response.get('Items', [])
        if not items:
            print(f"❌ 未找到 {vessel_id} 的预计算数据")
            return None

        item = items[0]
        data = json.loads(item['data'])

        print(f"\n{'='*70}")
        print(f"Vessel: {vessel_id}")
        print(f"计算时间: {item['computed_at']}")
        print(f"{'='*70}")

        # 显示摘要
        print(f"\n📊 摘要:")
        print(f"  FOC Timeline: {len(data['foc_timeline'])} 条记录")
        print(f"  STW Timeline: {len(data['stw_timeline'])} 条记录")

        # FOC 摘要
        foc_summary = data.get('foc_summary', {})
        print(f"\n📈 FOC-based Speed Loss (主指标):")
        print(f"  平均日耗油量: {foc_summary.get('avg_daily_foc_vlsfo')} MT/day")
        print(f"  平均 Speed Loss: {foc_summary.get('avg_speed_loss_pct')}%")
        print(f"  有效记录: {foc_summary.get('valid_records')}")

        # STW 摘要
        stw_summary = data.get('stw_summary', {})
        print(f"\n📉 STW-based Speed Loss (ISO 19030 验证):")
        print(f"  平均 Speed Loss: {stw_summary.get('avg_speed_loss_pct')}%")
        print(f"  有效记录: {stw_summary.get('valid_records')}")

        # 维修周期
        print(f"\n🔧 维修周期: {len(data['maintenance_cycles'])} 个")
        for cyc in data['maintenance_cycles'][:3]:  # 只显示前 3 个
            print(f"  Cycle {cyc['cycle_index']}: Day {cyc['start_day']}-{cyc['end_day']} ({cyc['records']} records)")

        # FOC Timeline 样本
        print(f"\n📋 FOC Timeline 样本 (前 5 条):")
        print(f"{'Day':<8} {'RPM':<8} {'FOC':<10} {'Baseline':<10} {'Speed Loss %':<15}")
        print("-" * 55)
        for point in data['foc_timeline'][:5]:
            print(f"{point['noon_day']:<8.0f} {point.get('rpm', '-'):<8} {point.get('daily_foc_vlsfo', '-'):<10} {point.get('baseline_foc', '-'):<10} {point.get('speed_loss_pct', '-'):<15}")

        print(f"\n✅ 完整数据已保存到本地（JSON 格式）")

        # 保存到文件
        output_file = f"speed_loss_{vessel_id}.json"
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"   文件: {output_file}")

        return data

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("用法: python query_speed_loss.py [vessel_id|--list]")
        print("\n例子:")
        print("  python query_speed_loss.py S11        # 查询 S11")
        print("  python query_speed_loss.py --list     # 列出所有")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == '--list':
        list_all_vessels()
    else:
        get_vessel_speed_loss(arg.upper())


if __name__ == '__main__':
    main()
