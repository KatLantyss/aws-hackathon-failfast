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
    Speed Loss = reference_speed - actual_speed
    Reference: median speed in calm conditions (wind≤3, sea≤1m)
    """
    rows = query_vessel(vessel_id)
    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    # Reference speed: calm condition rows
    calm = [r for r in rows
            if safe_float(r.get('WIND_SCALE'), 99) <= 3
            and safe_float(r.get('SEA_HEIGHT'), 99) <= 1.0]

    calm_speeds = [safe_float(r['SPEED_THROUGH_WATER']) for r in calm if r.get('SPEED_THROUGH_WATER')]
    ref_speed   = sorted(calm_speeds)[len(calm_speeds)//2] if calm_speeds else None  # median

    # Calculate speed loss per record
    timeline = []
    for r in rows:
        stw = safe_float(r.get('SPEED_THROUGH_WATER'))
        if stw is None or ref_speed is None:
            continue
        loss = round(ref_speed - stw, 3)
        timeline.append({
            'noon_day':   safe_float(r.get('NOON_UTC')),
            'voyage':     safe_float(r.get('VOYAGE')),
            'stw':        round(stw, 2),
            'ref_speed':  round(ref_speed, 2),
            'speed_loss': loss,
            'wind_scale': safe_float(r.get('WIND_SCALE')),
            'sea_height': safe_float(r.get('SEA_HEIGHT')),
        })

    avg_loss = round(mean([t['speed_loss'] for t in timeline]), 3) if timeline else None

    return resp(200, {
        'vessel_id':        vessel_id,
        'reference_speed':  round(ref_speed, 2) if ref_speed else None,
        'avg_speed_loss_kn': avg_loss,
        'calm_records_used': len(calm_speeds),
        'timeline':         timeline,
    })


def get_speed_loss_attribution(vessel_id, event):
    """
    Attribute speed loss to: hull_fouling, weather, propeller, other
    Simple heuristic model based on time since last maintenance + weather
    """
    rows  = query_vessel(vessel_id)
    maint = query_maintenance(vessel_id)

    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    # Last dry-dock / UWC events
    dd_events  = sorted([m for m in maint if 'DD' in str(m.get('event_type',''))],
                        key=lambda x: safe_float(x.get('event_day'), 0))
    last_dd_day = safe_float(dd_events[-1].get('event_day'), 0) if dd_events else 0

    # Compute attributions over time
    timeline = []
    for r in rows:
        noon = safe_float(r.get('NOON_UTC'), 0)
        stw  = safe_float(r.get('SPEED_THROUGH_WATER'))
        ref  = safe_float(r.get('FULL_SPD_STW_SLIP'))  # full-speed reference slip
        wind = safe_float(r.get('WIND_SCALE'), 0)
        sea  = safe_float(r.get('SEA_HEIGHT'), 0)

        if stw is None:
            continue

        days_since_dd = max(0, noon - last_dd_day)

        # Heuristics (tuned for 5-yr dataset)
        weather_loss = round(max(0, wind * 0.04 + sea * 0.08), 3)
        hull_loss    = round(min(1.5, days_since_dd * 0.0005), 3)   # grows with time since DD
        prop_loss    = round(safe_float(r.get('ME_SLIP'), 0) * 0.02, 3) if r.get('ME_SLIP') else 0
        other_loss   = round(max(0, 0.1), 3)

        timeline.append({
            'noon_day':      noon,
            'weather_loss':  weather_loss,
            'hull_loss':     hull_loss,
            'propeller_loss': prop_loss,
            'other_loss':    other_loss,
            'total_loss':    round(weather_loss + hull_loss + prop_loss + other_loss, 3),
        })

    # Summary
    if timeline:
        summary = {k: round(mean([t[k] for t in timeline]), 3)
                   for k in ('weather_loss','hull_loss','propeller_loss','other_loss','total_loss')}
    else:
        summary = {}

    return resp(200, {
        'vessel_id': vessel_id,
        'summary':   summary,
        'timeline':  timeline,
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
    """Rank all training vessels by average speed loss"""
    TRAIN_VESSELS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12']
    rankings = []

    for vid in TRAIN_VESSELS:
        rows = query_vessel(vid)
        stw_list = [safe_float(r.get('SPEED_THROUGH_WATER')) for r in rows if r.get('SPEED_THROUGH_WATER')]
        slip_list = [safe_float(r.get('ME_SLIP')) for r in rows if r.get('ME_SLIP')]
        cons_list = [safe_float(r.get('ME_CONSUMPTION')) for r in rows if r.get('ME_CONSUMPTION')]

        calm = [r for r in rows
                if safe_float(r.get('WIND_SCALE'), 99) <= 3
                and safe_float(r.get('SEA_HEIGHT'), 99) <= 1.0]
        calm_speeds = sorted([safe_float(r.get('SPEED_THROUGH_WATER')) for r in calm if r.get('SPEED_THROUGH_WATER')])
        ref = calm_speeds[len(calm_speeds)//2] if calm_speeds else None
        avg_stw = mean(stw_list) if stw_list else 0
        speed_loss = round(ref - avg_stw, 3) if ref else None

        rankings.append({
            'vessel_id':          vid,
            'avg_speed_loss_kn':  speed_loss,
            'avg_me_slip_pct':    round(mean(slip_list), 2) if slip_list else None,
            'avg_consumption_mt': round(mean(cons_list), 2) if cons_list else None,
            'records':            len(rows),
        })

    # Sort by speed loss ascending (less loss = better)
    rankings.sort(key=lambda x: x['avg_speed_loss_kn'] or 99)
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
