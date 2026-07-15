"""
Speed Loss 分析報告生成工具
根據計算結果生成決策支援報告
"""

import pandas as pd
import json
from datetime import datetime
from pathlib import Path

class ReportGenerator:
    """報告生成器"""

    def __init__(self, output_dir='./speed_loss_output'):
        self.output_dir = Path(output_dir)
        self.load_data()

    def load_data(self):
        """載入所有計算結果"""
        self.stats = pd.read_csv(self.output_dir / 'fleet_statistics.csv')
        self.complete = pd.read_csv(self.output_dir / 'speed_loss_complete.csv')
        self.anomalies = pd.read_csv(self.output_dir / 'anomalies.csv')

        with open(self.output_dir / 'visualization_data.json', 'r') as f:
            self.viz_data = json.load(f)

    def generate_executive_summary(self):
        """生成執行摘要"""
        print("\n" + "="*80)
        print("陽明海運 - 船隊 Speed Loss 分析報告")
        print("="*80)
        print(f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # 概覽統計
        print("[船隊概覽統計]")
        print(f"總船數：{len(self.stats)}")
        print(f"總航日數：{self.complete.shape[0]:,}")
        print(f"分析期間：Day {self.complete['NOON_UTC'].min():.0f} - Day {self.complete['NOON_UTC'].max():.0f}")

        # 性能指標
        fleet_avg_loss = self.stats['avg_speed_loss_l1'].mean()
        best_ship = self.stats.loc[self.stats['avg_speed_loss_l1'].idxmin()]
        worst_ship = self.stats.loc[self.stats['avg_speed_loss_l1'].idxmax()]

        print(f"\n[主要效能指標]")
        print(f"船隊平均 Speed Loss (L1)：{fleet_avg_loss:.1f}%")
        print(f"最佳表現 - {best_ship['ship_id']}：{best_ship['avg_speed_loss_l1']:.1f}%")
        print(f"需關注 - {worst_ship['ship_id']}：{worst_ship['avg_speed_loss_l1']:.1f}%")

        # 異常統計
        high_loss = len(self.anomalies[self.anomalies['type'] == 'HIGH_SPEED_LOSS'])
        abnormal_foc = len(self.anomalies[self.anomalies['type'] == 'ABNORMAL_FOC'])

        print(f"\n[異常事件統計]")
        print(f"高 Speed Loss 事件：{high_loss} 次")
        print(f"異常 FOC 事件：{abnormal_foc} 次")
        print(f"總異常數：{len(self.anomalies)} 次")

    def generate_ship_rankings(self):
        """生成船舶排名"""
        print("\n" + "="*80)
        print("[單船性能排名 (按平均 Speed Loss)]")
        print("="*80)

        rankings = self.stats.sort_values('avg_speed_loss_l1')[
            ['ship_id', 'days_count', 'avg_foc', 'avg_speed_loss_l1']
        ]

        print(f"\n{'排名':<5} {'船舶':<8} {'航日數':<8} {'平均油耗':<12} {'Speed Loss':<12} {'評估':<10}")
        print("-" * 70)

        for idx, (_, row) in enumerate(rankings.iterrows(), 1):
            loss = row['avg_speed_loss_l1']
            if loss < 10:
                rating = "優秀"
            elif loss < 15:
                rating = "良好"
            elif loss < 20:
                rating = "需關注"
            else:
                rating = "緊急"

            print(f"{idx:<5} {row['ship_id']:<8} {row['days_count']:<8.0f} "
                  f"{row['avg_foc']:<12.2f} {loss:<12.1f}% {rating:<10}")

    def generate_recommendations(self):
        """生成建議"""
        print("\n" + "="*80)
        print("[決策建議]")
        print("="*80)

        # 1. 高優先級維修建議
        high_loss_ships = self.stats[self.stats['avg_speed_loss_l1'] > 18]['ship_id'].tolist()
        if high_loss_ships:
            print(f"\n[緊急] 建議安排水下檢查的船舶：")
            for ship in high_loss_ships:
                loss = self.stats[self.stats['ship_id'] == ship]['avg_speed_loss_l1'].values[0]
                print(f"  - {ship}（平均 Speed Loss：{loss:.1f}%）")

        # 2. 異常事件深入調查
        print(f"\n[中等] 需深入調查的異常事件（最新 5 件）：")
        recent_anomalies = self.anomalies.sort_values('day', ascending=False).head(5)
        for _, row in recent_anomalies.iterrows():
            print(f"  - {row['ship_id']} Day {row['day']:.0f}："
                  f" {row['type']} (嚴重級別：{row['severity']})")

        # 3. 效能最佳的船舶分析
        best_ship = self.stats.loc[self.stats['avg_speed_loss_l1'].idxmin()]
        print(f"\n[參考] 最佳實踐船舶：")
        print(f"  - {best_ship['ship_id']}（Speed Loss：{best_ship['avg_speed_loss_l1']:.1f}%）")
        print(f"    平均油耗：{best_ship['avg_foc']:.2f} MT/day")
        print(f"    建議與此船舶經營團隊溝通經驗")

        # 4. 季節性建議
        print(f"\n[預防] 季節性計劃：")
        print(f"  - 高風力季節前：提前 4-6 周安排船體清洗")
        print(f"  - 定期檢查周期：每 180-365 天進行一次 UWI")
        print(f"  - 螺旋槳保養：與檢查同步進行效果最優")

    def generate_detailed_analysis(self):
        """生成詳細分析"""
        print("\n" + "="*80)
        print("[詳細分析]")
        print("="*80)

        # 油耗範圍分析
        print(f"\n[船隊油耗分佈]")
        print(f"平均油耗：{self.complete['daily_foc'].mean():.2f} MT/day")
        print(f"最低油耗：{self.complete['daily_foc'].min():.2f} MT/day")
        print(f"最高油耗：{self.complete['daily_foc'].max():.2f} MT/day")
        print(f"標準差：{self.complete['daily_foc'].std():.2f} MT/day")

        # 環境因素分析
        print(f"\n[環境因素影響]")
        print(f"平均風力等級：{self.complete['WIND_SCALE'].mean():.2f}")
        print(f"平均對水航速：{self.complete['SPEED_THROUGH_WATER'].mean():.2f} knots")

        # 維修效益
        print(f"\n[維修效益統計]")
        maintenance_events = self.complete.dropna(subset=['maintenance_improvement_pct'])
        if len(maintenance_events) > 0:
            avg_benefit = maintenance_events['maintenance_improvement_pct'].mean()
            max_benefit = maintenance_events['maintenance_improvement_pct'].max()
            print(f"平均維修效益：{avg_benefit:.2f}%")
            print(f"最大維修效益：{max_benefit:.2f}%")
            print(f"受追蹤的維修事件：{len(maintenance_events)}")

    def export_to_html(self, filename='speed_loss_report.html'):
        """匯出為 HTML 報告"""
        html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Speed Loss 分析報告</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; border-bottom: 3px solid #667eea; }
        h2 { color: #667eea; margin-top: 30px; }
        table { border-collapse: collapse; width: 100%; margin: 15px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #667eea; color: white; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .good { color: green; font-weight: bold; }
        .warning { color: orange; font-weight: bold; }
        .critical { color: red; font-weight: bold; }
        .box { border: 1px solid #ccc; padding: 15px; margin: 10px 0; background: #f5f5f5; }
    </style>
</head>
<body>
    <h1>陽明海運 - 船隊 Speed Loss 分析報告</h1>
    <p>生成時間：""" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>

    <h2>執行摘要</h2>
    <div class="box">
        <p><strong>船隊平均 Speed Loss (L1)：</strong>
           <span class="warning">""" + f"{self.stats['avg_speed_loss_l1'].mean():.1f}%" + """</span>
        </p>
        <p><strong>異常事件數：</strong> """ + f"{len(self.anomalies)}" + """</p>
        <p><strong>分析期間：</strong> """ + f"Day {self.complete['NOON_UTC'].min():.0f} - Day {self.complete['NOON_UTC'].max():.0f}" + """</p>
    </div>

    <h2>單船性能排名</h2>
    <table>
        <tr>
            <th>排名</th>
            <th>船舶</th>
            <th>航日數</th>
            <th>平均油耗 (MT/day)</th>
            <th>Speed Loss (L1)</th>
            <th>評估</th>
        </tr>
"""

        rankings = self.stats.sort_values('avg_speed_loss_l1')
        for idx, (_, row) in enumerate(rankings.iterrows(), 1):
            loss = row['avg_speed_loss_l1']
            if loss < 10:
                rating = '<span class="good">優秀</span>'
            elif loss < 15:
                rating = '<span class="good">良好</span>'
            elif loss < 20:
                rating = '<span class="warning">需關注</span>'
            else:
                rating = '<span class="critical">緊急</span>'

            html_content += f"""
        <tr>
            <td>{idx}</td>
            <td>{row['ship_id']}</td>
            <td>{row['days_count']:.0f}</td>
            <td>{row['avg_foc']:.2f}</td>
            <td>{loss:.1f}%</td>
            <td>{rating}</td>
        </tr>
"""

        html_content += """
    </table>

    <h2>建議行動</h2>
    <div class="box">
        <h3>緊急維修</h3>
        <ul>
"""

        high_loss_ships = self.stats[self.stats['avg_speed_loss_l1'] > 18]
        for _, row in high_loss_ships.iterrows():
            html_content += f"<li>{row['ship_id']} - 平均 Speed Loss：{row['avg_speed_loss_l1']:.1f}%</li>\n"

        html_content += """
        </ul>
    </div>

</body>
</html>
"""

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"\n✓ HTML 報告已生成：{filename}")

    def run(self):
        """運行完整報告生成"""
        self.generate_executive_summary()
        self.generate_ship_rankings()
        self.generate_detailed_analysis()
        self.generate_recommendations()
        self.export_to_html()

        print("\n" + "="*80)
        print("報告生成完成")
        print("="*80)


if __name__ == '__main__':
    generator = ReportGenerator()
    generator.run()
