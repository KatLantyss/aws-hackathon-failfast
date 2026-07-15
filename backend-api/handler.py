"""
Ship Performance Analysis API
Lambda handler - reads directly from DynamoDB
"""
import json
import os
import math
import pickle
import sys
import time
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from decimal import Decimal
from statistics import mean

# Add vendor directory to path (bundled dependencies: xgboost, scikit-learn, numpy)
_vendor = os.path.join(os.path.dirname(__file__), 'vendor')
if _vendor not in sys.path:
    sys.path.insert(0, _vendor)

import boto3
from boto3.dynamodb.conditions import Key
import numpy as np

# ── Model loading (module-level: loaded once per Lambda container) ────────────
_MODEL_BUNDLE = None

def _load_model():
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is not None:
        return _MODEL_BUNDLE
    model_path = os.path.join(os.path.dirname(__file__), 'model', 'model_v3.pkl')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with open(model_path, 'rb') as f:
            _MODEL_BUNDLE = pickle.load(f)
    return _MODEL_BUNDLE

# Ship type mapping (W1=0: S1-S8, S21 / W2=1: S9-S12, S22, S23)
SHIP_TYPE = {
    'S1': 0, 'S2': 0, 'S3': 0, 'S4': 0,
    'S5': 0, 'S6': 0, 'S7': 0, 'S8': 0,
    'S21': 0,
    'S9': 1, 'S10': 1, 'S11': 1, 'S12': 1,
    'S22': 1, 'S23': 1,
}

# Maintenance types that include hull cleaning
HULL_CLEAN_TYPES  = {'DD', 'UWC', 'UWC+PP'}
# Maintenance types that include propeller polishing
PROP_POLISH_TYPES = {'DD', 'PP', 'UWI+PP', 'UWC+PP'}
# Effective maintenance (any physical intervention, not pure inspection)
EFFECTIVE_TYPES   = {'DD', 'UWC', 'PP', 'UWI+PP', 'UWC+PP'}

# ── DynamoDB setup ──────────────────────────────────────────────────────────
REGION          = os.environ.get('AWS_REGION', 'us-east-1')
VESSEL_TABLE         = os.environ.get('VESSEL_TABLE',        'ship-analysis-dev-vessel-data')
MAINT_TABLE          = os.environ.get('MAINT_TABLE',         'ship-analysis-dev-maintenance-events')
FLEET_SUMMARY_TABLE  = os.environ.get('FLEET_SUMMARY_TABLE', 'ship-analysis-dev-fleet-summary')

ddb = boto3.resource('dynamodb', region_name=REGION)
vessel_tbl       = ddb.Table(VESSEL_TABLE)
maint_tbl        = ddb.Table(MAINT_TABLE)
fleet_summary_tbl = ddb.Table(FLEET_SUMMARY_TABLE)

# Pre-load model on cold start (best-effort; errors surface at predict time)
try:
    _load_model()
except Exception:
    pass

# ── In-memory cache ───────────────────────────────────────────────────────────
# Local dev: DynamoDB round-trips are the main bottleneck. Cache results for
# CACHE_TTL seconds so repeated requests (e.g. fleet ranking) don't re-query.
CACHE_TTL = int(os.environ.get('CACHE_TTL', '300'))  # default 5 minutes

_cache: dict = {}          # key → (timestamp, value)
_cache_lock = threading.Lock()


def _cache_get(key: str):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry[0]) < CACHE_TTL:
            return entry[1]
    return None


def _cache_set(key: str, value):
    with _cache_lock:
        _cache[key] = (time.time(), value)


def _cache_clear():
    """Clear all cached entries (useful for testing or forced refresh)."""
    with _cache_lock:
        _cache.clear()


# ── Background cache warm-up ──────────────────────────────────────────────────
ALL_VESSELS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12',
               'S21','S22','S23']


def _warmup_cache():
    """Prefetch all vessel + maintenance data into cache using parallel threads.

    Called from app.py startup event so all helper functions are defined by
    the time this runs.
    """
    def _fetch(vid):
        try:
            query_vessel(vid)
            query_maintenance(vid)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=15) as pool:
        list(pool.map(_fetch, ALL_VESSELS))

    # Prime the two dashboard-landing endpoints too — otherwise the first real
    # request (almost always the fleet overview page on load) still pays the
    # full DynamoDB round-trip even though every vessel is already cached.
    try:
        get_fleet_summary({})
        get_fleet_ranking({})
    except Exception:
        pass

    # Prime the fleet-wide degradation-rate calibration used by
    # speed-loss-attribution — it pools all 12 training vessels' data, so
    # without this the first attribution request pays that full cost.
    try:
        _fleet_degradation_rates()
    except Exception:
        pass


def start_warmup():
    """Kick off cache warm-up in a background daemon thread (non-blocking)."""
    threading.Thread(target=_warmup_cache, daemon=True).start()


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
    """Query all rows for a vessel, sorted by sort_key (NOON_UTC#idx).

    Results are cached for CACHE_TTL seconds (full-table queries only).
    When a limit is requested the cache is bypassed so callers always get
    fresh paginated results.
    """
    cache_key = f'vessel:{vessel_id}'

    # Only cache unlimited (full) fetches — limited queries are lightweight
    if limit is None:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

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

    if limit is None:
        _cache_set(cache_key, items)

    return items


