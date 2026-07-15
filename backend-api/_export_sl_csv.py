"""Export speed loss for all ships to CSV for review"""
import handler, json, csv, statistics

ships = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12','S21','S22','S23']

# 1. Summary CSV
with open('speed_loss_summary.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['ship', 'model_r2', 'train_n', 'total_records', 'valid_records',
                'avg_sl_pct', 'median_sl', 'p10', 'p25', 'p75', 'p90', 'max_sl',
                'zeros_pct', 'negative_pct', 'cycles'])
    
    for s in ships:
        r = handler.route({'httpMethod':'GET','path':f'/api/v1/vessels/{s}/speed-loss','queryStringParameters':{},'body':None}, None)
        body = json.loads(r['body'])
        mi = body.get('model_info', {})
        vals = [p['speed_loss_pct'] for p in body.get('foc_timeline', [])]
        if not vals:
            continue
        sv = sorted(vals)
        n = len(vals)
        w.writerow([
            s, mi.get('r2_score'), mi.get('training_samples'),
            body['foc_summary']['total_records'], n,
            f"{statistics.mean(vals):.2f}", f"{statistics.median(vals):.2f}",
            f"{sv[int(n*0.1)]:.2f}", f"{sv[int(n*0.25)]:.2f}",
            f"{sv[int(n*0.75)]:.2f}", f"{sv[int(n*0.9)]:.2f}", f"{max(vals):.2f}",
            f"{sum(1 for v in vals if v==0)/n*100:.1f}",
            f"{sum(1 for v in vals if v<0)/n*100:.1f}",
            len(body['maintenance_cycles'])
        ])

print("Written: speed_loss_summary.csv")

# 2. Full timeline CSV (all ships, all points)
with open('speed_loss_timeline.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['ship', 'noon_day', 'voyage', 'rpm', 'stw', 'daily_foc_vlsfo',
                'expected_foc', 'speed_loss_pct', 'fuel_type', 'hours_full_speed',
                'wind_scale', 'cargo_on_board', 'load_condition', 'maintenance_cycle'])
    
    for s in ships:
        r = handler.route({'httpMethod':'GET','path':f'/api/v1/vessels/{s}/speed-loss','queryStringParameters':{},'body':None}, None)
        body = json.loads(r['body'])
        for p in body.get('foc_timeline', []):
            w.writerow([
                s, p['noon_day'], p['voyage'], p['rpm'], p['stw'],
                p['daily_foc_vlsfo'], p['baseline_foc'], p['speed_loss_pct'],
                p['fuel_type'], p['hours_full_speed'], p['wind_scale'],
                p['cargo_on_board'], p['load_condition'], p['maintenance_cycle']
            ])

print("Written: speed_loss_timeline.csv")

# 3. Maintenance events with before/after (including RPM analysis)
with open('speed_loss_maintenance_impact.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['ship', 'event_day', 'event_type', 'sl_before_30d', 'sl_after_30d',
                'sl_drop', 'foc_before_30d', 'foc_after_30d', 'foc_drop_pct',
                'rpm_before_avg', 'rpm_after_avg', 'rpm_normalized_foc_drop_pct',
                'n_before', 'n_after'])

    for s in ships:
        r = handler.route({'httpMethod':'GET','path':f'/api/v1/vessels/{s}/speed-loss','queryStringParameters':{},'body':None}, None)
        body = json.loads(r['body'])
        foc_tl = body.get('foc_timeline', [])

        r2 = handler.route({'httpMethod':'GET','path':f'/api/v1/vessels/{s}/maintenance-events','queryStringParameters':{},'body':None}, None)
        maint = json.loads(r2['body']).get('events', [])

        for evt in maint:
            day = evt['event_day']
            etype = evt['event_type']
            before = [p for p in foc_tl if day - 30 <= p['noon_day'] < day]
            after = [p for p in foc_tl if day < p['noon_day'] <= day + 30]

            sl_b = statistics.mean([p['speed_loss_pct'] for p in before]) if before else None
            sl_a = statistics.mean([p['speed_loss_pct'] for p in after]) if after else None
            foc_b = statistics.mean([p['daily_foc_vlsfo'] for p in before]) if before else None
            foc_a = statistics.mean([p['daily_foc_vlsfo'] for p in after]) if after else None

            # RPM 分析
            rpm_b = statistics.mean([p['rpm'] for p in before if p.get('rpm')]) if before else None
            rpm_a = statistics.mean([p['rpm'] for p in after if p.get('rpm')]) if after else None

            # RPM 正規化的油耗改善：在相同 RPM 範圍內的改善
            rpm_normalized_drop = None
            if before and after and rpm_b is not None and rpm_a is not None:
                # 尋找 before 中最接近 rpm_a 的 RPM 範圍
                rpm_target = rpm_a
                rpm_tolerance = 5  # ±5 RPM
                before_in_range = [p for p in before if abs(p['rpm'] - rpm_target) <= rpm_tolerance and p.get('rpm')]
                after_in_range = [p for p in after if abs(p['rpm'] - rpm_target) <= rpm_tolerance and p.get('rpm')]

                if before_in_range and after_in_range:
                    foc_b_normalized = statistics.mean([p['daily_foc_vlsfo'] for p in before_in_range])
                    foc_a_normalized = statistics.mean([p['daily_foc_vlsfo'] for p in after_in_range])
                    if foc_b_normalized > 0:
                        rpm_normalized_drop = (foc_b_normalized - foc_a_normalized) / foc_b_normalized * 100

            sl_drop = f"{sl_b - sl_a:.2f}" if sl_b is not None and sl_a is not None else ""
            foc_drop = f"{(foc_b - foc_a)/foc_b*100:.2f}" if foc_b and foc_a and foc_b > 0 else ""

            w.writerow([
                s, day, etype,
                f"{sl_b:.2f}" if sl_b is not None else "",
                f"{sl_a:.2f}" if sl_a is not None else "",
                sl_drop,
                f"{foc_b:.2f}" if foc_b is not None else "",
                f"{foc_a:.2f}" if foc_a is not None else "",
                foc_drop,
                f"{rpm_b:.1f}" if rpm_b is not None else "",
                f"{rpm_a:.1f}" if rpm_a is not None else "",
                f"{rpm_normalized_drop:.2f}" if rpm_normalized_drop is not None else "",
                len(before), len(after)
            ])

print("Written: speed_loss_maintenance_impact.csv")
print("\nDone! Review these 3 files.")
