"""
Ship Performance Analysis API
Lambda handler - reads directly from DynamoDB
"""
import json
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal
from statistics import mean, stdev
import math

# ── DynamoDB setup ──────────────────────────────────────────────────────────
REGION          = os.environ.get('AWS_REGION', 'us-east-1')
VESSEL_TABLE    = os.environ.get('VESSEL_TABLE',  'ship-analysis-dev-vessel-data')
MAINT_TABLE     = os.environ.get('MAINT_TABLE',   'ship-analysis-dev-maintenance-events')

ddb = boto3.resource('dynamodb', region_name=REGION)
vessel_tbl = ddb.Table(VESSEL_TABLE)
maint_tbl  = ddb.Table(MAINT_TABLE)


# ── helpers ──────────────────────────────────────────────────────────────────
def decimal_to_float(obj):
    """JSON serializer that converts Decimal → float"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f'Not serializable: {type(obj)}')


def resp(status: int, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        },
        'body': json.dumps(body, default=decimal_to_float),
    }


def err(status: int, msg: str):
    return resp(status, {'error': msg})


def query_vessel(vessel_id: str, limit=None):
    """Query all rows for a vessel, sorted by sort_key (NOON_UTC#idx)"""
    kwargs = dict(
        KeyConditionExpression=Key('vessel_id').eq(vessel_id),
        ScanIndexForward=True,
    )
    if limit:
        kwargs['Limit'] = limit

    items = []
    while True:
        r = vessel_tbl.query(**kwargs)
        items.extend(r.get('Items', []))
        if 'LastEvaluatedKey' not in r:
            break
        if limit and len(items) >= limit:
            break
        kwargs['ExclusiveStartKey'] = r['LastEvaluatedKey']
    return items


def query_maintenance(vessel_id: str):
    kwargs = dict(KeyConditionExpression=Key('vessel_id').eq(vessel_id))
    items = []
    while True:
        r = maint_tbl.query(**kwargs)
        items.extend(r.get('Items', []))
        if 'LastEvaluatedKey' not in r:
            break
        kwargs['ExclusiveStartKey'] = r['LastEvaluatedKey']
    return items


def safe_float(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ── Route table ──────────────────────────────────────────────────────────────
def route(event, context):
    method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path   = event.get('path') or event.get('rawPath', '/')

    # OPTIONS preflight
    if method == 'OPTIONS':
        return resp(200, {})

    # /health
    if path == '/health':
        return resp(200, {'status': 'ok', 'vessel_table': VESSEL_TABLE, 'maint_table': MAINT_TABLE})

    # /api/v1/vessels
    if path == '/api/v1/vessels' and method == 'GET':
        return get_vessels(event)

    # /api/v1/vessels/{id}
    if path.startswith('/api/v1/vessels/'):
        parts = path.strip('/').split('/')            # ['api','v1','vessels','{id}',...]
        vessel_id = parts[3] if len(parts) > 3 else None
        if not vessel_id:
            return err(400, 'missing vessel_id')

        sub = parts[4] if len(parts) > 4 else None

        if sub is None and method == 'GET':
            return get_vessel_detail(vessel_id, event)
        if sub == 'noon-reports':
            return get_noon_reports(vessel_id, event)
        if sub == 'speed-loss':
            return get_speed_loss(vessel_id, event)
        if sub == 'speed-loss-attribution':
            return get_speed_loss_attribution(vessel_id, event)
        if sub == 'maintenance-events':
            return get_maintenance_events(vessel_id, event)
        if sub == 'maintenance-recommendation':
            return get_maintenance_recommendation(vessel_id, event)

    # /api/v1/fleet/ranking
    if path == '/api/v1/fleet/ranking':
        return get_fleet_ranking(event)

    # /api/v1/predict/fuel-consumption
    if path == '/api/v1/predict/fuel-consumption' and method == 'POST':
        return predict_fuel(event)

    return err(404, f'Not found: {method} {path}')


# ── Handlers ─────────────────────────────────────────────────────────────────

def get_vessels(event):
    """List all unique vessel IDs"""
    KNOWN_VESSELS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12',
                     'S21','S22','S23']
    TRAIN_VESSELS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12']
    PRED_VESSELS  = ['S21','S22','S23']
    vessels = [
        {
            'vessel_id': v,
            'type': 'training' if v in TRAIN_VESSELS else 'prediction',
        }
        for v in KNOWN_VESSELS
    ]
    return resp(200, {'vessels': vessels, 'total': len(vessels)})


def get_vessel_detail(vessel_id, event):
    """Summary stats for one vessel"""
    rows = query_vessel(vessel_id)
    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    speeds   = [safe_float(r.get('AVG_SPEED'))          for r in rows if r.get('AVG_SPEED')]
    consump  = [safe_float(r.get('ME_CONSUMPTION'))      for r in rows if r.get('ME_CONSUMPTION')]
    stw_list = [safe_float(r.get('SPEED_THROUGH_WATER')) for r in rows if r.get('SPEED_THROUGH_WATER')]

    return resp(200, {
        'vessel_id':       vessel_id,
        'total_records':   len(rows),
        'avg_speed_kn':    round(mean(speeds), 2)   if speeds   else None,
        'avg_consumption': round(mean(consump), 2)  if consump  else None,
        'avg_stw_kn':      round(mean(stw_list), 2) if stw_list else None,
        'voyage_range':    {
            'min': int(min(safe_float(r['VOYAGE'], 0) for r in rows)),
            'max': int(max(safe_float(r['VOYAGE'], 0) for r in rows)),
        },
    })


def get_noon_reports(vessel_id, event):
    """Return noon reports (paginated via query params limit/voyage)"""
    qs      = event.get('queryStringParameters') or {}
    limit   = int(qs.get('limit', 100))
    voyage  = qs.get('voyage')

    rows = query_vessel(vessel_id)
    if voyage:
        rows = [r for r in rows if str(safe_float(r.get('VOYAGE'), '')) == voyage]

    # Trim to limit
    rows = rows[:limit]

    records = []
    for r in rows:
        records.append({
            'vessel_id':           r['vessel_id'],
            'noon_day':            safe_float(r.get('NOON_UTC')),
            'voyage':              safe_float(r.get('VOYAGE')),
            'avg_speed_kn':        safe_float(r.get('AVG_SPEED')),
            'speed_through_water': safe_float(r.get('SPEED_THROUGH_WATER')),
            'me_rpm':              safe_float(r.get('ME_AVG_RPM')),
            'fore_draft':          safe_float(r.get('FORE_DRAFT')),
            'aft_draft':           safe_float(r.get('AFTER_DRAFT')),
            'cargo_on_board':      safe_float(r.get('CARGO_ON_BOARD')),
            'wind_scale':          safe_float(r.get('WIND_SCALE')),
            'sea_height':          safe_float(r.get('SEA_HEIGHT')),
            'horse_power':         safe_float(r.get('HORSE_POWER')),
            'me_consumption':      safe_float(r.get('ME_CONSUMPTION')),
            'total_consump':       safe_float(r.get('TOTAL_CONSUMP')),
            'sfoc':                safe_float(r.get('SFOC')),
            'me_slip':             safe_float(r.get('ME_SLIP')),
        })

    return resp(200, {
        'vessel_id': vessel_id,
        'count':     len(records),
        'records':   records,
    })


def get_speed_loss(vessel_id, event):
    """
    Speed Loss 基於 ISO 19030 框架，使用 FULL_SPD_STW_SLIP。
    FULL_SPD_STW_SLIP = 全速航行時段的螺旋槳對水滑差(%)，數值越高代表推進效能越差。
    有效範圍：0–30%（排除異常值）

    同時計算 ISO 19030-style speed loss：
    以 calm condition (WIND≤3, HOURS_FULL_SPEED≥22) 的前 baseline 期 STW vs RPM 作為基準，
    每筆資料在相同 RPM bin 下比較實際 STW，差值即 speed loss (kn)。
    """
    rows = query_vessel(vessel_id)
    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    # ── Step 1: FULL_SPD_STW_SLIP 趨勢（主指標）──────────────────────────
    slip_timeline = []
    for r in rows:
        slip = safe_float(r.get('FULL_SPD_STW_SLIP'))
        if slip is None or slip < 0 or slip > 30:
            continue
        slip_timeline.append({
            'noon_day':   safe_float(r.get('NOON_UTC')),
            'voyage':     safe_float(r.get('VOYAGE')),
            'slip_pct':   round(slip, 2),
            'wind_scale': safe_float(r.get('WIND_SCALE')),
            'hours_full_speed': safe_float(r.get('HOURS_FULL_SPEED')),
        })
    slip_timeline.sort(key=lambda x: x['noon_day'] or 0)

    avg_slip = round(mean([t['slip_pct'] for t in slip_timeline]), 2) if slip_timeline else None

    # ── Step 2: ISO 19030-style — RPM-bucket baseline ────────────────────
    # calm condition: WIND≤3, HOURS_FULL_SPEED≥22
    calm = [r for r in rows
            if safe_float(r.get('WIND_SCALE'), 99) <= 3
            and safe_float(r.get('HOURS_FULL_SPEED'), 0) >= 22
            and r.get('ME_AVG_RPM') and r.get('SPEED_THROUGH_WATER')]

    # baseline = first 10% of calm records (earliest days = cleanest hull)
    calm_sorted = sorted(calm, key=lambda x: safe_float(x.get('NOON_UTC'), 0))
    baseline_n  = max(5, len(calm_sorted) // 10)
    baseline    = calm_sorted[:baseline_n]

    # build RPM → STW lookup (5-RPM bins)
    rpm_stw = {}
    for r in baseline:
        rpm = safe_float(r.get('ME_AVG_RPM'))
        stw = safe_float(r.get('SPEED_THROUGH_WATER'))
        if rpm and stw:
            bucket = int(rpm // 5) * 5  # e.g. 67 → 65
            if bucket not in rpm_stw:
                rpm_stw[bucket] = []
            rpm_stw[bucket].append(stw)
    rpm_baseline = {k: round(mean(v), 3) for k, v in rpm_stw.items()}

    # calculate speed loss per calm record
    iso_timeline = []
    for r in calm_sorted:
        rpm = safe_float(r.get('ME_AVG_RPM'))
        stw = safe_float(r.get('SPEED_THROUGH_WATER'))
        if not rpm or not stw:
            continue
        bucket = int(rpm // 5) * 5
        ref = rpm_baseline.get(bucket)
        if ref is None:
            # find nearest bucket
            buckets = list(rpm_baseline.keys())
            if not buckets:
                continue
            bucket = min(buckets, key=lambda b: abs(b - bucket))
            ref = rpm_baseline[bucket]
        iso_timeline.append({
            'noon_day':    safe_float(r.get('NOON_UTC')),
            'voyage':      safe_float(r.get('VOYAGE')),
            'rpm':         round(rpm, 1),
            'stw':         round(stw, 2),
            'ref_stw':     ref,
            'speed_loss_kn': round(ref - stw, 3),
            'wind_scale':  safe_float(r.get('WIND_SCALE')),
        })

    avg_iso_loss = round(mean([t['speed_loss_kn'] for t in iso_timeline]), 3) if iso_timeline else None

    return resp(200, {
        'vessel_id': vessel_id,
        'method': 'FULL_SPD_STW_SLIP + ISO19030-RPM-baseline',
        # FULL_SPD_STW_SLIP 趨勢（所有有效資料）
        'slip_summary': {
            'avg_slip_pct':    avg_slip,
            'valid_records':   len(slip_timeline),
            'total_records':   len(rows),
        },
        'slip_timeline': slip_timeline,
        # ISO 19030-style speed loss（calm condition only）
        'iso_summary': {
            'avg_speed_loss_kn': avg_iso_loss,
            'baseline_records':  len(baseline),
            'calm_records':      len(calm_sorted),
            'rpm_baseline':      rpm_baseline,
        },
        'iso_timeline': iso_timeline,
    })


def get_speed_loss_attribution(vessel_id, event):
    """
    Speed Loss 歸因分析：基於養護事件前後 FULL_SPD_STW_SLIP 的實際差值。

    邏輯：
    - DD (乾塢) → hull + propeller 同時恢復
    - UWC / UWC+PP → hull cleaning 效果
    - PP / UWI+PP  → propeller polishing 效果
    - UWI          → 純檢查，理論上無改善（用來驗證模型）
    - weather      → DIFF_STW_SOG_SLIP（洋流/天候代理）

    每個事件計算前後 30 天的 avg slip 差值，正值 = 改善（slip 下降）。
    """
    rows  = query_vessel(vessel_id)
    maint = query_maintenance(vessel_id)

    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    # 有效 slip 資料（0–30%）
    slip_map = {}  # noon_day → slip_pct
    for r in rows:
        slip = safe_float(r.get('FULL_SPD_STW_SLIP'))
        day  = safe_float(r.get('NOON_UTC'))
        if slip is not None and 0 <= slip <= 30 and day is not None:
            slip_map[day] = slip

    def avg_slip_in_window(start, end):
        vals = [v for d, v in slip_map.items() if start <= d <= end]
        return round(mean(vals), 2) if len(vals) >= 3 else None

    # 養護事件歸因
    WINDOW = 30
    event_attributions = []
    for m in sorted(maint, key=lambda x: safe_float(x.get('event_day'), 0)):
        day   = safe_float(m.get('event_day'), 0)
        etype = str(m.get('event_type', ''))

        before = avg_slip_in_window(day - WINDOW, day)
        after  = avg_slip_in_window(day, day + WINDOW)

        if before is None or after is None:
            delta = None
            physical = False
        else:
            delta    = round(before - after, 2)   # 正值 = 改善（slip 降低）
            physical = 'UWI' not in etype or 'PP' in etype or 'UWC' in etype or 'DD' in etype

        # 歸因分類
        if 'DD' in etype:
            category = 'hull+propeller'
        elif 'UWC' in etype and 'PP' in etype:
            category = 'hull+propeller'
        elif 'UWC' in etype:
            category = 'hull'
        elif 'PP' in etype:
            category = 'propeller'
        elif etype == 'UWI':
            category = 'inspection_only'  # 不應有改善
        else:
            category = 'other'

        event_attributions.append({
            'event_type':     etype,
            'event_day':      day,
            'category':       category,
            'physical_intervention': physical,
            'slip_before_pct': before,
            'slip_after_pct':  after,
            'slip_delta_pct':  delta,   # 正值 = 改善
            'notes': (
                'No physical intervention expected' if etype == 'UWI'
                else f'Expected improvement: {delta:+.2f}%' if delta is not None
                else 'Insufficient data'
            ),
        })

    # 全時間軸：DIFF_STW_SOG_SLIP 代表洋流/天候影響
    weather_timeline = []
    for r in sorted(rows, key=lambda x: safe_float(x.get('NOON_UTC'), 0)):
        diff = safe_float(r.get('DIFF_STW_SOG_SLIP'))
        day  = safe_float(r.get('NOON_UTC'))
        if diff is not None and -15 <= diff <= 15 and day is not None:
            weather_timeline.append({
                'noon_day':      day,
                'diff_stw_sog':  round(diff, 3),  # + = STW > SOG (尾流/洋流順), - = STW < SOG (逆流)
            })

    # 彙總：各類別的平均改善量
    categories = {}
    for e in event_attributions:
        cat = e['category']
        if e['slip_delta_pct'] is not None and e['physical_intervention']:
            categories.setdefault(cat, []).append(e['slip_delta_pct'])
    summary = {cat: round(mean(vals), 2) for cat, vals in categories.items()}

    return resp(200, {
        'vessel_id':   vessel_id,
        'method':      'maintenance_event_before_after_slip_delta',
        'summary':     summary,
        'event_attributions': event_attributions,
        'weather_timeline': weather_timeline[:200],  # 限制回傳量
    })


def get_maintenance_events(vessel_id, event):
    rows = query_maintenance(vessel_id)
    events = [
        {
            'vessel_id':              r['vessel_id'],
            'event_day':              safe_float(r.get('event_day')),
            'event_type':             r.get('event_type'),
            'propeller_condition':    r.get('propeller_condition'),
            'hull_fouling_type':      r.get('hull_fouling_type'),
            'hull_coating_condition': r.get('hull_coating_condition'),
            'cavitation_found':       r.get('cavitation_found'),
            'draft_fwd_m':            safe_float(r.get('draft_fwd_m')),
            'draft_aft_m':            safe_float(r.get('draft_aft_m')),
        }
        for r in sorted(rows, key=lambda x: safe_float(x.get('event_day'), 0))
    ]
    return resp(200, {'vessel_id': vessel_id, 'events': events, 'total': len(events)})


def get_maintenance_recommendation(vessel_id, event):
    """Recommend next maintenance based on speed loss trend"""
    rows  = query_vessel(vessel_id)
    maint = query_maintenance(vessel_id)

    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    # Last 90 days of data (last 90 noon_day records)
    recent = sorted(rows, key=lambda x: safe_float(x.get('NOON_UTC'), 0))[-90:]
    slips  = [safe_float(r.get('ME_SLIP')) for r in recent if r.get('ME_SLIP')]
    avg_slip = round(mean(slips), 2) if slips else None

    # Last maintenance
    all_maint = sorted(maint, key=lambda x: safe_float(x.get('event_day'), 0))
    last_m    = all_maint[-1] if all_maint else None
    last_day  = safe_float(last_m.get('event_day'), 0) if last_m else 0
    latest_day = safe_float(recent[-1].get('NOON_UTC'), 0) if recent else 0
    days_since = latest_day - last_day

    # Simple rule: recommend if slip > 10% or days since last > 365
    urgent = (avg_slip and avg_slip > 10) or days_since > 365

    return resp(200, {
        'vessel_id':              vessel_id,
        'days_since_maintenance': round(days_since),
        'avg_me_slip_pct':        avg_slip,
        'recommendation':         'URGENT' if urgent else 'ROUTINE',
        'recommended_type':       'DD' if days_since > 730 else 'UWC',
        'reason':                 (
            'High ME slip indicates hull/propeller fouling' if avg_slip and avg_slip > 10
            else f'Scheduled maintenance due ({round(days_since)} days since last event)'
        ),
        'last_maintenance': {
            'event_type': last_m.get('event_type') if last_m else None,
            'event_day':  last_day,
        },
    })


def get_fleet_ranking(event):
    """Rank all training vessels by avg FULL_SPD_STW_SLIP (lower = better performance)"""
    TRAIN_VESSELS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12']
    rankings = []

    for vid in TRAIN_VESSELS:
        rows = query_vessel(vid)

        # FULL_SPD_STW_SLIP: 有效範圍 0-30%
        slip_list = [safe_float(r.get('FULL_SPD_STW_SLIP')) for r in rows
                     if safe_float(r.get('FULL_SPD_STW_SLIP')) is not None
                     and 0 <= safe_float(r.get('FULL_SPD_STW_SLIP'), -1) <= 30]
        cons_list = [safe_float(r.get('ME_CONSUMPTION')) for r in rows if r.get('ME_CONSUMPTION')]

        # latest 90-day trend vs full-period avg
        slip_sorted = sorted(
            [(safe_float(r.get('NOON_UTC'), 0), safe_float(r.get('FULL_SPD_STW_SLIP')))
             for r in rows
             if safe_float(r.get('FULL_SPD_STW_SLIP')) is not None
             and 0 <= safe_float(r.get('FULL_SPD_STW_SLIP'), -1) <= 30],
            key=lambda x: x[0]
        )
        recent_slip = [v for _, v in slip_sorted[-90:]] if len(slip_sorted) >= 10 else []
        trend = round(mean(recent_slip) - mean(slip_list), 2) if recent_slip and slip_list else None

        rankings.append({
            'vessel_id':          vid,
            'avg_slip_pct':       round(mean(slip_list), 2) if slip_list else None,
            'recent_90d_slip_pct': round(mean(recent_slip), 2) if recent_slip else None,
            'slip_trend':         trend,   # + = 近期惡化, - = 近期改善
            'avg_consumption_mt': round(mean(cons_list), 2) if cons_list else None,
            'valid_slip_records': len(slip_list),
            'total_records':      len(rows),
        })

    # 排名：avg_slip_pct 越低越好
    rankings.sort(key=lambda x: x['avg_slip_pct'] if x['avg_slip_pct'] is not None else 99)
    for i, r in enumerate(rankings):
        r['rank'] = i + 1

    return resp(200, {'fleet_ranking': rankings, 'total': len(rankings)})


def predict_fuel(event):
    """
    Simple fuel consumption prediction using linear model from training data
    POST body: { vessel_id, speed_kn, draft_fwd, draft_aft, cargo_on_board, wind_scale, sea_height }
    """
    try:
        body = json.loads(event.get('body') or '{}')
    except Exception:
        return err(400, 'Invalid JSON body')

    vessel_id    = body.get('vessel_id', 'S1')
    speed        = float(body.get('speed_kn', 15))
    draft_fwd    = float(body.get('draft_fwd', 14))
    draft_aft    = float(body.get('draft_aft', 14))
    cargo        = float(body.get('cargo_on_board', 80000))
    wind_scale   = float(body.get('wind_scale', 3))
    sea_height   = float(body.get('sea_height', 1.0))

    # Load training data for this vessel (or all training vessels)
    rows = query_vessel(vessel_id)
    if not rows:
        rows = query_vessel('S1')  # fallback

    # Fit simple linear: consumption ~ alpha * speed^3 + beta * cargo + gamma
    # Cubic speed relationship is standard naval architecture
    pairs = []
    for r in rows:
        c = safe_float(r.get('ME_CONSUMPTION'))
        s = safe_float(r.get('SPEED_THROUGH_WATER'))
        if c and s and c > 0:
            pairs.append((s, c))

    if len(pairs) < 10:
        return err(500, f'Not enough data for vessel {vessel_id}')

    # Least-squares fit: c = a * s^3
    s3_list = [p[0]**3 for p in pairs]
    c_list  = [p[1] for p in pairs]
    # a = sum(s3*c) / sum(s3^2)
    a = sum(x*y for x,y in zip(s3_list, c_list)) / sum(x**2 for x in s3_list)

    # Weather penalty
    weather_penalty = wind_scale * 0.5 + sea_height * 0.8

    predicted = round(a * speed**3 + weather_penalty, 2)

    # Counterfactual: what if we slow down by 1 knot?
    cf_speed     = speed - 1
    cf_predicted = round(a * cf_speed**3 + weather_penalty, 2)
    cf_saving    = round(predicted - cf_predicted, 2)

    return resp(200, {
        'vessel_id':              vessel_id,
        'input': {
            'speed_kn':       speed,
            'draft_fwd':      draft_fwd,
            'draft_aft':      draft_aft,
            'cargo_on_board': cargo,
            'wind_scale':     wind_scale,
            'sea_height':     sea_height,
        },
        'predicted_consumption_mt': predicted,
        'model':                    'cubic_speed_lsq',
        'counterfactual': {
            'slow_by_1kn_speed':       cf_speed,
            'predicted_consumption_mt': cf_predicted,
            'fuel_saving_mt':           cf_saving,
            'saving_pct':              round(cf_saving / predicted * 100, 1) if predicted else None,
        },
    })


# ── Lambda entry point ────────────────────────────────────────────────────────
def main(event, context):
    try:
        return route(event, context)
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return err(500, str(e))