def query_maintenance(vessel_id: str):
    cache_key = f'maint:{vessel_id}'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    kwargs = dict(KeyConditionExpression=Key('vessel_id').eq(vessel_id))
    items = []
    while True:
        r = maint_tbl.query(**kwargs)
        items.extend(r.get('Items', []))
        if 'LastEvaluatedKey' not in r:
            break
        kwargs['ExclusiveStartKey'] = r['LastEvaluatedKey']

    _cache_set(cache_key, items)
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

    # /api/v1/fleet/summary
    if path == '/api/v1/fleet/summary':
        return get_fleet_summary(event)

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
    Speed Loss Dashboard — 基於 ISO 19030 框架 + 題目指定的 FOC-based 方法。

    篩選條件（題目指定）：
    - WIND_SCALE ≤ 4（Beaufort）
    - HOURS_FULL_SPEED ≥ 22 小時
    - 當日有有效燃料數據

    計算方法：
    Layer 1 (FOC-based, 主指標)：
      Daily FOC = ME_FULLSPEED_CONSUMP_VLSFO_equiv / HOURS_FULL_SPEED × 24
      各燃料用 LCV 熱值換算 VLSFO 當量
      Baseline = 每個養護週期開始後的前 N 筆 calm records 的 RPM-bin median FOC
      Speed Loss % = (actual_foc - baseline_foc) / baseline_foc × 100

    Layer 2 (STW-based, ISO 19030 驗證)：
      在相同 RPM-bin 下比較 STW vs baseline STW
      Speed Loss % = (ref_stw - actual_stw) / ref_stw × 100
    """
    rows = query_vessel(vessel_id)
    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    maint = query_maintenance(vessel_id)

    # ── Fuel LCV constants (MJ/kg) ───────────────────────────────────────
    FUEL_LCV = {
        'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
        'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
        'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
        'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
        'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
    }
    LCV_VLSFO = 40.2
    FUEL_COLS = list(FUEL_LCV.keys())

    # W1 capacity ~110,000 DWT, W2 ~85,000 DWT — ballast threshold ~20%
    W1_BALLAST_THRESHOLD = 22000
    W2_BALLAST_THRESHOLD = 17000
    is_w1 = SHIP_TYPE.get(vessel_id, 0) == 0
    ballast_threshold = W1_BALLAST_THRESHOLD if is_w1 else W2_BALLAST_THRESHOLD

    # ── Identify maintenance cycle boundaries ────────────────────────────
    # Cycles reset on: DD, UWC, UWC+PP (hull cleaning events)
    cycle_events = sorted(
        [m for m in maint if m.get('event_type') in HULL_CLEAN_TYPES],
        key=lambda x: safe_float(x.get('event_day'), 0)
    )
    cycle_boundaries = [safe_float(m.get('event_day'), 0) for m in cycle_events]

    def get_cycle_index(day):
        """Return which maintenance cycle a given day belongs to."""
        idx = 0
        for bd in cycle_boundaries:
            if day >= bd:
                idx += 1
        return idx

    # ── Filter rows: calm condition per competition spec ──────────────────
    def get_daily_foc(r):
        """Calculate Daily FOC in VLSFO equivalent, normalized to 24h."""
        hfs = safe_float(r.get('HOURS_FULL_SPEED'), 0)
        if hfs < 22:
            return None, None

        # Find primary fuel (largest consumption value)
        best_col = None
        best_val = 0
        for fc in FUEL_COLS:
            v = safe_float(r.get(fc), 0)
            if v > best_val:
                best_val = v
                best_col = fc

        if best_col is None or best_val <= 0:
            return None, None

        # Convert to VLSFO equivalent via LCV
        lcv = FUEL_LCV.get(best_col, LCV_VLSFO)
        vlsfo_equiv = best_val * lcv / LCV_VLSFO

        # Normalize to 24-hour basis (competition formula)
        daily_foc = vlsfo_equiv / hfs * 24.0

        # Fuel type short name
        fuel_short = best_col.replace('ME_FULLSPEED_CONSUMP_', '')

        return round(daily_foc, 2), fuel_short

    # Build filtered dataset
    calm_rows = []
    for r in rows:
        ws = safe_float(r.get('WIND_SCALE'), 99)
        hfs = safe_float(r.get('HOURS_FULL_SPEED'), 0)
        if ws > 4 or hfs < 22:
            continue

        daily_foc, fuel_type = get_daily_foc(r)
        if daily_foc is None or daily_foc < 10:
            continue  # Skip anomalously low FOC

        rpm = safe_float(r.get('ME_AVG_RPM'))
        stw = safe_float(r.get('SPEED_THROUGH_WATER'))
        day = safe_float(r.get('NOON_UTC'), 0)
        cargo = safe_float(r.get('CARGO_ON_BOARD'), 0)

        calm_rows.append({
            '_row': r,  # keep reference for STW calc
            'noon_day': day,
            'voyage': safe_float(r.get('VOYAGE')),
            'rpm': rpm,
            'stw': stw,
            'daily_foc_vlsfo': daily_foc,
            'fuel_type': fuel_type,
            'hours_full_speed': hfs,
            'wind_scale': ws,
            'cargo_on_board': cargo,
            'load_condition': 'ballast' if cargo < ballast_threshold else 'laden',
            'cycle': get_cycle_index(day),
        })

    calm_rows.sort(key=lambda x: x['noon_day'])

    # ── Layer 1: FOC-based Speed Loss with per-cycle RPM-bin baseline ────
    # Group by cycle, build baseline from first N records of each cycle
    cycles_data = defaultdict(list)
    for cr in calm_rows:
        cycles_data[cr['cycle']].append(cr)

    # Build per-cycle RPM-bin baselines (first 15% of records or min 5)
    cycle_baselines_foc = {}   # cycle_idx → {rpm_bucket: median_foc}
    cycle_baselines_stw = {}   # cycle_idx → {rpm_bucket: median_stw}

    for cyc_idx, cyc_rows in cycles_data.items():
        n_baseline = max(5, len(cyc_rows) // 7)  # ~15% of cycle
        baseline_subset = cyc_rows[:n_baseline]

        # FOC by RPM bin
        rpm_foc = defaultdict(list)
        rpm_stw_map = defaultdict(list)
        for cr in baseline_subset:
            if cr['rpm'] and cr['rpm'] > 0:
                bucket = int(cr['rpm'] // 5) * 5
                rpm_foc[bucket].append(cr['daily_foc_vlsfo'])
                if cr['stw'] and cr['stw'] > 0:
                    rpm_stw_map[bucket].append(cr['stw'])

        # Use median for robustness against outliers
        cycle_baselines_foc[cyc_idx] = {
            k: round(sorted(v)[len(v)//2], 2) for k, v in rpm_foc.items() if v
        }
        cycle_baselines_stw[cyc_idx] = {
            k: round(sorted(v)[len(v)//2], 3) for k, v in rpm_stw_map.items() if v
        }

    def get_baseline_foc(cycle_idx, rpm):
        """Get baseline FOC for a given cycle and RPM."""
        bl = cycle_baselines_foc.get(cycle_idx, {})
        if not bl:
            return None
        bucket = int(rpm // 5) * 5
        ref = bl.get(bucket)
        if ref is None:
            # Find nearest bucket
            buckets = list(bl.keys())
            if not buckets:
                return None
            bucket = min(buckets, key=lambda b: abs(b - bucket))
            ref = bl[bucket]
        return ref

    def get_baseline_stw(cycle_idx, rpm):
        """Get baseline STW for a given cycle and RPM."""
        bl = cycle_baselines_stw.get(cycle_idx, {})
        if not bl:
            return None
        bucket = int(rpm // 5) * 5
        ref = bl.get(bucket)
        if ref is None:
            buckets = list(bl.keys())
            if not buckets:
                return None
            bucket = min(buckets, key=lambda b: abs(b - bucket))
            ref = bl[bucket]
        return ref

    # Calculate speed loss for each record
    foc_timeline = []
    stw_timeline = []

    for cr in calm_rows:
        rpm = cr['rpm']
        if not rpm or rpm <= 0:
            continue

        # FOC-based speed loss
        baseline_foc = get_baseline_foc(cr['cycle'], rpm)
        if baseline_foc and baseline_foc > 0:
            foc_sl_pct = max(0.0, (cr['daily_foc_vlsfo'] - baseline_foc) / baseline_foc * 100)
            foc_timeline.append({
                'noon_day': cr['noon_day'],
                'voyage': cr['voyage'],
                'rpm': round(rpm, 1),
                'stw': round(cr['stw'], 2) if cr['stw'] else None,
                'daily_foc_vlsfo': cr['daily_foc_vlsfo'],
                'baseline_foc': baseline_foc,
                'speed_loss_pct': round(foc_sl_pct, 2),
                'fuel_type': cr['fuel_type'],
                'hours_full_speed': cr['hours_full_speed'],
                'wind_scale': cr['wind_scale'],
                'cargo_on_board': cr['cargo_on_board'],
                'load_condition': cr['load_condition'],
                'maintenance_cycle': cr['cycle'],
            })

        # STW-based speed loss
        stw = cr['stw']
        if stw and stw > 0:
            ref_stw = get_baseline_stw(cr['cycle'], rpm)
            if ref_stw and ref_stw > 0:
                stw_sl_pct = max(0.0, (ref_stw - stw) / ref_stw * 100)
                stw_timeline.append({
                    'noon_day': cr['noon_day'],
                    'voyage': cr['voyage'],
                    'rpm': round(rpm, 1),
                    'stw': round(stw, 2),
                    'ref_stw': ref_stw,
                    'speed_loss_pct': round(stw_sl_pct, 2),
                    'wind_scale': cr['wind_scale'],
                    'load_condition': cr['load_condition'],
                    'maintenance_cycle': cr['cycle'],
                })

    # ── Summaries ────────────────────────────────────────────────────────
    avg_foc_sl = round(mean([t['speed_loss_pct'] for t in foc_timeline]), 2) if foc_timeline else None
    avg_stw_sl = round(mean([t['speed_loss_pct'] for t in stw_timeline]), 2) if stw_timeline else None

    # Build flat baseline maps for response
    # Merge all cycle baselines (show the one with most data)
    all_foc_baselines = {}
    for cyc_bl in cycle_baselines_foc.values():
        for k, v in cyc_bl.items():
            all_foc_baselines[k] = v  # last cycle wins for display
    all_stw_baselines = {}
    for cyc_bl in cycle_baselines_stw.values():
        for k, v in cyc_bl.items():
            all_stw_baselines[k] = v

    # Maintenance cycles summary
    maintenance_cycles = []
    for cyc_idx in sorted(cycles_data.keys()):
        cyc_rows_sorted = cycles_data[cyc_idx]
        if not cyc_rows_sorted:
            continue
        start_day = cyc_rows_sorted[0]['noon_day']
        end_day = cyc_rows_sorted[-1]['noon_day']
        # What event triggered this cycle?
        trigger = None
        if cyc_idx > 0 and cyc_idx - 1 < len(cycle_events):
            trigger = cycle_events[cyc_idx - 1].get('event_type')

        # Baseline vs end-of-cycle FOC
        bl_focs = [cr['daily_foc_vlsfo'] for cr in cyc_rows_sorted[:max(5, len(cyc_rows_sorted)//7)]]
        end_focs = [cr['daily_foc_vlsfo'] for cr in cyc_rows_sorted[-min(10, len(cyc_rows_sorted)):]]
        bl_avg = round(mean(bl_focs), 1) if bl_focs else None
        end_avg = round(mean(end_focs), 1) if end_focs else None
        degrad = round((end_avg - bl_avg) / bl_avg * 100, 1) if bl_avg and end_avg and bl_avg > 0 else None

        maintenance_cycles.append({
            'cycle_index': cyc_idx,
            'start_day': start_day,
            'end_day': end_day,
            'trigger_event': trigger,
            'records': len(cyc_rows_sorted),
            'baseline_foc_avg': bl_avg,
            'end_foc_avg': end_avg,
            'degradation_pct': degrad,
        })

    return resp(200, {
        'vessel_id': vessel_id,
        'method': 'ISO19030_FOC_normalized + STW_RPM_baseline',
        'filter_criteria': {
            'wind_scale_max': 4,
            'hours_full_speed_min': 22,
        },
        # Layer 1: FOC-based (primary indicator per competition spec)
        'foc_summary': {
            'avg_daily_foc_vlsfo': round(mean([t['daily_foc_vlsfo'] for t in foc_timeline]), 2) if foc_timeline else None,
            'avg_speed_loss_pct': avg_foc_sl,
            'baseline_foc_by_rpm': all_foc_baselines,
            'valid_records': len(foc_timeline),
            'total_records': len(rows),
        },
        'foc_timeline': foc_timeline,
        # Layer 2: STW-based (ISO 19030 verification)
        'stw_summary': {
            'avg_speed_loss_pct': avg_stw_sl,
            'baseline_stw_by_rpm': all_stw_baselines,
            'valid_records': len(stw_timeline),
        },
        'stw_timeline': stw_timeline,
        # Maintenance cycle breakdown
        'maintenance_cycles': maintenance_cycles,
    })


def _calm_slip_series(vessel_id):
    """FULL_SPD_STW_SLIP series filtered to calm/steady-state days (same
    criteria as get_speed_loss(): WIND_SCALE ≤ 4, HOURS_FULL_SPEED ≥ 22),
    sorted by day. Shared by fleet calibration and per-vessel attribution so
    both use the exact same "clean" dataset."""
    recs = []
    for r in query_vessel(vessel_id):
        slip = safe_float(r.get('FULL_SPD_STW_SLIP'))
        day  = safe_float(r.get('NOON_UTC'))
        ws   = safe_float(r.get('WIND_SCALE'))
        hfs  = safe_float(r.get('HOURS_FULL_SPEED'))
        if slip is None or day is None or not (0 <= slip <= 30):
            continue
        if ws is None or hfs is None or ws > 4 or hfs < 22:
            continue
        recs.append((day, slip))
    recs.sort()
    return recs


def _cycle_index(day, boundaries):
    idx = 0
    for b in boundaries:
        if day >= b:
            idx += 1
    return idx


def _fleet_degradation_rates():
    """Fleet-calibrated hull / propeller degradation rate (%FULL_SPD_STW_SLIP
    per 30 days), pooled across all 12 training vessels.

    Why pooled instead of per-ship/per-event: a single ship's single
    maintenance cycle is dominated by day-to-day operational noise (R² ~0.07
    fitting slip vs. days-since-cleaning per cycle — the trend is real but
    weak relative to noise). Pooling ~3,000+ calm-condition records per
    channel across the whole fleet turns that weak per-cycle signal into a
    statistically solid population-level rate: hull ~0.088%/30d (t≈12),
    propeller ~0.083%/30d (t≈6) — both far past the |t|>2 significance bar.
    This is the number that actually answers "how much of speed loss is
    attributable to hull vs. propeller fouling", not any single event's
    noisy before/after snapshot.

    Each cycle is centered on its own baseline (mean of its first ~15%)
    before pooling, so ship-to-ship absolute-level differences don't bias
    the pooled slope — only the *shape* of degradation over elapsed days
    contributes. Cached (queries all 12 training vessels).
    """
    cache_key = 'fleet:degradation_rates'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    TRAIN_VESSELS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12']

    def pooled_rate(type_set):
        pooled_x, pooled_y = [], []
        for vid in TRAIN_VESSELS:
            recs  = _calm_slip_series(vid)
            maint = query_maintenance(vid)
            boundaries = sorted(
                safe_float(m.get('event_day'), 0)
                for m in maint if str(m.get('event_type', '')) in type_set
            )
            cycles = defaultdict(list)
            for day, slip in recs:
                cycles[_cycle_index(day, boundaries)].append((day, slip))

            for idx, cyc in cycles.items():
                if idx == 0 or len(cyc) < 10:
                    continue  # skip unanchored first cycle + too-sparse cycles
                cyc.sort()
                start_day = boundaries[idx - 1]
                n_base = max(3, len(cyc) // 7)
                baseline = mean([s for _, s in cyc[:n_base]])
                for d, s in cyc:
                    pooled_x.append(d - start_day)
                    pooled_y.append(s - baseline)

        n = len(pooled_x)
        if n < 30:
            return {'slope_per_30d_pct': None, 't_stat': None, 'n_records': n, 'significant': False}

        mx, my = mean(pooled_x), mean(pooled_y)
        sxx = sum((x - mx) ** 2 for x in pooled_x)
        if sxx == 0:
            return {'slope_per_30d_pct': None, 't_stat': None, 'n_records': n, 'significant': False}
        sxy   = sum((x - mx) * (y - my) for x, y in zip(pooled_x, pooled_y))
        slope = sxy / sxx
        intercept = my - slope * mx
        resid = [y - (slope * x + intercept) for x, y in zip(pooled_x, pooled_y)]
        mse = sum(r ** 2 for r in resid) / (n - 2)
        se_slope = math.sqrt(mse / sxx)
        t_stat = slope / se_slope if se_slope else None

        return {
            'slope_per_30d_pct': round(slope * 30, 4),
            't_stat':            round(t_stat, 2) if t_stat else None,
            'n_records':         n,
            'significant':       bool(t_stat and abs(t_stat) > 2),
        }

    result = {
        'hull':                pooled_rate(HULL_CLEAN_TYPES),
        'propeller':           pooled_rate(PROP_POLISH_TYPES),
        'calibrated_on_vessels': len(TRAIN_VESSELS),
        'method': 'pooled_linear_regression_calm_slip_vs_days_since_cleaning',
    }
    _cache_set(cache_key, result)
    return result


def get_speed_loss_attribution(vessel_id, event):
    """
    Speed Loss 歸因分析：用「艦隊校準劣化速率」模型分開估算船殼與螺旋槳個別
    對滑差(%)的貢獻，取代舊版「事件前後 ±30 天快照平均」的做法。

    為什麼要換方法：單一事件、單一船的 before/after 快照比較，被短期操作雜訊
    （天候、載重、清潔後試俥等）嚴重污染——實測過三種改法（天候篩選、RPM 配對、
    週期邊界快照）,「清潔後效能反而變差」這種違反物理常識的比例都還停在 40-60%
    區間。真正乾淨的訊號，是把全船隊的資料 pool 起來做迴歸（見
    `_fleet_degradation_rates()`）：單一週期的 R² 只有 ~0.07（雜訊蓋過趨勢），
    但 pool 起來後 n>3000，船殼/螺旋槳的劣化速率都達到統計顯著（|t|>2）。

    邏輯：
    - 用 `_fleet_degradation_rates()` 算出的船隊平均速率（%/30天），乘上「這次
      清潔距上次同通道清潔累積了幾天」，估算這次清潔前累積了多少滑差——這是
      模型推論值，不是原始資料直接比較，所以不會再出現「清潔後變差」這種假訊號。
    - `slip_after_pct`＝清潔後那個週期實際觀測到的 baseline（真實資料錨點）；
      `slip_before_pct`＝該值加上模型估算的累積量；`slip_delta_pct`＝累積量本身。
    - DD/UWC+PP → 船殼+螺旋槳速率都套用；UWC → 只套船殼；PP/UWI+PP → 只套螺旋槳；
      UWI（純檢查）→ 不套用任何速率，維持「不該有改善」。

    weather：DIFF_STW_SOG_SLIP（洋流/天候代理），跟養護事件無關，維持原樣。
    """
    rows  = query_vessel(vessel_id)
    maint = query_maintenance(vessel_id)

    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    rates = _fleet_degradation_rates()
    hull_rate = rates['hull']['slope_per_30d_pct']
    prop_rate = rates['propeller']['slope_per_30d_pct']

    slip_series = _calm_slip_series(vessel_id)

    MIN_CYCLE_RECORDS = 6

    def cycle_baselines(type_set):
        """Observed post-clean baseline (mean of first ~15%) per cycle,
        keyed by cycle index, plus the sorted trigger-event list."""
        trigger_events = sorted(
            [m for m in maint if str(m.get('event_type', '')) in type_set],
            key=lambda x: safe_float(x.get('event_day'), 0),
        )
        boundaries = [safe_float(m.get('event_day'), 0) for m in trigger_events]
        buckets = defaultdict(list)
        for day, slip in slip_series:
            buckets[_cycle_index(day, boundaries)].append((day, slip))
        baselines = {}
        for idx, records in buckets.items():
            if len(records) < MIN_CYCLE_RECORDS:
                continue
            n_base = max(3, len(records) // 7)
            baselines[idx] = round(mean([s for _, s in records[:n_base]]), 2)
        return trigger_events, boundaries, baselines

    hull_events, hull_boundaries, hull_baselines = cycle_baselines(HULL_CLEAN_TYPES)
    prop_events, prop_boundaries, prop_baselines = cycle_baselines(PROP_POLISH_TYPES)

    def estimate(events, boundaries, baselines, rate, target_day):
        """days-since-prior-same-channel-event × fleet rate = modeled
        accumulated slip before this cleaning; after = observed post-clean
        baseline of the cycle this event starts."""
        idx = next((i for i, m in enumerate(events)
                    if safe_float(m.get('event_day'), 0) == target_day), None)
        if idx is None or rate is None:
            return None, None
        after = baselines.get(idx + 1)
        if after is None:
            return None, None
        days_accumulated = target_day - (boundaries[idx - 1] if idx > 0 else 0.0)
        accumulated_slip = round(rate / 30.0 * days_accumulated, 2)
        before = round(after + accumulated_slip, 2)
        return before, after

    # 養護事件歸因
    event_attributions = []
    for m in sorted(maint, key=lambda x: safe_float(x.get('event_day'), 0)):
        day   = safe_float(m.get('event_day'), 0)
        etype = str(m.get('event_type', ''))

        if 'DD' in etype:
            category = 'hull+propeller'
        elif 'UWC' in etype and 'PP' in etype:
            category = 'hull+propeller'
        elif 'UWC' in etype:
            category = 'hull'
        elif 'PP' in etype:
            category = 'propeller'
        elif etype == 'UWI':
            category = 'inspection_only'  # 不應有改善，不套用任何速率
        else:
            category = 'other'

        if category in ('hull', 'hull+propeller'):
            before, after = estimate(hull_events, hull_boundaries, hull_baselines, hull_rate, day)
        elif category == 'propeller':
            before, after = estimate(prop_events, prop_boundaries, prop_baselines, prop_rate, day)
        else:
            before, after = None, None

        if before is None or after is None:
            delta = None
            physical = False
        else:
            delta    = round(before - after, 2)   # 正值 = 改善（滑差下降），模型推論恆非負
            physical = category != 'inspection_only'

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
                else f'Fleet-rate-modeled improvement: {delta:+.2f}%' if delta is not None
                else 'Insufficient data (cycle too short/sparse, or first event with no prior anchor)'
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
        'method':      'fleet_calibrated_degradation_rate',
        'fleet_calibration': rates,
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

    rows_sorted = sorted(rows, key=lambda x: safe_float(x.get('NOON_UTC'), 0))

    # Last 90 days of data (last 90 noon_day records)
    recent = rows_sorted[-90:]
    slips  = [safe_float(r.get('ME_SLIP')) for r in recent if r.get('ME_SLIP')]
    avg_slip = round(mean(slips), 2) if slips else None

    # Prior 90-day window, same recent-vs-prior methodology as slip_trend in
    # build_fleet_summary.py, to get a real degradation rate (not a guess).
    prior = rows_sorted[-180:-90] if len(rows_sorted) > 90 else []
    prior_slips = [safe_float(r.get('ME_SLIP')) for r in prior if r.get('ME_SLIP')]
    avg_prior_slip = round(mean(prior_slips), 2) if prior_slips else None
    degradation_rate_pct_per_day = (
        round((avg_slip - avg_prior_slip) / 90, 5)
        if avg_slip is not None and avg_prior_slip is not None else 0.0
    )

    # Real average fuel consumption for this vessel (MT/day). Combined with the
    # same baseline*slip%*1.8*FUEL_PRICE methodology used in
    # build_fleet_summary.py for excess_fuel_cost_usd_per_day, this projects a
    # cumulative excess-fuel-cost curve if maintenance is deferred — no
    # per-event cleaning/opportunity cost is included since that data doesn't
    # exist anywhere in the dataset.
    cons_list = [safe_float(r.get('ME_CONSUMPTION')) for r in recent if r.get('ME_CONSUMPTION')]
    avg_consumption_mt = round(mean(cons_list), 2) if cons_list else None

    FUEL_PRICE = 620
    curve = []
    if avg_slip is not None and avg_consumption_mt is not None:
        cumulative = 0.0
        for d in range(91):
            projected_slip = max(0.0, avg_slip + degradation_rate_pct_per_day * d)
            excess_per_day = avg_consumption_mt * (projected_slip / 100) * 1.8 * FUEL_PRICE
            cumulative += excess_per_day
            curve.append({
                'deferral_days':                   d,
                'projected_slip_pct':               round(projected_slip, 2),
                'cumulative_excess_fuel_cost_usd':  round(cumulative, 2),
            })

    # Last maintenance
    all_maint = sorted(maint, key=lambda x: safe_float(x.get('event_day'), 0))
    last_m    = all_maint[-1] if all_maint else None
    last_day  = safe_float(last_m.get('event_day'), 0) if last_m else 0
    latest_day = safe_float(recent[-1].get('NOON_UTC'), 0) if recent else 0
    days_since = latest_day - last_day

    # Simple rule: recommend if slip > 10% or days since last > 365
    urgent = (avg_slip and avg_slip > 10) or days_since > 365

    return resp(200, {
        'vessel_id':                     vessel_id,
        'days_since_maintenance':        round(days_since),
        'avg_me_slip_pct':               avg_slip,
        'avg_consumption_mt':            avg_consumption_mt,
        'degradation_rate_pct_per_day':  degradation_rate_pct_per_day,
        'fuel_price_usd_per_mt':         FUEL_PRICE,
        'recommendation':                'URGENT' if urgent else 'ROUTINE',
        'recommended_type':              'DD' if days_since > 730 else 'UWC',
        'reason':                        (
            'High ME slip indicates hull/propeller fouling' if avg_slip and avg_slip > 10
            else f'Scheduled maintenance due ({round(days_since)} days since last event)'
        ),
        'last_maintenance': {
            'event_type': last_m.get('event_type') if last_m else None,
            'event_day':  last_day,
        },
        'curve': curve,
    })


def get_fleet_summary(event):
    """Single-call fleet summary used by the dashboard overview.

    Reads pre-computed per-vessel stats from the fleet-summary DynamoDB table
    (populated by build_fleet_summary.py). Falls back to on-the-fly computation
    if the table is empty or unavailable.

    Response shape:
    {
      total_vessels: int,
      training_vessels: int,
      prediction_vessels: int,
      pending_maintenance: int,
      avg_fleet_slip_pct: float,
      total_excess_fuel_cost_usd_per_day: float,
      worst_vessel: { vessel_id, avg_slip_pct, urgency },
      per_vessel: [
        { vessel_id, vessel_type, ship_class, avg_slip_pct,
          recent_90d_slip_pct, slip_trend, avg_consumption_mt,
          urgency, days_since_maintenance, excess_fuel_cost_usd_per_day,
          total_records, total_voyages, last_updated }
      ]
    }
    """
    cache_key = 'fleet:summary'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    TRAIN_VESSELS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12']
    PRED_VESSELS  = ['S21','S22','S23']
    ALL = TRAIN_VESSELS + PRED_VESSELS

    # ── Read from fleet-summary table (single Scan — 15 items, very fast) ────
    per_vessel = []
    try:
        scan_resp = fleet_summary_tbl.scan()
        raw_items = scan_resp.get('Items', [])
        # Handle DynamoDB pagination (unlikely for 15 items, but safe)
        while 'LastEvaluatedKey' in scan_resp:
            scan_resp = fleet_summary_tbl.scan(ExclusiveStartKey=scan_resp['LastEvaluatedKey'])
            raw_items.extend(scan_resp.get('Items', []))
    except Exception:
        raw_items = []

    if raw_items:
        def _f(item, key):
            v = item.get(key)
            return float(v) if v is not None else None

        def _i(item, key):
            v = item.get(key)
            return int(v) if v is not None else None

        def _s(item, key, default=''):
            v = item.get(key)
            return str(v) if v is not None else default

        for item in raw_items:
            per_vessel.append({
                # identification
                'vessel_id':    _s(item, 'vessel_id'),
                'type':         _s(item, 'vessel_type', 'training'),
                'ship_class':   _s(item, 'ship_class'),
                # slip
                'avg_slip_pct':        _f(item, 'avg_slip_pct'),
                'recent_90d_slip_pct': _f(item, 'recent_90d_slip_pct'),
                'slip_trend':          _f(item, 'slip_trend'),
                'valid_slip_records':  _i(item, 'valid_slip_records'),
                # performance
                'avg_speed_kn':       _f(item, 'avg_speed_kn'),
                'avg_stw_kn':         _f(item, 'avg_stw_kn'),
                'avg_rpm':            _f(item, 'avg_rpm'),
                'avg_consumption_mt': _f(item, 'avg_consumption_mt'),
                'avg_sfoc':           _f(item, 'avg_sfoc'),
                'avg_horse_power':    _f(item, 'avg_horse_power'),
                'avg_me_slip_pct':    _f(item, 'avg_me_slip_pct'),
                'avg_load_pct':       _f(item, 'avg_load_pct'),
                # environment
                'avg_wind_scale':       _f(item, 'avg_wind_scale'),
                'avg_sea_height_m':     _f(item, 'avg_sea_height_m'),
                'avg_sea_water_temp_c': _f(item, 'avg_sea_water_temp_c'),
                # loading
                'avg_fore_draft_m':      _f(item, 'avg_fore_draft_m'),
                'avg_aft_draft_m':       _f(item, 'avg_aft_draft_m'),
                'avg_mid_draft_m':       _f(item, 'avg_mid_draft_m'),
                'avg_cargo_on_board_mt': _f(item, 'avg_cargo_on_board_mt'),
                'avg_displacement_mt':   _f(item, 'avg_displacement_mt'),
                # voyage coverage
                'total_records':   _i(item, 'total_records') or 0,
                'total_voyages':   _i(item, 'total_voyages') or 0,
                'day_range_min':   _i(item, 'day_range_min'),
                'day_range_max':   _i(item, 'day_range_max'),
                'data_span_days':  _i(item, 'data_span_days'),
                # maintenance
                'total_maint_events':     _i(item, 'total_maint_events'),
                'last_event_type':        _s(item, 'last_event_type') or None,
                'last_event_day':         _i(item, 'last_event_day'),
                'days_since_maintenance': _i(item, 'days_since_maintenance'),
                'days_since_hull_clean':  _i(item, 'days_since_hull_clean'),
                'last_hull_clean_type':   _s(item, 'last_hull_clean_type') or None,
                'last_hull_clean_day':    _i(item, 'last_hull_clean_day'),
                'last_prop_polish_day':   _i(item, 'last_prop_polish_day'),
                'days_since_prop_polish': _i(item, 'days_since_prop_polish'),
                # cost
                'excess_fuel_cost_usd_per_day': float(item['excess_fuel_cost_usd_per_day']) if item.get('excess_fuel_cost_usd_per_day') is not None else 0.0,
                # urgency
                'urgency': _s(item, 'urgency', 'LOW'),
                # position
                'lat':         float(item['lat'])         if item.get('lat')         is not None else 0.0,
                'lon':         float(item['lon'])         if item.get('lon')         is not None else 0.0,
                'heading_deg': float(item['heading_deg']) if item.get('heading_deg') is not None else 0.0,
                'speed_kt':    float(item['speed_kt'])    if item.get('speed_kt')    is not None else 0.0,
                # meta
                'last_updated': _s(item, 'last_updated'),
                'rank': None,
            })

        # Attach rank from fleet/ranking (uses its own cache)
        ranking_resp = get_fleet_ranking(event)
        if ranking_resp['statusCode'] == 200:
            import json as _json
            for entry in _json.loads(ranking_resp['body']).get('fleet_ranking', []):
                for v in per_vessel:
                    if v['vessel_id'] == entry['vessel_id']:
                        v['rank'] = entry['rank']
                        break

    else:
        # ── Fallback: on-the-fly computation (no table data yet) ──────────────
        W1_SHIPS_SET = {'S1','S2','S3','S4','S5','S6','S7','S8','S21'}
        FUEL_PRICE   = 620

        def _vessel_summary_fallback(vid: str) -> dict:
            rows  = query_vessel(vid)
            maint = query_maintenance(vid)
            slip_list = [safe_float(r.get('FULL_SPD_STW_SLIP'))
                         for r in rows
                         if safe_float(r.get('FULL_SPD_STW_SLIP')) is not None
                         and 0 <= safe_float(r.get('FULL_SPD_STW_SLIP'), -1) <= 30]
            avg_slip   = round(mean(slip_list), 2) if slip_list else None
            slip_sorted = sorted(
                [(safe_float(r.get('NOON_UTC'), 0), safe_float(r.get('FULL_SPD_STW_SLIP')))
                 for r in rows
                 if safe_float(r.get('FULL_SPD_STW_SLIP')) is not None
                 and 0 <= safe_float(r.get('FULL_SPD_STW_SLIP'), -1) <= 30],
                key=lambda x: x[0])
            recent_90d = round(mean([v for _, v in slip_sorted[-90:]]), 2) if len(slip_sorted) >= 10 else avg_slip
            sorted_maint = sorted(maint, key=lambda x: safe_float(x.get('event_day'), 0))
            last_day   = safe_float(sorted_maint[-1].get('event_day'), 0) if sorted_maint else 0
            latest_day = safe_float(max((safe_float(r.get('NOON_UTC'), 0) for r in rows), default=0))
            days_since = round(latest_day - last_day) if rows else None
            HULL_CLEAN_TYPES = {'DD', 'UWC', 'UWC+PP'}
            hull_clean_events = [m for m in sorted_maint if str(m.get('event_type', '')).strip() in HULL_CLEAN_TYPES]
            last_hull_day = safe_float(hull_clean_events[-1].get('event_day'), 0) if hull_clean_events else 0
            days_since_hull = round(latest_day - last_hull_day) if (rows and hull_clean_events) else None
            slip_val   = recent_90d or avg_slip or 0
            urgency    = ('HIGH'   if (slip_val >= 10 or (days_since and days_since > 365)) else
                          'MEDIUM' if (slip_val >= 6  or (days_since and days_since > 270)) else 'LOW')
            cons_list  = [safe_float(r.get('ME_CONSUMPTION')) for r in rows if r.get('ME_CONSUMPTION')]
            avg_consumption = round(mean(cons_list), 2) if cons_list else None
            # Uses this vessel's own real avg consumption, not a guessed per-class constant.
            excess_per_day = (
                round(avg_consumption * (slip_val / 100) * 1.8 * FUEL_PRICE, 2)
                if avg_consumption is not None else None
            )
            return {
                'vessel_id':               vid,
                'type':                    'training' if vid in TRAIN_VESSELS else 'prediction',
                'ship_class':              'W1' if vid in W1_SHIPS_SET else 'W2',
                'avg_slip_pct':            avg_slip,
                'recent_90d_slip_pct':     recent_90d,
                'slip_trend':              None,
                'avg_consumption_mt':      avg_consumption,
                'urgency':                 urgency,
                'days_since_maintenance':  days_since,
                'days_since_hull_clean':   days_since_hull,
                'excess_fuel_cost_usd_per_day': excess_per_day,
                'lat':         0.0,
                'lon':         0.0,
                'heading_deg': 0.0,
                'speed_kt':    0.0,
                'total_records':           len(rows),
                'total_voyages':           0,
                'last_updated':            '',
                'rank':                    None,
            }

        with ThreadPoolExecutor(max_workers=15) as pool:
            futures = {pool.submit(_vessel_summary_fallback, vid): vid for vid in ALL}
            for future in as_completed(futures):
                try:
                    per_vessel.append(future.result())
                except Exception:
                    pass

    # Sort: training first, then prediction; within group by avg_slip desc
    per_vessel.sort(key=lambda v: (0 if v['type'] == 'training' else 1, -(v['avg_slip_pct'] or 0)))

    # Fleet-level aggregates (training vessels only for slip average)
    training  = [v for v in per_vessel if v['type'] == 'training']
    slip_vals = [v['avg_slip_pct'] for v in training if v['avg_slip_pct'] is not None]
    pending   = [v for v in per_vessel if v['urgency'] != 'LOW']
    total_excess = sum(v['excess_fuel_cost_usd_per_day'] or 0 for v in per_vessel)
    worst = max(training, key=lambda v: v['avg_slip_pct'] or 0) if training else None

    result = resp(200, {
        'total_vessels':                  len(ALL),
        'training_vessels':               len(TRAIN_VESSELS),
        'prediction_vessels':             len(PRED_VESSELS),
        'pending_maintenance':            len(pending),
        'avg_fleet_slip_pct':             round(mean(slip_vals), 2) if slip_vals else None,
        'total_excess_fuel_cost_usd_per_day': round(total_excess, 2),
        'worst_vessel': {
            'vessel_id':    worst['vessel_id'],
            'avg_slip_pct': worst['avg_slip_pct'],
            'urgency':      worst['urgency'],
        } if worst else None,
        'per_vessel': per_vessel,
    })
    _cache_set(cache_key, result)
    return result


def _rank_one_vessel(vid: str) -> dict:
    """Compute ranking stats for a single vessel (runs in thread pool)."""
    rows = query_vessel(vid)

    slip_list = [safe_float(r.get('FULL_SPD_STW_SLIP')) for r in rows
                 if safe_float(r.get('FULL_SPD_STW_SLIP')) is not None
                 and 0 <= safe_float(r.get('FULL_SPD_STW_SLIP'), -1) <= 30]
    cons_list = [safe_float(r.get('ME_CONSUMPTION')) for r in rows if r.get('ME_CONSUMPTION')]

    slip_sorted = sorted(
        [(safe_float(r.get('NOON_UTC'), 0), safe_float(r.get('FULL_SPD_STW_SLIP')))
         for r in rows
         if safe_float(r.get('FULL_SPD_STW_SLIP')) is not None
         and 0 <= safe_float(r.get('FULL_SPD_STW_SLIP'), -1) <= 30],
        key=lambda x: x[0]
    )
    recent_slip = [v for _, v in slip_sorted[-90:]] if len(slip_sorted) >= 10 else []
    trend = round(mean(recent_slip) - mean(slip_list), 2) if recent_slip and slip_list else None

    return {
        'vessel_id':           vid,
        'avg_slip_pct':        round(mean(slip_list), 2) if slip_list else None,
        'recent_90d_slip_pct': round(mean(recent_slip), 2) if recent_slip else None,
        'slip_trend':          trend,
        'avg_consumption_mt':  round(mean(cons_list), 2) if cons_list else None,
        'valid_slip_records':  len(slip_list),
        'total_records':       len(rows),
    }


def get_fleet_ranking(event):
    """Rank all training vessels by avg FULL_SPD_STW_SLIP (lower = better performance)."""
    TRAIN_VESSELS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12']

    # Return cached ranking if still fresh
    cache_key = 'fleet:ranking'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Fetch all vessels in parallel (12 DynamoDB queries → concurrent threads)
    rankings = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(_rank_one_vessel, vid): vid for vid in TRAIN_VESSELS}
        for future in as_completed(futures):
            try:
                rankings.append(future.result())
            except Exception:
                pass  # skip failed vessel, don't crash the whole ranking

    # 排名：avg_slip_pct 越低越好
    rankings.sort(key=lambda x: x['avg_slip_pct'] if x['avg_slip_pct'] is not None else 99)
    for i, r in enumerate(rankings):
        r['rank'] = i + 1

    result = resp(200, {'fleet_ranking': rankings, 'total': len(rankings)})
    _cache_set(cache_key, result)
    return result


def _build_features(vessel_id, speed_kn, stw, wind_scale, wind_speed,
                    sea_height, swell_height, sea_water_temp, water_depth,
                    diff_stw_sog_slip, full_spd_stw_slip,
                    hours_full_speed, hours_total,
                    fore_draft, aft_draft, mid_draft,
                    maint_rows,
                    as_of_day=None,
                    override_days_since_hull_clean=None,
                    override_days_since_prop_polish=None):
    """
    Build the 29-feature vector expected by model_v3.pkl.

    Features (in order):
      0  WIND_SCALE
      1  WIND_SPEED
      2  SEA_HEIGHT
      3  SWELL_HEIGHT
      4  SEA_WATER_TEMP
      5  WATER_DEPTH
      6  DIFF_STW_SOG_SLIP
      7  FULL_SPD_STW_SLIP
      8  AVG_SPEED
      9  SPEED_THROUGH_WATER
     10  HOURS_FULL_SPEED
     11  HOURS_TOTAL
     12  FORE_DRAFT
     13  AFTER_DRAFT
     14  MID_DRAFT
     15  ship_type              (W1=0, W2=1)
     16  days_since_dd
     17  days_since_hull_clean
     18  days_since_prop_polish
     19  days_since_effective_maint
     20  last_maint_hull_effect
     21  last_maint_prop_effect
     22  maint_count_total
     23  maint_count_effective
     24  sqrt_days_since_hull_clean
     25  sqrt_days_since_prop_polish
     26  physics_consumption    (ship_coefficient / speed^2)
     27  is_clean_voyage        (hours_full_speed >= 22)
     28  is_calm_sea            (wind_scale <= 3 and sea_height <= 1)

    override_days_since_hull_clean / override_days_since_prop_polish:
      When set, directly replace those features for counterfactual inference.
    """
    bundle = _load_model()
    coeff  = bundle['ship_coefficients'].get(vessel_id, 320.0)  # fallback avg

    # ── Maintenance-derived features ─────────────────────────────────────────
    # as_of_day: the NOON_UTC of the day being predicted.
    # If not provided, fall back to last maintenance event day + 1.
    if as_of_day is not None:
        _as_of = float(as_of_day)
    elif maint_rows:
        _as_of = max(safe_float(m.get('event_day'), 0) for m in maint_rows) + 1.0
    else:
        _as_of = 365.0  # safe default

    days_since_dd          = _as_of  # default: never had DD
    days_since_hull_clean  = _as_of
    days_since_prop_polish = _as_of
    days_since_eff         = _as_of
    last_hull_effect       = 0.0
    last_prop_effect       = 0.0
    maint_count_total      = 0
    maint_count_effective  = 0

    # Walk events in chronological order; last matching event wins
    for m in sorted(maint_rows or [], key=lambda x: safe_float(x.get('event_day'), 0)):
        eday  = safe_float(m.get('event_day'), 0)
        etype = str(m.get('event_type', ''))
        maint_count_total += 1

        if etype in EFFECTIVE_TYPES:
            maint_count_effective += 1
            days_since_eff = _as_of - eday

        if etype == 'DD':
            days_since_dd          = _as_of - eday
            days_since_hull_clean  = _as_of - eday
            days_since_prop_polish = _as_of - eday
            last_hull_effect = 1.0
            last_prop_effect = 1.0
        else:
            if etype in HULL_CLEAN_TYPES:
                days_since_hull_clean = _as_of - eday
                last_hull_effect = 1.0
            if etype in PROP_POLISH_TYPES:
                days_since_prop_polish = _as_of - eday
                last_prop_effect = 1.0

    # Apply counterfactual overrides (simulate freshly cleaned state)
    if override_days_since_hull_clean is not None:
        days_since_hull_clean = float(override_days_since_hull_clean)
        last_hull_effect = 1.0
    if override_days_since_prop_polish is not None:
        days_since_prop_polish = float(override_days_since_prop_polish)
        last_prop_effect = 1.0

    # Physics baseline: admiralty-style  consumption = coeff / speed^2
    safe_speed = max(stw, 0.1)
    physics_consumption = coeff / (safe_speed ** 2)

    is_clean_voyage = 1.0 if (hours_full_speed or 0) >= 22 else 0.0
    is_calm_sea     = 1.0 if (wind_scale or 0) <= 3 and (sea_height or 0) <= 1.0 else 0.0

    row = [
        wind_scale      or 0.0,
        wind_speed      or 0.0,
        sea_height      or 0.0,
        swell_height    or 0.0,
        sea_water_temp  or 20.0,
        water_depth     or 100.0,
        diff_stw_sog_slip or 0.0,
        full_spd_stw_slip or 0.0,
        speed_kn,
        stw,
        hours_full_speed or 24.0,
        hours_total      or 24.0,
        fore_draft  or 13.0,
        aft_draft   or 13.0,
        mid_draft   or 13.0,
        float(SHIP_TYPE.get(vessel_id, 0)),
        days_since_dd,
        days_since_hull_clean,
        days_since_prop_polish,
        days_since_eff,
        last_hull_effect,
        last_prop_effect,
        float(maint_count_total),
        float(maint_count_effective),
        math.sqrt(max(days_since_hull_clean, 0)),
        math.sqrt(max(days_since_prop_polish, 0)),
        physics_consumption,
        is_clean_voyage,
        is_calm_sea,
    ]
    return np.array([row], dtype=np.float32)


def predict_fuel(event):
    """
    XGBoost fuel consumption prediction using model_v3.pkl.

    Mode 1 — noon_day lookup (recommended):
      Pass vessel_id + noon_day → handler fetches that day's row from DynamoDB
      and computes all features automatically.

      POST { "vessel_id": "S21", "noon_day": 136 }

    Mode 2 — manual override (optional, for what-if scenarios):
      Any A-class field can be overridden by including it in the request body.
      Useful for simulating different conditions on a known day.

      POST {
        "vessel_id": "S21",
        "noon_day":  136,
        "wind_scale": 6       ← override just this field
      }

    Counterfactual (UWC+PP):
      The response always includes a counterfactual prediction showing
      how much fuel would be saved if UWC+PP were performed right now
      (days_since_hull_clean = 0, days_since_prop_polish = 0).
    """
    try:
        body = json.loads(event.get('body') or '{}')
    except Exception:
        return err(400, 'Invalid JSON body')

    vessel_id = body.get('vessel_id')
    if not vessel_id:
        return err(400, 'vessel_id is required')

    noon_day = safe_float(body.get('noon_day'))

    # ── Fetch DynamoDB row for this noon_day ──────────────────────────────────
    row_data = {}
    if noon_day is not None:
        all_rows = query_vessel(vessel_id)
        # Find the row whose NOON_UTC matches noon_day (within ±0.5 day)
        matched = [r for r in all_rows
                   if safe_float(r.get('NOON_UTC')) is not None
                   and abs(safe_float(r.get('NOON_UTC')) - noon_day) < 0.5]
        if not matched:
            return err(404, f'No data found for vessel {vessel_id} on noon_day {noon_day}')
        row_data = matched[0]

    # ── Resolve feature values (DynamoDB row → override with body if provided) ─
    def get(field, default=None):
        # body takes precedence over DynamoDB row
        if field in body:
            v = body[field]
            return float(v) if v is not None else default
        return safe_float(row_data.get(field), default)

    speed_kn          = get('AVG_SPEED',            get('speed_kn', 15.0))
    stw               = get('SPEED_THROUGH_WATER',  speed_kn)
    wind_scale        = get('WIND_SCALE',            3.0)
    wind_speed        = get('WIND_SPEED',            10.0)
    sea_height        = get('SEA_HEIGHT',            1.0)
    swell_height      = get('SWELL_HEIGHT',          0.5)
    sea_water_temp    = get('SEA_WATER_TEMP',        20.0)
    water_depth       = get('WATER_DEPTH',           100.0)
    diff_stw_sog_slip = get('DIFF_STW_SOG_SLIP',    0.0)
    full_spd_stw_slip = get('FULL_SPD_STW_SLIP',    8.0)
    hours_full_speed  = get('HOURS_FULL_SPEED',      22.0)
    hours_total       = get('HOURS_TOTAL',           24.0)
    fore_draft        = get('FORE_DRAFT',            13.5)
    aft_draft         = get('AFTER_DRAFT',           13.5)
    mid_draft         = get('MID_DRAFT',             (fore_draft + aft_draft) / 2)

    # ── Load maintenance history (events up to noon_day only) ────────────────
    maint_rows = query_maintenance(vessel_id)
    maint_rows_sorted = sorted(
        [m for m in maint_rows
         if noon_day is None or safe_float(m.get('event_day'), 0) <= noon_day],
        key=lambda x: safe_float(x.get('event_day'), 0),
    )

    try:
        bundle = _load_model()
        model  = bundle['model']
    except Exception as e:
        return err(500, f'Model load failed: {e}')

    # ── Baseline prediction ───────────────────────────────────────────────────
    X = _build_features(
        vessel_id, speed_kn, stw,
        wind_scale, wind_speed, sea_height, swell_height,
        sea_water_temp, water_depth, diff_stw_sog_slip, full_spd_stw_slip,
        hours_full_speed, hours_total, fore_draft, aft_draft, mid_draft,
        maint_rows_sorted,
        as_of_day=noon_day,
    )
    predicted = round(float(model.predict(X)[0]), 2)

    # ── Counterfactual: simulate UWC+PP performed right now ──────────────────
    X_cf = _build_features(
        vessel_id, speed_kn, stw,
        wind_scale, wind_speed, sea_height, swell_height,
        sea_water_temp, water_depth, diff_stw_sog_slip, full_spd_stw_slip,
        hours_full_speed, hours_total, fore_draft, aft_draft, mid_draft,
        maint_rows_sorted,
        as_of_day=noon_day,
        override_days_since_hull_clean=0.0,
        override_days_since_prop_polish=0.0,
    )
    predicted_cf  = round(float(model.predict(X_cf)[0]), 2)
    cf_saving     = round(predicted - predicted_cf, 2)
    cf_saving_pct = round(cf_saving / predicted * 100, 1) if predicted > 0 else None

    # Annual saving estimate (300 sea days/year, bunker $600/MT)
    annual_saving_mt  = round(cf_saving * 300, 1)
    annual_saving_usd = round(cf_saving * 300 * 600, 0)

    # Days since last maintenance (for context)
    days_since_hull  = None
    days_since_prop  = None
    if noon_day is not None:
        for m in reversed(maint_rows_sorted):
            eday  = safe_float(m.get('event_day'), 0)
            etype = str(m.get('event_type', ''))
            if days_since_hull is None and etype in HULL_CLEAN_TYPES:
                days_since_hull = round(noon_day - eday, 0)
            if days_since_prop is None and etype in PROP_POLISH_TYPES:
                days_since_prop = round(noon_day - eday, 0)
            if days_since_hull is not None and days_since_prop is not None:
                break

    return resp(200, {
        'vessel_id': vessel_id,
        'noon_day':  noon_day,
        'model':     'xgboost_v3_hybrid',
        'input_used': {
            'avg_speed_kn':    speed_kn,
            'stw_kn':          stw,
            'wind_scale':      wind_scale,
            'sea_height':      sea_height,
            'fore_draft':      fore_draft,
            'aft_draft':       aft_draft,
            'hours_full_speed': hours_full_speed,
            'days_since_hull_clean':  days_since_hull,
            'days_since_prop_polish': days_since_prop,
        },
        'predicted_consumption_mt': predicted,
        'counterfactual_uwc_pp': {
            'description':              'Predicted consumption if UWC+PP were performed now (days_since=0)',
            'predicted_consumption_mt': predicted_cf,
            'fuel_saving_mt_per_day':   cf_saving,
            'saving_pct':               cf_saving_pct,
            'est_annual_saving_mt':     annual_saving_mt,
            'est_annual_saving_usd':    annual_saving_usd,
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
