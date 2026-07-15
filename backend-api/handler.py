"""
Ship Performance Analysis API
Lambda handler - reads directly from DynamoDB
"""
import json
import os
import math
import pickle
import ssl
import sys
import time
import threading
import urllib.request
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
import lightgbm  # Required to deserialize the v5 LightGBM ensemble member.
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestRegressor

# ── Model loading (module-level: loaded once per Lambda container) ────────────
_MODEL_BUNDLE = None


def _load_model():
    """Load the v5 VLSFO-equivalent 24-hour ensemble artifact once."""
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is not None:
        return _MODEL_BUNDLE
    model_path = os.path.join(os.path.dirname(__file__), 'model', 'model_v5_final.pkl')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with open(model_path, 'rb') as f:
            _MODEL_BUNDLE = pickle.load(f)
    if _MODEL_BUNDLE.get('version') != 'v5_final':
        raise ValueError('Expected v5_final model artifact')
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

# Fuel LCV constants (MJ/kg) — used to convert whichever fuel a day used into
# a VLSFO-equivalent Daily FOC (competition-specified formula).
FUEL_LCV = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}
LCV_VLSFO = 40.2
FUEL_COLS = list(FUEL_LCV.keys())


def get_daily_foc(r):
    """Daily FOC (VLSFO-equivalent, normalized to 24h) for one noon-report
    row, or (None, None) if the row doesn't qualify (not full-speed, no
    valid fuel column)."""
    hfs = safe_float(r.get('HOURS_FULL_SPEED'), 0)
    if hfs < 22:
        return None, None
    best_col, best_val = None, 0
    for fc in FUEL_COLS:
        v = safe_float(r.get(fc), 0)
        if v > best_val:
            best_val, best_col = v, fc
    if best_col is None or best_val <= 0:
        return None, None
    lcv = FUEL_LCV.get(best_col, LCV_VLSFO)
    vlsfo_equiv = best_val * lcv / LCV_VLSFO
    daily_foc = vlsfo_equiv / hfs * 24.0
    return round(daily_foc, 2), best_col.replace('ME_FULLSPEED_CONSUMP_', '')

# ── DynamoDB setup ──────────────────────────────────────────────────────────
REGION          = os.environ.get('AWS_REGION', 'us-east-1')
VESSEL_TABLE         = os.environ.get('VESSEL_TABLE',        'ship-analysis-dev-vessel-data')
MAINT_TABLE          = os.environ.get('MAINT_TABLE',         'ship-analysis-dev-maintenance-events')
FLEET_SUMMARY_TABLE  = os.environ.get('FLEET_SUMMARY_TABLE', 'ship-analysis-dev-fleet-summary')
FUEL_ANOMALY_TABLE   = os.environ.get('FUEL_ANOMALY_TABLE',  'ship-analysis-dev-fuel-anomaly-cause')

