"""Deep review of speed loss calculation - why so many zeros? Is sawtooth visible?"""
import handler, json, statistics

# Test S4 which should have clear sawtooth (5 maintenance events)
for ship in ['S4', 'S11', 'S1']:
    r = handler.route({'httpMethod': 'GET', 'path': f'/api/v1/vessels/{ship}/speed-loss', 'queryStringParameters': {}, 'body': None}, None)
    body = json.loads(r['body'])
    foc_tl = body['foc_timeline']
    cycles = body['maintenance_cycles']
    
    print(f"\n{'='*60}")
    print(f"Ship {ship}: {len(foc_tl)} records, {len(cycles)} cycles")
    print(f"Model R2: {body['model_info']['r2_score']}")
    
    vals = [p['speed_loss_pct'] for p in foc_tl]
    zeros = sum(1 for v in vals if v == 0)
    print(f"Speed Loss: mean={statistics.mean(vals):.2f}% median={statistics.median(vals):.2f}% zeros={zeros} ({zeros/len(vals)*100:.0f}%)")
    
    # Look at the distribution more carefully
    print(f"  P10={sorted(vals)[int(len(vals)*0.1)]:.1f}% P25={sorted(vals)[int(len(vals)*0.25)]:.1f}% P50={sorted(vals)[int(len(vals)*0.5)]:.1f}% P75={sorted(vals)[int(len(vals)*0.75)]:.1f}% P90={sorted(vals)[int(len(vals)*0.9)]:.1f}%")
    
    # Check: are the zeros because actual < expected (model overpredicts)?
    under_predicted = [(p['daily_foc_vlsfo'], p['baseline_foc'], p['daily_foc_vlsfo'] - p['baseline_foc']) 
                       for p in foc_tl if p['speed_loss_pct'] == 0]
    if under_predicted:
        deltas = [d[2] for d in under_predicted]
        print(f"  Zero-SL records: actual_foc vs expected_foc delta: mean={statistics.mean(deltas):.2f}, min={min(deltas):.2f}, max={max(deltas):.2f}")
        # Show a few examples
        print(f"  Examples (actual, expected, delta):")
        for a, e, d in under_predicted[:5]:
            print(f"    actual={a:.1f} expected={e:.1f} delta={d:.1f}")
    
    # Check sawtooth: look at speed loss by maintenance cycle
    print(f"\n  Per-cycle breakdown:")
    for cyc in cycles:
        ci = cyc['cycle_index']
        cyc_vals = [p['speed_loss_pct'] for p in foc_tl if p['maintenance_cycle'] == ci]
        if not cyc_vals:
            print(f"    Cycle {ci}: no data")
            continue
        # First 10 vs last 10
        first10 = cyc_vals[:10]
        last10 = cyc_vals[-10:]
        print(f"    Cycle {ci} ({cyc['trigger_event'] or 'initial'}): n={len(cyc_vals)} "
              f"first10_avg={statistics.mean(first10):.1f}% last10_avg={statistics.mean(last10):.1f}% "
              f"mean={statistics.mean(cyc_vals):.1f}% max={max(cyc_vals):.1f}%")
    
    # Show timeline segments around maintenance events
    r2 = handler.route({'httpMethod': 'GET', 'path': f'/api/v1/vessels/{ship}/maintenance-events', 'queryStringParameters': {}, 'body': None}, None)
    maint = json.loads(r2['body'])['events']
    print(f"\n  Around maintenance events (30d before → 30d after):")
    for evt in maint:
        day = evt['event_day']
        etype = evt['event_type']
        before = [p['speed_loss_pct'] for p in foc_tl if day - 30 <= p['noon_day'] < day]
        after = [p['speed_loss_pct'] for p in foc_tl if day < p['noon_day'] <= day + 30]
        before_foc = [p['daily_foc_vlsfo'] for p in foc_tl if day - 30 <= p['noon_day'] < day]
        after_foc = [p['daily_foc_vlsfo'] for p in foc_tl if day < p['noon_day'] <= day + 30]
        
        sl_b = f"{statistics.mean(before):.1f}%" if before else "n/a"
        sl_a = f"{statistics.mean(after):.1f}%" if after else "n/a"
        foc_b = f"{statistics.mean(before_foc):.1f}" if before_foc else "n/a"
        foc_a = f"{statistics.mean(after_foc):.1f}" if after_foc else "n/a"
        print(f"    Day {day:.0f} {etype:<8}: SL {sl_b} → {sl_a} | FOC {foc_b} → {foc_a} MT/d (n={len(before)}/{len(after)})")