ddb = boto3.resource('dynamodb', region_name=REGION)
vessel_tbl       = ddb.Table(VESSEL_TABLE)
maint_tbl        = ddb.Table(MAINT_TABLE)
fleet_summary_tbl = ddb.Table(FLEET_SUMMARY_TABLE)
fuel_anomaly_tbl  = ddb.Table(FUEL_ANOMALY_TABLE)

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

    # Prime the fuel-anomaly-cause fleet models (two RandomForests + a SHAP
    # explainer, fit on all 12 training vessels) — same reasoning as above.
    try:
        _fleet_fuel_anomaly_models()
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
        if sub == 'fuel-anomaly-cause':
            return get_fuel_anomaly_cause(vessel_id, event)

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

    def numeric_values(field):
        return [value for r in rows if (value := safe_float(r.get(field))) is not None]

    speeds = numeric_values('AVG_SPEED')
    consump = numeric_values('ME_CONSUMPTION')
    stw_list = numeric_values('SPEED_THROUGH_WATER')

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
        # Return all vt_fd.csv fields (convert uppercase keys to lowercase)
        # EXCLUDING speed_loss — that's served separately by get_speed_loss endpoint
        record = {}
        for k, v in r.items():
            if k not in ['vessel_id', 'sort_key', 'speed_loss']:
                # Convert NOON_UTC -> noon_utc, AVG_SPEED -> avg_speed, etc.
                key = k.lower()
                record[key] = safe_float(v) if isinstance(v, (int, float, str)) and v not in [None, ''] else v
        records.append(record)

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
    # get_daily_foc is the module-level helper (shared with
    # _fleet_degradation_rates / get_speed_loss_attribution).

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

        # FOC-based speed loss. Not clamped to 0 — a negative value is a real
        # result (that day's FOC beat the baseline) and callers rely on
        # seeing it rather than a flattened 0 (see adapter.ts's speedLossPct mapping).
        baseline_foc = get_baseline_foc(cr['cycle'], rpm)
        if baseline_foc and baseline_foc > 0:
            foc_sl_pct = (cr['daily_foc_vlsfo'] - baseline_foc) / baseline_foc * 100
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
                stw_sl_pct = (ref_stw - stw) / ref_stw * 100
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

    # Layer 3: ISO 19030-2 (9-correction + per-vessel quantile/DD baseline).
    # `speed_loss` is backfilled directly onto each vessel_tbl row offline
    # (add_speedloss_column_full_iso.py + import_vt_fd_to_dynamodb.py) — read
    # it straight from the row instead of recomputing, and keep None (non-
    # steady-state, never backfilled) and negative values (outperformed
    # baseline) as-is rather than flattening them.
    iso_speedloss_timeline = sorted(
        (
            {
                'noon_day': safe_float(r.get('NOON_UTC'), 0),
                'speed_loss_pct': safe_float(r.get('SPEED_LOSS')),
                'sort_key': r.get('sort_key'),
                'row_index': safe_float(r.get('row_index')),
                'is_valid': r.get('SPEED_LOSS') is not None,  # true = has speed_loss, false = null/missing
            }
            for r in rows
        ),
        key=lambda p: p['noon_day'],
    )

    return resp(200, {
        'vessel_id': vessel_id,
        'method': 'ISO19030_FOC_normalized + STW_RPM_baseline',
        'filter_criteria': {
            'wind_scale_max': 4,
            'hours_full_speed_min': 22,
        },
        # Layer 3: ISO 19030-2, precomputed — see comment above. Preferred by
        # the frontend adapter over Layers 1/2 when present.
        'iso_speedloss_timeline': iso_speedloss_timeline,
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
    sorted by day. This is a propeller-condition metric (theoretical vs.
    actual advance per revolution) — used for the propeller channel."""
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


def _calm_foc_series(vessel_id):
    """Daily FOC (VLSFO-equivalent, same as get_speed_loss()'s Layer 1)
    filtered to calm/steady-state days. FOC is driven by total resistance —
    hull fouling's actual physical signature (same RPM needs more fuel to
    push through a dirtier hull) — used for the hull channel. FULL_SPD_STW_SLIP
    is a propeller-advance-efficiency metric, not a hull-resistance metric,
    so it's the wrong variable to calibrate hull degradation against even
    though it was the one originally used here."""
    recs = []
    for r in query_vessel(vessel_id):
        day = safe_float(r.get('NOON_UTC'))
        ws  = safe_float(r.get('WIND_SCALE'))
        hfs = safe_float(r.get('HOURS_FULL_SPEED'))
        if day is None or ws is None or hfs is None or ws > 4 or hfs < 22:
            continue
        foc, _fuel = get_daily_foc(r)
        if foc is None or foc < 10:
            continue
        recs.append((day, foc))
    recs.sort()
    return recs


def _cycle_index(day, boundaries):
    idx = 0
    for b in boundaries:
        if day >= b:
            idx += 1
    return idx


def _fleet_degradation_rates():
    """Fleet-calibrated hull / propeller degradation rate, pooled across all
    12 training vessels — hull uses Daily FOC (Speed-Loss-equivalent, %
    relative to each cycle's own baseline), propeller uses FULL_SPD_STW_SLIP
    (percentage points relative to baseline). Different metrics on purpose:
    slip is a propeller-advance-efficiency indicator, FOC/resistance is the
    hull-fouling signature — using slip for both would silently attribute
    hull degradation to the wrong physical quantity.

    Why pooled instead of per-ship/per-event: a single ship's single
    maintenance cycle is dominated by day-to-day operational noise (R² ~0.07
    fitting either metric vs. days-since-cleaning per cycle — the trend is
    real but weak relative to noise). Pooling thousands of calm-condition
    records per channel across the whole fleet turns that weak per-cycle
    signal into a statistically solid population-level rate: hull
    ~0.7%/30d (t≈8), propeller ~0.083%/30d (t≈6) — both far past the |t|>2
    significance bar. (The hull figure lines up with the ~20%/severe-fouling
    order of magnitude the competition brief itself cites for hull/propeller
    over a multi-year neglected cycle.) This is the number that actually
    answers "how much of speed loss is attributable to hull vs. propeller
    fouling", not any single event's noisy before/after snapshot.

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

    def pooled_rate(type_set, series_fn, relative):
        """relative=True: pool (value-baseline)/baseline*100 (FOC, cross-ship/
        cross-fuel scale varies so normalize to % of baseline). relative=False:
        pool value-baseline directly (slip is already a percentage, its own
        scale is comparable across ships)."""
        pooled_x, pooled_y = [], []
        for vid in TRAIN_VESSELS:
            recs  = series_fn(vid)
            maint = query_maintenance(vid)
            boundaries = sorted(
                safe_float(m.get('event_day'), 0)
                for m in maint if str(m.get('event_type', '')) in type_set
            )
            cycles = defaultdict(list)
            for day, val in recs:
                cycles[_cycle_index(day, boundaries)].append((day, val))

            for idx, cyc in cycles.items():
                if idx == 0 or len(cyc) < 10:
                    continue  # skip unanchored first cycle + too-sparse cycles
                cyc.sort()
                start_day = boundaries[idx - 1]
                n_base = max(3, len(cyc) // 7)
                baseline = mean([v for _, v in cyc[:n_base]])
                if relative and baseline == 0:
                    continue
                for d, v in cyc:
                    pooled_x.append(d - start_day)
                    pooled_y.append((v - baseline) / baseline * 100 if relative else v - baseline)

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
        'hull': {
            **pooled_rate(HULL_CLEAN_TYPES, _calm_foc_series, relative=True),
            'metric': 'speed_loss_pct_foc_relative_to_cycle_baseline',
        },
        'propeller': {
            **pooled_rate(PROP_POLISH_TYPES, _calm_slip_series, relative=False),
            'metric': 'full_spd_stw_slip_pct_points',
        },
        'calibrated_on_vessels': len(TRAIN_VESSELS),
        'method': 'pooled_linear_regression_vs_days_since_cleaning',
    }
    _cache_set(cache_key, result)
    return result


# ── Fuel anomaly root-cause classification ─────────────────────────────────
# Ported from notebooks/anomaly_analysis.ipynb §6-9: a baseline model that
# only sees operating conditions predicts "expected" daily fuel consumption;
# the gap between actual and expected (residual) is what a second model +
# SHAP decompose into hull / propeller / weather contributions, per day.

FUEL_ANOMALY_OP_FEATURES = [
    'ME_AVG_RPM', 'SPEED_THROUGH_WATER', 'AVG_SPEED', 'FORE_DRAFT', 'AFTER_DRAFT',
    'CARGO_ON_BOARD', 'WIND_SCALE', 'SEA_HEIGHT', 'SWELL_HEIGHT', 'SEA_WATER_TEMP',
]
FUEL_ANOMALY_CAUSE_FEATURES = [
    'days_since_hull_clean', 'days_since_prop_polish', 'propeller_condition_code',
    'WIND_SCALE', 'SEA_HEIGHT', 'SWELL_HEIGHT', 'SEA_WATER_TEMP',
]
FUEL_ANOMALY_CAUSE_GROUPS = {
    '船殼汙損': ['days_since_hull_clean'],
    '螺旋槳汙損': ['days_since_prop_polish', 'propeller_condition_code'],
    '天候': ['WIND_SCALE', 'SEA_HEIGHT', 'SWELL_HEIGHT', 'SEA_WATER_TEMP'],
}
FUEL_ANOMALY_THRESHOLD_PCT = 15
PROPELLER_CONDITION_CODE = {'Poor': 0, 'Fair': 1, 'Good': 2, 'Unknown': -1}

# 船殼/螺旋槳汙損可以靠排程維護（清船殼、拋光螺旋槳）處理，天候不行——
# ROI 估算只把「可維修」根因算進省下的油耗，天候造成的異常天數只統計不計入 $。
FUEL_ANOMALY_MAINTAINABLE_CAUSES = {'船殼汙損', '螺旋槳汙損'}

# 觀察到的 DD（Dry Dock）週期：10 艘訓練船的 DD 事件都落在 event_day 769–985
# （平均 ~877），且每一筆 DD 紀錄的 propeller_condition/hull_fouling_type/
# hull_coating_condition/cavitation_found 全部是空的——代表 DD 在這份資料裡是
# 船級社定期特檢週期，不是被觀測到的船況觸發的。跟 PP/UWC 不同，沒有任何船況
# 訊號可以拿來從油耗異常歸因推論「該不該排 DD」，只能用固定週期提醒。
FLEET_DD_INTERVAL_DAYS = 877


def _recommend_maintenance_action(hull_confident_days, propeller_confident_days):
    """PP/UWC/UWC+PP 直接對應到已經判定出的根因——船殼汙損就該 UWC、螺旋槳
    汙損就該 PP，這是物理上固定的映射，不是另外學一個分類器。真正不確定、
    需要模型判斷的是「根因是什麼」（cause_model 的 SHAP 分解），這裡只是把
    結果轉成動作。DD 不適用這套推論，見 FLEET_DD_INTERVAL_DAYS 說明。"""
    if hull_confident_days and propeller_confident_days:
        return 'UWC+PP'
    if hull_confident_days:
        return 'UWC'
    if propeller_confident_days:
        return 'PP'
    return None


def _days_since_maint_type(maint_rows, noon_day, type_set):
    """Days since the most recent maintenance event whose type is in
    type_set, as of noon_day. No prior event of that type → treat noon_day
    itself as the elapsed count (same fallback as get_speed_loss_attribution)."""
    prior_days = [
        safe_float(m.get('event_day'), 0) for m in maint_rows
        if str(m.get('event_type', '')) in type_set and safe_float(m.get('event_day'), 1e18) <= noon_day
    ]
    return (noon_day - max(prior_days)) if prior_days else noon_day


def _last_propeller_condition(maint_rows, noon_day):
    prior = [m for m in maint_rows if safe_float(m.get('event_day'), 1e18) <= noon_day and m.get('propeller_condition')]
    if not prior:
        return 'Unknown'
    last = max(prior, key=lambda m: safe_float(m.get('event_day'), 0))
    return last.get('propeller_condition') or 'Unknown'


def _fuel_anomaly_rows(vessel_id, rows=None, maint_rows=None):
    """Build the per-day feature table (operating conditions + maintenance-
    derived cause features + daily_foc) for one vessel's calm-condition days.
    Shared by fleet model training and per-vessel inference so both use the
    exact same feature definitions."""
    rows = query_vessel(vessel_id) if rows is None else rows
    maint_rows = query_maintenance(vessel_id) if maint_rows is None else maint_rows

    out = []
    for r in rows:
        ws  = safe_float(r.get('WIND_SCALE'))
        hfs = safe_float(r.get('HOURS_FULL_SPEED'))
        day = safe_float(r.get('NOON_UTC'))
        if ws is None or hfs is None or day is None or ws > 4 or hfs < 22:
            continue
        daily_foc, _fuel = get_daily_foc(r)
        if daily_foc is None or daily_foc < 10:
            continue

        op_vals = {f: safe_float(r.get(f)) for f in FUEL_ANOMALY_OP_FEATURES}
        if any(v is None for v in op_vals.values()):
            continue

        prop_cond = _last_propeller_condition(maint_rows, day)
        row = {
            'noon_day': day,
            'daily_foc': daily_foc,
            'days_since_hull_clean':  _days_since_maint_type(maint_rows, day, HULL_CLEAN_TYPES),
            'days_since_prop_polish': _days_since_maint_type(maint_rows, day, PROP_POLISH_TYPES),
            'propeller_condition_code': PROPELLER_CONDITION_CODE.get(prop_cond, -1),
            **op_vals,
        }
        out.append(row)
    return out


def _fleet_fuel_anomaly_models():
    """Fleet-calibrated fuel-anomaly models, cached (queries all 12 training
    vessels — expensive, don't recompute per request):

    1. baseline_model: operating conditions (RPM/STW/draft/cargo/weather) →
       daily_foc. Deliberately blind to maintenance state, so its residual
       (actual − predicted) is attributable to whatever it *can't* see.
    2. cause_model: maintenance + weather features → residual_pct. Its SHAP
       values decompose each anomalous day's residual into hull/propeller/
       weather contributions.
    """
    cache_key = 'fleet:fuel_anomaly_models'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    TRAIN_VESSELS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12']
    all_rows = []
    for vid in TRAIN_VESSELS:
        all_rows.extend(_fuel_anomaly_rows(vid))

    if len(all_rows) < 50:
        result = {'baseline_model': None, 'cause_model': None, 'explainer': None, 'r2': None, 'n_records': len(all_rows)}
        _cache_set(cache_key, result)
        return result

    df = pd.DataFrame(all_rows)

    X_op = df[FUEL_ANOMALY_OP_FEATURES]
    y = df['daily_foc']
    baseline_model = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=42, n_jobs=-1)
    baseline_model.fit(X_op, y)
    # In-sample R² — a quick sanity check this cache entry is healthy, not a
    # held-out validation metric (the notebook's train/test split is what's
    # used to actually validate the method; see notebooks/anomaly_analysis.ipynb).
    r2 = float(baseline_model.score(X_op, y))

    df['predicted_foc'] = baseline_model.predict(X_op)
    df['residual_pct'] = (df['daily_foc'] - df['predicted_foc']) / df['predicted_foc'] * 100

    X_cause = df[FUEL_ANOMALY_CAUSE_FEATURES]
    cause_model = RandomForestRegressor(n_estimators=300, max_depth=6, random_state=42, n_jobs=-1)
    cause_model.fit(X_cause, df['residual_pct'])
    explainer = shap.TreeExplainer(cause_model)

    result = {
        'baseline_model': baseline_model,
        'cause_model': cause_model,
        'explainer': explainer,
        'r2': round(r2, 4),
        'n_records': len(df),
        'calibrated_on_vessels': len(TRAIN_VESSELS),
    }
    _cache_set(cache_key, result)
    return result


def _fuel_anomaly_roi(anomaly_items, total_days_analyzed):
    """Split anomaly days into 可維修 (hull/propeller — actionable via a
    cleaning/drydock schedule) vs 天候 (not actionable), and estimate the $
    upside of fixing the maintainable share.

    Only confident (`cause_model_agrees`), over-consuming (`direction=='over'`)
    maintainable-cause days count toward the $ estimate — weather-driven or
    unconfident days aren't something a maintenance schedule can fix, and
    'under' days aren't excess consumption to begin with. The per-day excess
    is spread across `total_days_analyzed` (not just the anomaly days) to get
    an average daily waste rate representative of the whole observed period,
    then annualized and priced the same way as predict_fuel()'s counterfactual
    (`_calculate_energy_pricing`), so the $ figure is comparable across
    endpoints.

    `anomaly_items` — list of dicts with normalized keys: primary_cause,
    direction, cause_model_agrees, daily_foc_actual, daily_foc_expected.
    """
    maintainable_days = 0
    maintainable_confident_days = 0
    hull_confident_days = 0
    propeller_confident_days = 0
    weather_days = 0
    weather_confident_days = 0
    excess_mt_total = 0.0

    for it in anomaly_items:
        cause = it.get('primary_cause')
        agrees = bool(it.get('cause_model_agrees'))
        if cause in FUEL_ANOMALY_MAINTAINABLE_CAUSES:
            maintainable_days += 1
            if agrees:
                maintainable_confident_days += 1
                if cause == '船殼汙損':
                    hull_confident_days += 1
                elif cause == '螺旋槳汙損':
                    propeller_confident_days += 1
                if it.get('direction') == 'over':
                    actual = safe_float(it.get('daily_foc_actual'), 0.0)
                    expected = safe_float(it.get('daily_foc_expected'), 0.0)
                    excess_mt_total += max(0.0, actual - expected)
        elif cause == '天候':
            weather_days += 1
            if agrees:
                weather_confident_days += 1

    avg_excess_mt_per_day = (excess_mt_total / total_days_analyzed) if total_days_analyzed else 0.0
    pricing = _calculate_energy_pricing(avg_excess_mt_per_day, 'VLSFO_equivalent', LCV_VLSFO)

    return {
        'maintainable_vs_weather': {
            'maintainable_days': maintainable_days,
            'maintainable_confident_days': maintainable_confident_days,
            'weather_days': weather_days,
            'weather_confident_days': weather_confident_days,
        },
        'recommended_action': _recommend_maintenance_action(hull_confident_days, propeller_confident_days),
        'roi': {
            'avg_excess_fuel_mt_per_day': round(avg_excess_mt_per_day, 3),
            'annual_excess_fuel_mt': round(avg_excess_mt_per_day * SEA_DAYS_PER_YEAR, 1),
            'annual_saving_usd_if_fixed': pricing['annual_saving_usd'],
            'basis': 'confident, over-consuming, maintainable-cause (hull/propeller) days only; weather excluded',
            'energy_pricing': pricing,
        },
    }


def _fuel_anomaly_from_precomputed(vessel_id, limit):
    """Try the precomputed table first (populated by
    precompute_fuel_anomaly.py directly from CSV — deliberately bypasses
    query_vessel()/the vessel-data table, which has duplicate noon-report
    items from an earlier double-upload). Returns None if the table is
    empty/unavailable for this vessel, so the caller falls back to live
    computation."""
    try:
        resp_page = fuel_anomaly_tbl.query(
            KeyConditionExpression=Key('vessel_id').eq(vessel_id),
            ScanIndexForward=False,  # newest noon_day first
        )
        items = resp_page.get('Items', [])
    except Exception:
        return None
    if not items:
        return None

    # noon_day=-1 is a sentinel meta item (see precompute_fuel_anomaly.py)
    # holding fleet-wide stats that don't fit the per-day anomaly shape.
    meta = next((it for it in items if safe_float(it.get('noon_day')) == -1), None)
    items = [it for it in items if safe_float(it.get('noon_day')) != -1]

    cause_breakdown: dict = {}
    confident_cause_breakdown: dict = {}
    for it in items:
        cause = it.get('primary_cause')
        if cause:
            cause_breakdown[cause] = cause_breakdown.get(cause, 0) + 1
            if it.get('cause_model_agrees'):
                confident_cause_breakdown[cause] = confident_cause_breakdown.get(cause, 0) + 1

    total_days_analyzed = int(safe_float(meta.get('total_days_analyzed'), 0)) if meta else 0
    roi = _fuel_anomaly_roi(items, total_days_analyzed)

    anomalies_out = [{
        'noon_day': safe_float(it.get('noon_day')),
        'daily_foc_actual': safe_float(it.get('daily_foc_actual')),
        'daily_foc_expected': safe_float(it.get('daily_foc_expected')),
        'residual_pct': safe_float(it.get('residual_pct')),
        'direction': it.get('direction'),
        'primary_cause': it.get('primary_cause'),
        'primary_cause_contribution_pct': safe_float(it.get('primary_cause_contribution_pct')),
        'cause_model_agrees': bool(it.get('cause_model_agrees')) if it.get('cause_model_agrees') is not None else None,
        'days_since_hull_clean': int(safe_float(it.get('days_since_hull_clean'), 0)),
        'days_since_prop_polish': int(safe_float(it.get('days_since_prop_polish'), 0)),
    } for it in items[:limit]]

    return resp(200, {
        'vessel_id': vessel_id,
        'method': 'residual_shap_classification_precomputed',
        'baseline_model_r2': safe_float(meta.get('baseline_model_r2')) if meta else None,
        'anomaly_threshold_pct': FUEL_ANOMALY_THRESHOLD_PCT,
        'summary': {
            'total_days_analyzed': total_days_analyzed,
            'anomaly_days': len(items),
            'cause_breakdown': cause_breakdown,
            'confident_cause_breakdown': confident_cause_breakdown,
            **roi,
        },
        'anomalies': anomalies_out,
    })


def get_fuel_anomaly_cause(vessel_id, event):
    """
    每日油耗異常根因分類：先用只看操作條件的模型算出「這個操作條件下預期油耗」，
    殘差（實際−預期）超過門檻的日子視為異常，再用 SHAP 把殘差拆解成船殼/螺旋槳/
    天候三類貢獻，取貢獻最大的當這一天的主因。方法完整推導見
    notebooks/anomaly_analysis.ipynb §6-9。

    優先讀 ship-analysis-dev-fuel-anomaly-cause 表（precompute_fuel_anomaly.py
    直接從 CSV 算出、批次寫入，繞開 vessel-data 表現有的重複資料問題）；
    表是空的（還沒跑過批次腳本）才即時計算。
    """
    qs = event.get('queryStringParameters') or {}
    try:
        limit = int(qs.get('limit', 20))
    except (TypeError, ValueError):
        limit = 20

    precomputed = _fuel_anomaly_from_precomputed(vessel_id, limit)
    if precomputed is not None:
        return precomputed

    rows = query_vessel(vessel_id)
    if not rows:
        return err(404, f'Vessel {vessel_id} not found')
    maint_rows = query_maintenance(vessel_id)

    models = _fleet_fuel_anomaly_models()
    if models['baseline_model'] is None:
        return err(502, 'fuel-anomaly-cause: fleet models unavailable (insufficient calibration data)')

    qs = event.get('queryStringParameters') or {}
    try:
        limit = int(qs.get('limit', 20))
    except (TypeError, ValueError):
        limit = 20

    vessel_rows = _fuel_anomaly_rows(vessel_id, rows=rows, maint_rows=maint_rows)
    if not vessel_rows:
        return resp(200, {
            'vessel_id': vessel_id, 'method': 'residual_shap_classification',
            'baseline_model_r2': models['r2'], 'anomaly_threshold_pct': FUEL_ANOMALY_THRESHOLD_PCT,
            'summary': {
                'total_days_analyzed': 0, 'anomaly_days': 0, 'cause_breakdown': {},
                'confident_cause_breakdown': {}, **_fuel_anomaly_roi([], 0),
            },
            'anomalies': [],
        })

    df = pd.DataFrame(vessel_rows)
    X_op = df[FUEL_ANOMALY_OP_FEATURES]
    df['predicted_foc'] = models['baseline_model'].predict(X_op)
    df['residual_pct'] = (df['daily_foc'] - df['predicted_foc']) / df['predicted_foc'] * 100
    df['direction'] = np.select(
        [df['residual_pct'] > FUEL_ANOMALY_THRESHOLD_PCT, df['residual_pct'] < -FUEL_ANOMALY_THRESHOLD_PCT],
        ['over', 'under'], default='normal',
    )

    anomalies_df = df[df['direction'] != 'normal'].copy()
    cause_breakdown = {}
    confident_cause_breakdown = {}
    if len(anomalies_df):
        X_cause = anomalies_df[FUEL_ANOMALY_CAUSE_FEATURES]
        # cause_model 自己對 residual_pct 的預測值（= SHAP 貢獻加總 + base_value）。
        # 這是「候選根因特徵能解釋的部分」，不等於 baseline_model 算出的真實
        # residual_pct——cause_model 不是完美模型，兩者方向可能不一致，尤其
        # 天候雜訊大的天。方向一致時 primary_cause 才可信，用
        # cause_model_agrees 明確標示，不要讓不一致的分類悄悄混進統計。
        cause_model_pred = models['cause_model'].predict(X_cause)
        anomalies_df['cause_model_predicted_residual_pct'] = cause_model_pred
        anomalies_df['cause_model_agrees'] = np.sign(cause_model_pred) == np.sign(anomalies_df['residual_pct'])

        shap_values = models['explainer'].shap_values(X_cause)
        shap_df = pd.DataFrame(shap_values, columns=FUEL_ANOMALY_CAUSE_FEATURES, index=anomalies_df.index)
        group_shap = pd.DataFrame({
            group: shap_df[cols].sum(axis=1) for group, cols in FUEL_ANOMALY_CAUSE_GROUPS.items()
        })
        # 對「燒太多」(over) 是貢獻最正的那組主導；對「燒太少」(under) 是貢獻
        # 最負的那組（把預期往下拉最多）主導——兩者統一用「絕對值最大」判斷，
        # 用 apply 逐列找出來，比矩陣花式索引直覺、不怕 index/位置對不齊。
        primary_cause = group_shap.abs().idxmax(axis=1)
        primary_cause_shap = group_shap.apply(lambda row: row[primary_cause[row.name]], axis=1)
        anomalies_df['primary_cause'] = primary_cause
        anomalies_df['primary_cause_shap'] = primary_cause_shap
        cause_breakdown = anomalies_df['primary_cause'].value_counts().to_dict()
        confident_cause_breakdown = anomalies_df.loc[anomalies_df['cause_model_agrees'], 'primary_cause'].value_counts().to_dict()

    # ROI 要用「全部異常天」算，不能被下面的 limit 截斷影響（截斷只是給
    # anomalies[] 顯示用的，summary/ROI 要反映完整分析區間）。
    roi_items = [{
        'primary_cause': r.get('primary_cause'),
        'direction': r['direction'],
        'cause_model_agrees': bool(r.get('cause_model_agrees', False)),
        'daily_foc_actual': r['daily_foc'],
        'daily_foc_expected': r.get('predicted_foc'),
    } for _, r in anomalies_df.iterrows()]
    roi = _fuel_anomaly_roi(roi_items, len(df))

    anomalies_df = anomalies_df.sort_values('noon_day', ascending=False).head(limit)

    anomalies_out = []
    for _, r in anomalies_df.iterrows():
        anomalies_out.append({
            'noon_day': r['noon_day'],
            'daily_foc_actual': round(r['daily_foc'], 2),
            'daily_foc_expected': round(r['predicted_foc'], 2),
            'residual_pct': round(r['residual_pct'], 2),
            'direction': r['direction'],
            'primary_cause': r.get('primary_cause'),
            'primary_cause_contribution_pct': round(r['primary_cause_shap'], 2) if 'primary_cause_shap' in r else None,
            'cause_model_agrees': bool(r['cause_model_agrees']) if 'cause_model_agrees' in r else None,
            'days_since_hull_clean': round(r['days_since_hull_clean']),
            'days_since_prop_polish': round(r['days_since_prop_polish']),
        })

    return resp(200, {
        'vessel_id': vessel_id,
        'method': 'residual_shap_classification',
        'baseline_model_r2': models['r2'],
        'anomaly_threshold_pct': FUEL_ANOMALY_THRESHOLD_PCT,
        'summary': {
            'total_days_analyzed': len(df),
            'anomaly_days': len(df[df['direction'] != 'normal']),
            'cause_breakdown': cause_breakdown,
            'confident_cause_breakdown': confident_cause_breakdown,
            **roi,
        },
        'anomalies': anomalies_out,
    })


def _vessel_excess_fuel_mt_per_day(vessel_id, rows=None, maint_rows=None):
    """Model-grounded current excess fuel rate (MT/day) for one vessel:
    average of (actual − baseline-model-expected) daily FOC over its most
    recent qualifying (calm-condition) days, floored at 0.

    Replaces the old `avg_consumption_mt * (slip% / 100) * 1.8` heuristic —
    that 1.8 multiplier has no documented derivation anywhere in the repo
    (checked git blame back to the commit that introduced it); this uses the
    same baseline model as get_fuel_anomaly_cause() instead, so "excess fuel"
    means the same thing everywhere in the API. Returns None if there isn't
    enough calm-condition data to compute it.
    """
    models = _fleet_fuel_anomaly_models()
    if models['baseline_model'] is None:
        return None

    vessel_rows = _fuel_anomaly_rows(vessel_id, rows=rows, maint_rows=maint_rows)
    if not vessel_rows:
        return None

    df = pd.DataFrame(vessel_rows).sort_values('noon_day')
    recent = df.tail(90)  # same 90-day recency window used elsewhere in this file
    predicted = models['baseline_model'].predict(recent[FUEL_ANOMALY_OP_FEATURES])
    residual_mt = recent['daily_foc'].to_numpy() - predicted
    return max(0.0, float(np.mean(residual_mt)))


def get_speed_loss_attribution(vessel_id, event):
    """
    Speed Loss 歸因分析：用「艦隊校準劣化速率」模型分開估算船殼與螺旋槳個別
    貢獻，取代舊版「事件前後 ±30 天快照平均」的做法。船殼、螺旋槳用不同物理量：

    - 船殼通道：Daily FOC（跟 get_speed_loss() Layer 1 同一套，VLSFO 當量）—
      船殼阻力的直接訊號是「同轉速下要燒更多油」，不是滑差。
    - 螺旋槳通道：FULL_SPD_STW_SLIP（螺旋槳理論前進 vs 實際前進的差）— 這才是
      滑差真正對應的物理量。

    （這兩個通道原本都用滑差校準，是錯的——滑差本質是螺旋槳效率指標，拿它去
    估算船殼貢獻，物理上量錯東西了。）

    為什麼要換方法（而不是原始事件前後直接比較）：單一事件、單一船的
    before/after 快照比較，被短期操作雜訊（天候、載重、清潔後試俥等）嚴重
    污染——實測過三種改法（天候篩選、RPM 配對、週期邊界快照），「清潔後效能
    反而變差」這種違反物理常識的比例都還停在 40-60% 區間。真正乾淨的訊號，
    是把全船隊的資料 pool 起來做迴歸（見 `_fleet_degradation_rates()`）：
    單一週期的 R² 只有 ~0.07（雜訊蓋過趨勢），但 pool 起來後 n>3000，兩個
    通道的劣化速率都達到統計顯著（|t|>2）。

    邏輯：
    - 船殼：`slip_after_pct`（欄位名稱沿用舊 schema，實際代表 speed-loss %）
      固定為 0（清潔後即為該週期自己的基準，定義上是 0%）；`slip_before_pct`＝
      船隊船殼速率 × 這次清潔距上次船殼清潔累積的天數（模型推論的speed loss%）；
      `slip_delta_pct` 等於 `slip_before_pct`。
    - 螺旋槳：`slip_after_pct`＝清潔後新週期實際觀測到的滑差 baseline（真實
      資料錨點）；`slip_before_pct`＝該值加上船隊螺旋槳速率 × 累積天數；
      `slip_delta_pct`＝累積量。
    - DD/UWC+PP → 船殼+螺旋槳速率都套用；UWC → 只套船殼；PP/UWI+PP → 只套
      螺旋槳；UWI（純檢查）→ 不套用任何速率，維持「不該有改善」。
    - 每筆額外回傳 `metric` 欄位標示這筆數字實際單位（船殼是 speed-loss %、
      螺旋槳是 slip 百分點），避免誤讀成同一種量。

    weather：DIFF_STW_SOG_SLIP（洋流/天候代理），跟養護事件無關，維持原樣。
    """
    rows  = query_vessel(vessel_id)
    maint = query_maintenance(vessel_id)

    if not rows:
        return err(404, f'Vessel {vessel_id} not found')

    rates = _fleet_degradation_rates()
    hull_rate = rates['hull']['slope_per_30d_pct']
    prop_rate = rates['propeller']['slope_per_30d_pct']

    hull_series = _calm_foc_series(vessel_id)
    prop_series = _calm_slip_series(vessel_id)

    MIN_CYCLE_RECORDS = 6

    def cycle_events_and_boundaries(type_set):
        trigger_events = sorted(
            [m for m in maint if str(m.get('event_type', '')) in type_set],
            key=lambda x: safe_float(x.get('event_day'), 0),
        )
        boundaries = [safe_float(m.get('event_day'), 0) for m in trigger_events]
        return trigger_events, boundaries

    def observed_baselines(series, boundaries):
        """Observed baseline (mean of first ~15%) per cycle, keyed by cycle index."""
        buckets = defaultdict(list)
        for day, val in series:
            buckets[_cycle_index(day, boundaries)].append((day, val))
        baselines = {}
        for idx, records in buckets.items():
            if len(records) < MIN_CYCLE_RECORDS:
                continue
            n_base = max(3, len(records) // 7)
            baselines[idx] = mean([v for _, v in records[:n_base]])
        return baselines

    hull_events, hull_boundaries = cycle_events_and_boundaries(HULL_CLEAN_TYPES)
    prop_events, prop_boundaries = cycle_events_and_boundaries(PROP_POLISH_TYPES)
    prop_baselines = observed_baselines(prop_series, prop_boundaries)
    # Hull cycles only need to know which cycles have *enough* records to
    # trust — the FOC baseline value itself isn't used (hull "after" is
    # defined as 0%, its own cycle's baseline by construction).
    hull_has_enough_data = set(observed_baselines(hull_series, hull_boundaries).keys())

    def estimate_hull(target_day):
        """Hull: after = 0% (this cycle's own baseline, by definition);
        before = fleet hull rate × days since prior hull-clean (modeled
        Speed-Loss-% accumulated, FOC-based, not slip)."""
        idx = next((i for i, m in enumerate(hull_events)
                    if safe_float(m.get('event_day'), 0) == target_day), None)
        if idx is None or hull_rate is None or (idx + 1) not in hull_has_enough_data:
            return None, None
        days_accumulated = target_day - (hull_boundaries[idx - 1] if idx > 0 else 0.0)
        before = round(hull_rate / 30.0 * days_accumulated, 2)
        return before, 0.0

    def estimate_propeller(target_day):
        """Propeller: after = observed post-clean slip baseline (real data
        anchor); before = after + fleet propeller rate × days accumulated."""
        idx = next((i for i, m in enumerate(prop_events)
                    if safe_float(m.get('event_day'), 0) == target_day), None)
        if idx is None or prop_rate is None:
            return None, None
        after = prop_baselines.get(idx + 1)
        if after is None:
            return None, None
        days_accumulated = target_day - (prop_boundaries[idx - 1] if idx > 0 else 0.0)
        before = round(after + prop_rate / 30.0 * days_accumulated, 2)
        return before, round(after, 2)

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
            before, after = estimate_hull(day)
            metric = 'speed_loss_pct_foc'
        elif category == 'propeller':
            before, after = estimate_propeller(day)
            metric = 'slip_pct_points'
        else:
            before, after, metric = None, None, None

        if before is None or after is None:
            delta = None
            physical = False
        else:
            delta    = round(before - after, 2)   # 正值 = 改善，模型推論恆非負
            physical = category != 'inspection_only'

        event_attributions.append({
            'event_type':     etype,
            'event_day':      day,
            'category':       category,
            'physical_intervention': physical,
            'metric':          metric,
            'slip_before_pct': before,
            'slip_after_pct':  after,
            'slip_delta_pct':  delta,   # 正值 = 改善
            'notes': (
                'No physical intervention expected' if etype == 'UWI'
                else f'Fleet-rate-modeled improvement: {delta:+.2f}% ({metric})' if delta is not None
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
    def recent_numeric(records, field):
        return [value for r in records if (value := safe_float(r.get(field))) is not None]

    slips = recent_numeric(recent, 'ME_SLIP')
    avg_slip = round(mean(slips), 2) if slips else None

    # Prior 90-day window, same recent-vs-prior methodology as speed_loss_trend
    # in build_fleet_summary.py, to get a real degradation rate (not a guess).
    prior = rows_sorted[-180:-90] if len(rows_sorted) > 90 else []
    prior_slips = recent_numeric(prior, 'ME_SLIP')
    avg_prior_slip = round(mean(prior_slips), 2) if prior_slips else None
    degradation_rate_pct_per_day = (
        round((avg_slip - avg_prior_slip) / 90, 5)
        if avg_slip is not None and avg_prior_slip is not None else 0.0
    )

    # Real average fuel consumption for this vessel (MT/day), used only for
    # display — the projection curve below is anchored to a model-derived
    # excess rate, not a slip%-based guess.
    cons_list = recent_numeric(recent, 'ME_CONSUMPTION')
    avg_consumption_mt = round(mean(cons_list), 2) if cons_list else None

    # Current excess fuel rate (MT/day), from the same baseline model as
    # get_fuel_anomaly_cause() — replaces the old avg_consumption_mt *
    # (slip%/100) * 1.8 heuristic, whose 1.8 multiplier has no documented
    # derivation anywhere in this repo's history.
    current_excess_mt_per_day = _vessel_excess_fuel_mt_per_day(vessel_id, rows=rows, maint_rows=maint)

    FUEL_PRICE = 620
    curve = []
    if avg_slip is not None and current_excess_mt_per_day is not None:
        cumulative = 0.0
        for d in range(91):
            projected_slip = max(0.0, avg_slip + degradation_rate_pct_per_day * d)
            # Excess fuel is assumed to scale with projected slip relative to
            # today's slip (same degradation trend as the rest of this curve);
            # the anchor value itself — how much excess *today* — comes from
            # the model, not a fixed multiplier.
            scale = (projected_slip / avg_slip) if avg_slip > 0 else 1.0
            excess_per_day = current_excess_mt_per_day * scale * FUEL_PRICE
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

    # DD 用最近一次「DD 事件」本身算,不是最近一次任意類型維護——DD 走固定
    # 週期(見 FLEET_DD_INTERVAL_DAYS),跟 PP/UWC 的觸發條件不是同一回事。
    dd_events     = [m for m in all_maint if 'DD' in str(m.get('event_type', ''))]
    last_dd_day   = safe_float(dd_events[-1].get('event_day'), 0) if dd_events else 0
    days_since_dd = latest_day - last_dd_day
    dd_due        = days_since_dd >= FLEET_DD_INTERVAL_DAYS

    # Simple rule: recommend if slip > 10% or days since last > 365
    urgent = (avg_slip and avg_slip > 10) or days_since > 365

    return resp(200, {
        'vessel_id':                     vessel_id,
        'days_since_maintenance':        round(days_since),
        'avg_me_slip_pct':               avg_slip,
        'avg_consumption_mt':            avg_consumption_mt,
        'current_excess_fuel_mt_per_day': round(current_excess_mt_per_day, 2) if current_excess_mt_per_day is not None else None,
        'degradation_rate_pct_per_day':  degradation_rate_pct_per_day,
        'fuel_price_usd_per_mt':         FUEL_PRICE,
        'recommendation':                'URGENT' if urgent else 'ROUTINE',
        'recommended_type':              'DD' if dd_due else 'UWC',
        'reason':                        (
            'High ME slip indicates hull/propeller fouling' if avg_slip and avg_slip > 10
            else f'Scheduled maintenance due ({round(days_since)} days since last event)'
        ),
        'drydock_reminder': {
            'days_since_last_dd':         round(days_since_dd),
            'fleet_avg_dd_interval_days': FLEET_DD_INTERVAL_DAYS,
            'due':                        dd_due,
        },
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
      avg_fleet_speed_loss_pct: float,
      total_excess_fuel_cost_usd_per_day: float,
      worst_vessel: { vessel_id, avg_speed_loss_pct, urgency },
      per_vessel: [
        { vessel_id, vessel_type, ship_class, avg_speed_loss_pct,
          latest_speed_loss_pct, speed_loss_trend, avg_consumption_mt,
          urgency, days_since_maintenance, days_since_dd, dd_due,
          recommended_action, excess_fuel_cost_usd_per_day,
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

        def _bool(item, key, default=False):
            v = item.get(key)
            return bool(v) if v is not None else default

        for item in raw_items:
            per_vessel.append({
                # identification
                'vessel_id':    _s(item, 'vessel_id'),
                'type':         _s(item, 'vessel_type', 'training'),
                'ship_class':   _s(item, 'ship_class'),
                # speed loss
                'avg_speed_loss_pct':       _f(item, 'avg_speed_loss_pct'),
                'latest_speed_loss_pct':    _f(item, 'latest_speed_loss_pct'),
                'speed_loss_trend':         _f(item, 'speed_loss_trend'),
                'valid_speed_loss_records': _i(item, 'valid_speed_loss_records'),
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
                'days_since_dd':          _i(item, 'days_since_dd'),
                'dd_due':                 _bool(item, 'dd_due'),
                'recommended_action':     _s(item, 'recommended_action') or None,
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
            # Same source + semantics as build_fleet_summary.py's compute_summary:
            # precomputed SPEED_LOSS column, avg = last-90 mean, latest = most
            # recent valid reading, trend = latest vs. nearest reading >=90 days prior.
            speed_loss_pts = sorted(
                [(safe_float(r.get('NOON_UTC'), 0), safe_float(r.get('SPEED_LOSS')))
                 for r in rows
                 if safe_float(r.get('SPEED_LOSS')) is not None],
                key=lambda x: x[0])
            all_speed_losses = [s for _, s in speed_loss_pts]
            avg_speed_loss   = round(mean([s for _, s in speed_loss_pts[-90:]]), 2) if speed_loss_pts else None
            if speed_loss_pts:
                latest_day, latest_speed_loss = speed_loss_pts[-1]
                prior_speed_loss = next(
                    (s for d, s in reversed(speed_loss_pts[:-1]) if d <= latest_day - 90),
                    None,
                )
                speed_loss_trend = round(latest_speed_loss - prior_speed_loss, 2) if prior_speed_loss is not None else None
            else:
                latest_speed_loss = None
                speed_loss_trend = None
            sorted_maint = sorted(maint, key=lambda x: safe_float(x.get('event_day'), 0))
            last_day   = safe_float(sorted_maint[-1].get('event_day'), 0) if sorted_maint else 0
            latest_day = safe_float(max((safe_float(r.get('NOON_UTC'), 0) for r in rows), default=0))
            days_since = round(latest_day - last_day) if rows else None
            HULL_CLEAN_TYPES = {'DD', 'UWC', 'UWC+PP'}
            hull_clean_events = [m for m in sorted_maint if str(m.get('event_type', '')).strip() in HULL_CLEAN_TYPES]
            last_hull_day = safe_float(hull_clean_events[-1].get('event_day'), 0) if hull_clean_events else 0
            days_since_hull = round(latest_day - last_hull_day) if (rows and hull_clean_events) else None
            speed_loss_trend_val = speed_loss_trend or 0
            urgency    = ('HIGH'   if speed_loss_trend_val >= 20 else
                          'MEDIUM' if speed_loss_trend_val >= 10 else 'LOW')
            cons_list  = [safe_float(r.get('ME_CONSUMPTION')) for r in rows if r.get('ME_CONSUMPTION')]
            avg_consumption = round(mean(cons_list), 2) if cons_list else None
            # Model-grounded excess (see _vessel_excess_fuel_mt_per_day) — not
            # the old avg_consumption * (speed-loss%/100) * 1.8 heuristic, whose
            # 1.8 multiplier has no documented derivation anywhere in this repo.
            excess_mt_per_day = _vessel_excess_fuel_mt_per_day(vid, rows=rows, maint_rows=maint)
            excess_per_day = (
                round(excess_mt_per_day * FUEL_PRICE, 2)
                if excess_mt_per_day is not None else None
            )
            return {
                'vessel_id':               vid,
                'type':                    'training' if vid in TRAIN_VESSELS else 'prediction',
                'ship_class':              'W1' if vid in W1_SHIPS_SET else 'W2',
                'avg_speed_loss_pct':       avg_speed_loss,
                'latest_speed_loss_pct':    latest_speed_loss,
                'speed_loss_trend':         speed_loss_trend,
                'valid_speed_loss_records': len(all_speed_losses),
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

    # Sort: training first, then prediction; within group by avg_speed_loss desc
    per_vessel.sort(key=lambda v: (0 if v['type'] == 'training' else 1, -(v['avg_speed_loss_pct'] or 0)))

    # Fleet-level aggregates (training vessels only for speed-loss average)
    training        = [v for v in per_vessel if v['type'] == 'training']
    speed_loss_vals = [v['avg_speed_loss_pct'] for v in training if v['avg_speed_loss_pct'] is not None]
    pending   = [v for v in per_vessel if v['urgency'] != 'LOW']
    total_excess = sum(v['excess_fuel_cost_usd_per_day'] or 0 for v in per_vessel)
    worst = max(training, key=lambda v: v['avg_speed_loss_pct'] or 0) if training else None

    result = resp(200, {
        'total_vessels':                  len(ALL),
        'training_vessels':               len(TRAIN_VESSELS),
        'prediction_vessels':             len(PRED_VESSELS),
        'pending_maintenance':            len(pending),
        'avg_fleet_speed_loss_pct':       round(mean(speed_loss_vals), 2) if speed_loss_vals else None,
        'total_excess_fuel_cost_usd_per_day': round(total_excess, 2),
        'worst_vessel': {
            'vessel_id':         worst['vessel_id'],
            'avg_speed_loss_pct': worst['avg_speed_loss_pct'],
            'urgency':           worst['urgency'],
        } if worst else None,
        'per_vessel': per_vessel,
    })
    _cache_set(cache_key, result)
    return result


def _rank_one_vessel(vid: str) -> dict:
    """Compute ranking stats for a single vessel (runs in thread pool).

    Same SPEED_LOSS source + semantics as build_fleet_summary.py's
    compute_summary and get_fleet_summary's _vessel_summary_fallback: avg =
    last-90 mean, latest = most recent valid reading, trend = latest vs.
    nearest reading >=90 days prior.
    """
    rows = query_vessel(vid)
    cons_list = [safe_float(r.get('ME_CONSUMPTION')) for r in rows if r.get('ME_CONSUMPTION')]

    speed_loss_pts = sorted(
        [(safe_float(r.get('NOON_UTC'), 0), safe_float(r.get('SPEED_LOSS')))
         for r in rows
         if safe_float(r.get('SPEED_LOSS')) is not None],
        key=lambda x: x[0]
    )
    all_speed_losses = [s for _, s in speed_loss_pts]
    avg_speed_loss = round(mean([s for _, s in speed_loss_pts[-90:]]), 2) if speed_loss_pts else None
    if speed_loss_pts:
        latest_day, latest_speed_loss = speed_loss_pts[-1]
        prior_speed_loss = next(
            (s for d, s in reversed(speed_loss_pts[:-1]) if d <= latest_day - 90),
            None,
        )
        speed_loss_trend = round(latest_speed_loss - prior_speed_loss, 2) if prior_speed_loss is not None else None
    else:
        latest_speed_loss = None
        speed_loss_trend = None

    return {
        'vessel_id':                vid,
        'avg_speed_loss_pct':       avg_speed_loss,
        'latest_speed_loss_pct':    latest_speed_loss,
        'speed_loss_trend':         speed_loss_trend,
        'avg_consumption_mt':       round(mean(cons_list), 2) if cons_list else None,
        'valid_speed_loss_records': len(all_speed_losses),
        'total_records':            len(rows),
    }


def get_fleet_ranking(event):
    """Rank all training vessels by avg_speed_loss_pct (lower = better performance)."""
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

    # 排名：avg_speed_loss_pct 越低越好
    rankings.sort(key=lambda x: x['avg_speed_loss_pct'] if x['avg_speed_loss_pct'] is not None else 99)
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


V5_MAINTENANCE_TYPES = {'PP': 1, 'UWI': 2, 'UWI+PP': 3, 'UWC': 4, 'UWC+PP': 5, 'DD': 6}
V5_FEATURE_DEFAULTS = {
    'SEA_SPEED_DISTANCE': 0.0, 'TOTAL_DISTANCE': 0.0, 'ME_AVG_RPM': 1.0,
    'PROPELLER_SPEED': 0.0, 'HOURS_TOTAL': 24.0, 'FORE_DRAFT': 13.0,
    'AFTER_DRAFT': 13.0, 'MID_DRAFT': 13.0, 'DISPLACEMENT': 1.0,
    'CARGO_ON_BOARD': 0.0, 'AVG_SPEED': 0.0, 'SPEED_THROUGH_WATER': 1.0,
    'DIFF_STW_SOG_SLIP': 0.0, 'FULL_SPD_STW_SLIP': 0.0, 'WIND_SCALE': 0.0,
    'WIND_SPEED': 0.0, 'WIND_DIRECTION': 0.0, 'SEA_HEIGHT': 0.0,
    'SEA_DIRECTION': 0.0, 'SWELL_HEIGHT': 0.0, 'SWELL_DIRECTION': 0.0,
    'SEA_WATER_TEMP': 20.0, 'WATER_DEPTH': 100.0,
}


def _v5_speed_loss_pct(vessel_id, noon_day):
    """Read the existing ISO 19030 FOC speed-loss value for v5's feature contract."""
    cache_key = f'v5:speed-loss:{vessel_id}'
    timeline = _cache_get(cache_key)
    if timeline is None:
        response = get_speed_loss(vessel_id, {})
        if response.get('statusCode') != 200:
            return 0.0
        try:
            timeline = json.loads(response['body']).get('foc_timeline', [])
        except (KeyError, TypeError, json.JSONDecodeError):
            return 0.0
        _cache_set(cache_key, timeline)
    for point in timeline:
        if abs(safe_float(point.get('noon_day'), -1) - noon_day) < 0.5:
            return safe_float(point.get('speed_loss_pct'), 0.0)
    return 0.0


def _v5_maintenance_features(maint_rows, noon_day, counterfactual=False):
    """Match v5's DAYS_SINCE_LAST_MAINT and LAST_MAINT_TYPE training features."""
    if counterfactual:
        return 0.0, float(V5_MAINTENANCE_TYPES['UWC+PP'])
    prior = [m for m in maint_rows if safe_float(m.get('event_day'), -1) <= noon_day]
    if not prior:
        return float(noon_day), np.nan
    last = max(prior, key=lambda m: safe_float(m.get('event_day'), -1))
    return max(0.0, noon_day - safe_float(last.get('event_day'), noon_day)), float(
        V5_MAINTENANCE_TYPES.get(str(last.get('event_type', '')), np.nan)
    )


def _build_v5_features(vessel_id, row_data, body, maint_rows, noon_day, counterfactual=False):
    """Build the exact 30-feature DataFrame expected by model_v5_final.pkl."""
    bundle = _load_model()

    def get(field):
        if field in body and body[field] is not None:
            return float(body[field])
        return safe_float(row_data.get(field), V5_FEATURE_DEFAULTS.get(field, 0.0))

    days_since_maint, last_maint_type = _v5_maintenance_features(
        maint_rows, noon_day, counterfactual=counterfactual,
    )
    rpm = max(get('ME_AVG_RPM'), 1.0)
    stw = max(get('SPEED_THROUGH_WATER'), 1.0)
    speed_loss_pct = 0.0 if counterfactual else _v5_speed_loss_pct(vessel_id, noon_day)
    raw = {feature: get(feature) for feature in bundle['features']}
    raw.update({
        'DAYS_SINCE_LAST_MAINT': days_since_maint,
        'LAST_MAINT_TYPE': last_maint_type,
        'speed_loss_pct': speed_loss_pct,
        'RPM_CUBED': (rpm / 100.0) ** 3,
        'POWER_SPEED_RATIO': (rpm / 100.0) ** 3 / (stw / 10.0) ** 3,
        'DAYS_SINCE_MAINT_SQRT': math.sqrt(days_since_maint),
        'NOON_UTC_NORM': noon_day / 1825.0,
    })
    return pd.DataFrame([{feature: raw[feature] for feature in bundle['features']}])


def _predict_v5(features):
    """Predict VLSFO-equivalent 24-hour Daily FOC with the persisted 50/50 ensemble."""
    bundle = _load_model()
    weights = bundle['ensemble_weights']
    prediction = (
        weights['xgb'] * float(bundle['xgb_model'].predict(features)[0])
        + weights['lgbm'] * float(bundle['lgbm_model'].predict(features)[0])
    )
    return max(0.0, prediction)


def _v5_to_source_fuel_mt(vlsfo_equivalent_mt_24h, source_lcv_mj_per_kg, hours_full_speed):
    """Convert v5's normalized target back to the NOON Report fuel-period target."""
    return vlsfo_equivalent_mt_24h * (40.2 / source_lcv_mj_per_kg) * (hours_full_speed / 24.0)


FUEL_LCV_MJ_PER_KG = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2,
    'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2,
    'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}
DEFAULT_FUEL_TYPE = 'ME_FULLSPEED_CONSUMP_VLSFO'
CPC_PRICE_URL = 'https://www.cpc.com.tw/GetOilPriceJson.aspx?type=TodayOilPriceString'
USD_TWD_EXCHANGE_RATE_URL = 'https://open.er-api.com/v6/latest/USD'
DIESEL_LCV_MJ_PER_KG = 42.7
DIESEL_DENSITY_KG_PER_L = 0.84
SEA_DAYS_PER_YEAR = 300


_external_price_lock = threading.Lock()


def _resolve_fuel_basis(body, row_data):
    requested = body.get('fuel_type')
    if requested is not None:
        if requested not in FUEL_LCV_MJ_PER_KG:
            raise ValueError(f'Unsupported fuel_type: {requested}')
        return requested, 'request', FUEL_LCV_MJ_PER_KG[requested]

    predicted_types = [fuel_type for fuel_type in FUEL_LCV_MJ_PER_KG if row_data.get(fuel_type) == 'PREDICT']
    if len(predicted_types) == 1:
        fuel_type = predicted_types[0]
        return fuel_type, 'noon_report_predict_target', FUEL_LCV_MJ_PER_KG[fuel_type]

    quantities = {
        fuel_type: safe_float(row_data.get(fuel_type))
        for fuel_type in FUEL_LCV_MJ_PER_KG
        if safe_float(row_data.get(fuel_type)) is not None and safe_float(row_data.get(fuel_type)) > 0
    }
    if quantities:
        total_mt = sum(quantities.values())
        weighted_lcv = sum(FUEL_LCV_MJ_PER_KG[fuel_type] * mt for fuel_type, mt in quantities.items()) / total_mt
        if len(quantities) == 1:
            fuel_type = next(iter(quantities))
            return fuel_type, 'noon_report', weighted_lcv
        return 'MIXED', 'weighted_noon_report', weighted_lcv
    return DEFAULT_FUEL_TYPE, 'default_vlsfo', FUEL_LCV_MJ_PER_KG[DEFAULT_FUEL_TYPE]


def _get_cpc_diesel_price():
    """Return CPC public diesel retail price metadata without failing inference."""
    cache_key = 'external:cpc-diesel-price'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    with _external_price_lock:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            fallback_price = float(os.environ.get('FUEL_PRICE_FALLBACK_TWD_PER_L', '28.8'))
            if not math.isfinite(fallback_price) or fallback_price <= 0:
                raise ValueError('fallback price must be finite and positive')
        except (TypeError, ValueError):
            fallback_price = 28.8
        fallback = {
            'twd_per_litre': fallback_price,
            'effective_date': None,
            'source_name': 'Taiwan CPC public retail diesel price',
            'source_url': CPC_PRICE_URL,
            'status': 'fallback',
        }
        try:
            request = urllib.request.Request(CPC_PRICE_URL, headers={'User-Agent': 'ship-analysis-roi/1.0'})
            # Python 3.14 enables OpenSSL strict X.509 checks that reject CPC's
            # otherwise CA/hostname-valid chain for a missing Subject Key Identifier.
            # Disable only strict-chain extras; certificate and hostname verification remain enabled.
            ssl_context = ssl.create_default_context()
            ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT
            with urllib.request.urlopen(request, timeout=3, context=ssl_context) as response:
                payload = json.loads(response.read().decode('utf-8'))
            price = safe_float(payload.get('sPrice5'))
            if price is None or price <= 0:
                raise ValueError('CPC response did not contain a valid diesel price')
            result = {
                **fallback,
                'twd_per_litre': price,
                'effective_date': payload.get('PriceUpdate'),
                'status': 'fetched',
            }
        except Exception:
            result = fallback
        _cache_set(cache_key, result)
        return result


def _get_usd_twd_exchange_rate():
    """Return public TWD per USD rate with a safe fallback for cost display."""
    cache_key = 'external:usd-twd-exchange-rate'
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    with _external_price_lock:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            fallback_rate = float(os.environ.get('USD_TWD_FALLBACK_RATE', '32.0'))
            if not math.isfinite(fallback_rate) or fallback_rate <= 0:
                raise ValueError('fallback rate must be finite and positive')
        except (TypeError, ValueError):
            fallback_rate = 32.0
        fallback = {
            'twd_per_usd': fallback_rate,
            'effective_date': None,
            'source_name': 'ExchangeRate-API open access USD rates',
            'source_url': USD_TWD_EXCHANGE_RATE_URL,
            'status': 'fallback',
        }
        try:
            request = urllib.request.Request(USD_TWD_EXCHANGE_RATE_URL, headers={'User-Agent': 'ship-analysis-roi/1.0'})
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode('utf-8'))
            rate = safe_float((payload.get('rates') or {}).get('TWD'))
            if rate is None or rate <= 0:
                raise ValueError('exchange-rate response did not contain a valid TWD rate')
            result = {
                **fallback,
                'twd_per_usd': rate,
                'effective_date': payload.get('time_last_update_utc'),
                'status': 'fetched',
            }
        except Exception:
            result = fallback
        _cache_set(cache_key, result)
        return result


def _calculate_energy_pricing(fuel_saving_mt_per_day, fuel_type, source_lcv):
    """Normalize fuel mass to energy, then show its cost delta consistently in USD."""
    saving_gj_per_day = max(0.0, fuel_saving_mt_per_day) * source_lcv
    diesel_equivalent_l_per_day = (
        saving_gj_per_day * 1000 / DIESEL_LCV_MJ_PER_KG / DIESEL_DENSITY_KG_PER_L
    )
    price = _get_cpc_diesel_price()
    exchange_rate = _get_usd_twd_exchange_rate()
    daily_saving_twd = diesel_equivalent_l_per_day * price['twd_per_litre']
    daily_saving_usd = daily_saving_twd / exchange_rate['twd_per_usd']
    return {
        'currency': 'USD',
        'fuel_type': fuel_type,
        'source_lcv_mj_per_kg': source_lcv,
        'normalized_energy_gj_per_day': round(saving_gj_per_day, 2),
        'diesel_equivalent_l_per_day': round(diesel_equivalent_l_per_day, 2),
        'price_twd_per_litre': price['twd_per_litre'],
        'daily_saving_usd': round(daily_saving_usd, 2),
        'annual_saving_usd': round(daily_saving_usd * SEA_DAYS_PER_YEAR, 0),
        'sea_days_per_year': SEA_DAYS_PER_YEAR,
        'price_source': {
            'name': price['source_name'],
            'url': price['source_url'],
            'effective_date': price['effective_date'],
            'status': price['status'],
            'basis': 'CPC super diesel retail price is an open-data energy-price proxy, not a bunker spot quote.',
        },
        'exchange_rate': {
            'twd_per_usd': exchange_rate['twd_per_usd'],
            'effective_date': exchange_rate['effective_date'],
            'name': exchange_rate['source_name'],
            'url': exchange_rate['source_url'],
            'status': exchange_rate['status'],
        },
    }


def predict_fuel(event):
    """
    v5 ensemble fuel prediction in VLSFO-equivalent, 24-hour-normalized MT/day.

    The model is only applicable to its trained steady-state envelope:
    WIND_SCALE ≤ 4 and HOURS_FULL_SPEED ≥ 22.  A noon-day lookup supplies the
    remaining voyage and maintenance features; request fields can override any
    raw report feature for what-if analysis.

    The counterfactual sets the v5 maintenance state to UWC+PP performed now
    and resets FOC-based speed loss to zero, matching the clean-state scenario
    used for this UI estimate.
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

    try:
        fuel_type, fuel_type_source, effective_fuel_lcv = _resolve_fuel_basis(body, row_data)
    except ValueError as exc:
        return err(400, str(exc))

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

    if noon_day is None:
        return err(400, 'noon_day is required for v5 feature construction')
    if wind_scale > 4 or hours_full_speed < 22:
        return err(422, 'v5 model is applicable only when WIND_SCALE <= 4 and HOURS_FULL_SPEED >= 22')

    # ── Load maintenance history (events up to noon_day only) ────────────────
    maint_rows = query_maintenance(vessel_id)
    maint_rows_sorted = sorted(
        [m for m in maint_rows
         if noon_day is None or safe_float(m.get('event_day'), 0) <= noon_day],
        key=lambda x: safe_float(x.get('event_day'), 0),
    )

    try:
        _load_model()
        X = _build_v5_features(vessel_id, row_data, body, maint_rows_sorted, noon_day)
        X_cf = _build_v5_features(
            vessel_id, row_data, body, maint_rows_sorted, noon_day, counterfactual=True,
        )
        predicted_vlsfo_equivalent = _predict_v5(X)
        predicted_cf_vlsfo_equivalent = _predict_v5(X_cf)
        predicted = round(_v5_to_source_fuel_mt(
            predicted_vlsfo_equivalent, effective_fuel_lcv, hours_full_speed,
        ), 2)
        predicted_cf = round(_v5_to_source_fuel_mt(
            predicted_cf_vlsfo_equivalent, effective_fuel_lcv, hours_full_speed,
        ), 2)
    except Exception as e:
        return err(500, f'Model load or v5 feature construction failed: {e}')

    # Expose the same fuel-period MT target as the NOON Report while retaining
    # v5's normalized value for traceability. Energy is invariant across the
    # conversion because source MT × source LCV equals VLSFO-equivalent energy.
    raw_cf_delta = round(predicted - predicted_cf, 2)
    cf_saving = max(0.0, raw_cf_delta)
    cf_saving_pct = round(cf_saving / predicted * 100, 1) if predicted > 0 else None

    annual_saving_mt = round(cf_saving * SEA_DAYS_PER_YEAR, 1)
    energy_pricing = _calculate_energy_pricing(cf_saving, fuel_type, effective_fuel_lcv)

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
        'model':     'v5_xgboost_lightgbm_ensemble',
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
            'fuel_type': fuel_type,
            'fuel_type_source': fuel_type_source,
            'effective_fuel_lcv_mj_per_kg': round(effective_fuel_lcv, 3),
            'prediction_basis': 'source_fuel_full_speed_period',
            'normalized_vlsfo_equivalent_mt_24h': round(predicted_vlsfo_equivalent, 2),
            'model_basis': 'VLSFO_equivalent_24h',
            'model_applicability': {'wind_scale_max': 4, 'hours_full_speed_min': 22},
        },
        'predicted_consumption_mt': predicted,
        'counterfactual_uwc_pp': {
            'description':              'v5 VLSFO-equivalent 24h prediction if UWC+PP were performed now (maintenance age and FOC speed loss reset)',
            'predicted_consumption_mt': predicted_cf,
            'fuel_saving_mt_per_day':   cf_saving,
            'raw_fuel_delta_mt_per_day': raw_cf_delta,
            'benefit_available':         raw_cf_delta > 0,
            'saving_pct':               cf_saving_pct,
            'est_annual_saving_mt':     annual_saving_mt,
            'energy_pricing':           energy_pricing,
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
