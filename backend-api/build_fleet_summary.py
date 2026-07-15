#!/usr/bin/env python3
"""
build_fleet_summary.py

Computes per-vessel fleet summary statistics from vt_fd.csv + maintenance.csv
and writes them into DynamoDB table: ship-analysis-dev-fleet-summary

Usage:
    python3 build_fleet_summary.py           # write to DynamoDB
    python3 build_fleet_summary.py --dry-run # print without writing

Table schema (PK = vessel_id):
  Identification
    vessel_id, vessel_type, ship_class

  Slip / Speed Loss  (precomputed SPEED_LOSS column from vt_fd_speed_loss.csv;
                       sparse — only populated on qualifying full-speed days)
    avg_speed_loss_pct        mean of last 90 valid SPEED_LOSS records
    latest_speed_loss_pct     latest valid SPEED_LOSS reading — this
                               vessel's "current" speed loss
    speed_loss_trend          latest reading - nearest valid reading >=90
                               days before it  (+ = degrading)
    valid_speed_loss_records  count of valid speed-loss records (all-time)

  Performance indicators (mean over last 90 noon-report rows)
    avg_speed_kn           mean AVG_SPEED (SOG)
    avg_stw_kn             mean SPEED_THROUGH_WATER
    avg_rpm                mean ME_AVG_RPM
    avg_consumption_mt     mean ME_CONSUMPTION (MT/day)
    avg_sfoc               mean SFOC (g/kWh)  — may be null (hidden field)
    avg_horse_power        mean HORSE_POWER (kW) — may be null
    avg_me_slip_pct        mean ME_SLIP (%) — may be null

  Environmental conditions (mean over last 90 noon-report rows)
    avg_wind_scale         mean WIND_SCALE (Beaufort)
    avg_sea_height_m       mean SEA_HEIGHT (m)
    avg_sea_water_temp_c   mean SEA_WATER_TEMP (°C)
    avg_fore_draft_m       mean FORE_DRAFT (m)
    avg_aft_draft_m        mean AFTER_DRAFT (m)
    avg_cargo_on_board_mt  mean CARGO_ON_BOARD (MT)
    avg_displacement_mt    mean DISPLACEMENT (MT)

  Voyage coverage
    total_records          total noon-report rows
    total_voyages          distinct VOYAGE values
    day_range_min          earliest NOON_UTC
    day_range_max          latest NOON_UTC
    data_span_days         day_range_max - day_range_min

  Maintenance
    total_maint_events     total maintenance events
    last_event_type        event_type of last maintenance event
    last_event_day         NOON_UTC of last maintenance event
    days_since_maintenance latest noon - last any event
    days_since_hull_clean  latest noon - last DD/UWC/UWC+PP
    last_hull_clean_type   event_type of last hull-cleaning event
    last_propeller_polish_day latest PP/UWC+PP/UWI+PP day
    days_since_prop_polish latest noon - last propeller polish
    days_since_dd          latest noon - last DD event specifically
    dd_due                 days_since_dd >= FLEET_DD_INTERVAL_DAYS (fleet-observed cycle)
    recommended_action     UWC / PP / UWC+PP / None — read from the precomputed
                            fuel-anomaly-cause table's confident hull/propeller
                            attribution (same mapping as handler.py's
                            _recommend_maintenance_action)

  Cost
    excess_fuel_cost_usd_per_day  estimated daily excess cost, priced with the
                                  same live CPC diesel price + USD/TWD rate as
                                  handler.py's fuel-anomaly-cause ROI

  Urgency
    urgency                LOW / MEDIUM / HIGH — HIGH also triggers on dd_due
                            or a non-null recommended_action, not just the
                            slip%/days-since-maintenance rule

  Position (static — no AIS in competition data)
    lat, lon, speed_kt

  Meta
    last_updated           ISO-8601 UTC timestamp of this summary build
"""

import argparse
import csv
import json
import math
import os
import ssl
import statistics
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
from boto3.dynamodb.conditions import Key
from sklearn.ensemble import RandomForestRegressor

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent
VT_FD_CSV = BASE_DIR / 'backend' / 'hackathon-data' / 'vt_fd_speed_loss.csv'
MAINT_CSV = BASE_DIR / 'backend' / 'hackathon-data' / 'maintenance.csv'

# ── Constants ─────────────────────────────────────────────────────────────────
TABLE_NAME = os.environ.get('FLEET_SUMMARY_TABLE', 'ship-analysis-dev-fleet-summary')
REGION     = os.environ.get('AWS_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-1'))
FUEL_ANOMALY_TABLE = os.environ.get('FUEL_ANOMALY_TABLE', 'ship-analysis-dev-fuel-anomaly-cause')

TRAIN_VESSELS = {'S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12'}
PRED_VESSELS  = {'S21','S22','S23'}
W1_SHIPS      = {'S1','S2','S3','S4','S5','S6','S7','S8','S21'}
W2_SHIPS      = {'S9','S10','S11','S12','S22','S23'}

# Live energy pricing (same source + method as handler.py's
# _calculate_energy_pricing/get_fuel_anomaly_cause ROI, duplicated here rather
# than imported — this script is a standalone batch job, same convention as
# precompute_fuel_anomaly.py) — replaces the old fixed $620/MT guess so the
# $ figure here is comparable to the Fuel Attribution page's ROI instead of
# using a different, undocumented price.
LCV_VLSFO = 40.2  # MJ/kg, VLSFO-equivalent basis (matches handler.py)
DIESEL_LCV_MJ_PER_KG = 42.7
DIESEL_DENSITY_KG_PER_L = 0.84
CPC_PRICE_URL = 'https://www.cpc.com.tw/GetOilPriceJson.aspx?type=TodayOilPriceString'
USD_TWD_EXCHANGE_RATE_URL = 'https://open.er-api.com/v6/latest/USD'

# Same fleet-observed DD cycle as handler.py's FLEET_DD_INTERVAL_DAYS
# (duplicated, not imported — see note above): 10 training-vessel DD events
# cluster at day 769-985 (mean ~877), and every DD row's condition fields are
# blank, so it reads as a statutory survey cycle rather than a
# condition-triggered event. Used below to fold a real "DD overdue" signal
# into urgency, instead of it depending only on the old hand-picked
# slip%/days-since-any-maintenance thresholds.
FLEET_DD_INTERVAL_DAYS = 877


def _get_cpc_diesel_price():
    fallback_price = 28.8
    try:
        request = urllib.request.Request(CPC_PRICE_URL, headers={'User-Agent': 'ship-analysis-roi/1.0'})
        ssl_context = ssl.create_default_context()
        ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        with urllib.request.urlopen(request, timeout=3, context=ssl_context) as response:
            payload = json.loads(response.read().decode('utf-8'))
        price = float(payload.get('sPrice5'))
        if not math.isfinite(price) or price <= 0:
            raise ValueError('CPC response did not contain a valid diesel price')
        return price
    except Exception:
        print(f"  WARNING: CPC diesel price fetch failed — using fallback {fallback_price} TWD/L")
        return fallback_price


def _get_usd_twd_exchange_rate():
    fallback_rate = 32.0
    try:
        request = urllib.request.Request(USD_TWD_EXCHANGE_RATE_URL, headers={'User-Agent': 'ship-analysis-roi/1.0'})
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode('utf-8'))
        rate = float((payload.get('rates') or {}).get('TWD'))
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError('exchange-rate response did not contain a valid TWD rate')
        return rate
    except Exception:
        print(f"  WARNING: USD/TWD exchange-rate fetch failed — using fallback {fallback_rate}")
        return fallback_rate


def _excess_fuel_usd_per_day(excess_mt_per_day, twd_per_litre, twd_per_usd):
    """Same mass→energy→currency conversion as handler.py's
    _calculate_energy_pricing, collapsed to just the $/day figure since this
    table only stores the single number, not the full pricing breakdown."""
    energy_gj_per_day = excess_mt_per_day * LCV_VLSFO
    diesel_equivalent_l_per_day = energy_gj_per_day * 1000 / DIESEL_LCV_MJ_PER_KG / DIESEL_DENSITY_KG_PER_L
    return diesel_equivalent_l_per_day * twd_per_litre / twd_per_usd


def _recommend_maintenance_action(hull_confident_days, propeller_confident_days):
    """Same mapping as handler.py's _recommend_maintenance_action (duplicated,
    not imported — see note above): hull cause -> UWC, propeller cause -> PP,
    both -> UWC+PP, neither -> None."""
    if hull_confident_days and propeller_confident_days:
        return 'UWC+PP'
    if hull_confident_days:
        return 'UWC'
    if propeller_confident_days:
        return 'PP'
    return None


def fetch_recommended_action(vessel_id: str, latest_noon: float, window_days: float = 90) -> str | None:
    """Reads the precomputed fuel-anomaly-cause table (populated separately by
    precompute_fuel_anomaly.py — this script does not retrain that SHAP model
    itself, just aggregates its stored per-day classifications) and maps
    confident hull/propeller anomaly days to a maintenance action, same
    aggregation as handler.py's _fuel_anomaly_roi.

    Restricted to the last `window_days` of noon_day (same recency window as
    avg_speed_loss_pct elsewhere in this file) — anomaly days are sparse and
    spread across each vessel's whole multi-year history (~20-40 total over
    4-5 years), so counting *any* confident day ever means nearly every
    vessel gets a non-null action, which saturates urgency to HIGH fleet-wide
    and defeats its purpose. Recency keeps this a "currently ongoing" signal.

    Returns None (no signal, not "no action needed") if the table is
    empty/unreachable for this vessel — urgency then falls back to the other
    signals untouched."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        table = dynamodb.Table(FUEL_ANOMALY_TABLE)
        response = table.query(KeyConditionExpression=Key('vessel_id').eq(vessel_id))
        items = response.get('Items', [])
    except Exception:
        return None
    cutoff = latest_noon - window_days
    recent = [it for it in items if float(it.get('noon_day', -1)) >= cutoff]
    hull_confident = sum(1 for it in recent if it.get('primary_cause') == '船殼汙損' and it.get('cause_model_agrees'))
    prop_confident  = sum(1 for it in recent if it.get('primary_cause') == '螺旋槳汙損' and it.get('cause_model_agrees'))
    return _recommend_maintenance_action(hull_confident, prop_confident)

# Event type classification (from README)
HULL_CLEAN_TYPES  = {'DD', 'UWC', 'UWC+PP'}           # hull physically cleaned
PROP_POLISH_TYPES = {'PP', 'UWC+PP', 'UWI+PP', 'DD'}  # propeller polished
EFFECTIVE_TYPES   = {'DD', 'UWC', 'PP', 'UWI+PP', 'UWC+PP'}  # any physical intervention

# Static positions — placed on actual Yang Ming shipping lanes.
# W1 (S1-S8, S21): Asia-Europe via Suez Canal (FE3 service)
#   Key waypoints: Taiwan Strait → South China Sea → Malacca → Indian Ocean
#                  → Gulf of Aden → Red Sea → Suez → Mediterranean → NW Europe
# W2 (S9-S12, S22-S23): Trans-Pacific service
#   Key waypoints: Taiwan/Japan → North Pacific → US West Coast
# heading_deg: approximate course angle on each lane segment
# lat/lon: confirmed open-ocean positions, not over land
SHIP_POSITIONS: dict[str, dict] = {
    # W1 — Asia-Europe (Suez route), various positions along the lane
    'S1':  {'lat': 21.50, 'lon': 115.80, 'heading_deg': 225},  # S China Sea, open water SW of HK
    'S2':  {'lat':  1.00, 'lon': 105.50, 'heading_deg': 270},  # S China Sea, W of Singapore, open water
    'S3':  {'lat': 11.50, 'lon':  57.00, 'heading_deg': 300},  # Arabian Sea, open ocean NW of Socotra
    'S4':  {'lat': 52.50, 'lon':   3.20, 'heading_deg': 100},  # North Sea, off coast approaching Rotterdam
    'S5':  {'lat': 35.50, 'lon':  25.50, 'heading_deg': 280},  # Aegean Sea, open water W of Crete
    'S6':  {'lat':  4.50, 'lon':  79.00, 'heading_deg': 280},  # Indian Ocean, open water S of Sri Lanka
    'S7':  {'lat': 24.50, 'lon':  58.50, 'heading_deg':  15},  # Gulf of Oman, open water
    'S8':  {'lat': 30.80, 'lon': 124.50, 'heading_deg': 180},  # E China Sea, open water off Zhoushan
    'S21': {'lat': 12.00, 'lon':  44.50, 'heading_deg': 340},  # Gulf of Aden, open water
    # W2 — Trans-Pacific (Asia ↔ US West Coast)
    'S9':  {'lat': 32.50, 'lon':-119.50, 'heading_deg': 260},  # Pacific, open water W of LA
    'S10': {'lat': 36.00, 'lon':-148.00, 'heading_deg':  85},  # N Pacific, mid-ocean eastbound
    'S11': {'lat': 21.80, 'lon': 119.20, 'heading_deg':  15},  # Taiwan Strait, open water S of Taiwan
    'S12': {'lat': 39.00, 'lon':-163.00, 'heading_deg':  75},  # N Pacific, mid-ocean eastbound
    'S22': {'lat': 28.00, 'lon': 168.00, 'heading_deg':  65},  # W Pacific, open ocean
    'S23': {'lat': 29.50, 'lon': 124.00, 'heading_deg':  45},  # E China Sea, open water E of Shanghai
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_float(val, default=None):
    if val is None:
        return default
    s = str(val).strip()
    if s in ('', 'HIDDEN', 'PREDICT', 'NA', 'N/A', 'nan', 'None'):
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def mean_or_none(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return round(statistics.mean(clean), 4) if clean else None


def last_event_of_type(sorted_events: list, types: set) -> dict | None:
    matches = [e for e in sorted_events if str(e.get('event_type', '')).strip() in types]
    return matches[-1] if matches else None


# ── Excess-fuel baseline model ─────────────────────────────────────────────
# Mirrors backend-api/handler.py's _fleet_fuel_anomaly_models() /
# _vessel_excess_fuel_mt_per_day() — duplicated here (not imported) because
# this script works from CSV directly and runs standalone, without a live
# DynamoDB-backed handler process. Replaces the old
# avg_consumption * (slip%/100) * 1.8 heuristic, whose 1.8 multiplier has no
# documented derivation anywhere in this repo's history (checked git blame
# back to the commit that introduced it — see notebooks/anomaly_analysis.ipynb
# §6 for the full method and validation).
FUEL_LCV = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2, 'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2, 'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}
FUEL_COLS = list(FUEL_LCV.keys())
OP_FEATURES = ['ME_AVG_RPM', 'SPEED_THROUGH_WATER', 'AVG_SPEED', 'FORE_DRAFT', 'AFTER_DRAFT',
               'CARGO_ON_BOARD', 'WIND_SCALE', 'SEA_HEIGHT', 'SWELL_HEIGHT', 'SEA_WATER_TEMP']


def get_daily_foc(row: dict) -> float | None:
    hfs = safe_float(row.get('HOURS_FULL_SPEED'), 0)
    if hfs is None or hfs < 22:
        return None
    best_col, best_val = None, 0
    for fc in FUEL_COLS:
        v = safe_float(row.get(fc), 0) or 0
        if v > best_val:
            best_val, best_col = v, fc
    if best_col is None or best_val <= 0:
        return None
    lcv = FUEL_LCV[best_col]
    return best_val * lcv / 40.2 / hfs * 24.0


def _calm_op_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        ws, hfs = safe_float(r.get('WIND_SCALE')), safe_float(r.get('HOURS_FULL_SPEED'))
        if ws is None or hfs is None or ws > 4 or hfs < 22:
            continue
        daily_foc = get_daily_foc(r)
        if daily_foc is None or daily_foc < 10:
            continue
        op_vals = {f: safe_float(r.get(f)) for f in OP_FEATURES}
        if any(v is None for v in op_vals.values()):
            continue
        out.append({'daily_foc': daily_foc, **op_vals})
    return out


def build_baseline_model(vessel_data: dict[str, list[dict]]) -> RandomForestRegressor | None:
    """Fleet-wide baseline model: operating conditions -> expected daily FOC,
    trained on all training vessels' calm-condition days, deliberately blind
    to maintenance state (same design as handler.py's fuel-anomaly-cause)."""
    all_rows = []
    for vid in TRAIN_VESSELS:
        all_rows.extend(_calm_op_rows(vessel_data.get(vid, [])))
    if len(all_rows) < 50:
        print(f"  WARNING: only {len(all_rows)} calm-condition rows available — skipping excess-fuel model, excess_fuel_cost_usd_per_day will be null.")
        return None
    df = pd.DataFrame(all_rows)
    model = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=42, n_jobs=-1)
    model.fit(df[OP_FEATURES], df['daily_foc'])
    return model


def vessel_excess_fuel_mt_per_day(model: RandomForestRegressor | None, rows: list[dict]) -> float | None:
    """This vessel's average (actual - baseline-model-expected) daily FOC over
    its most recent 90 qualifying (calm-condition) days, floored at 0."""
    if model is None:
        return None
    calm = _calm_op_rows(rows)
    if not calm:
        return None
    df = pd.DataFrame(calm).tail(90)
    predicted = model.predict(df[OP_FEATURES])
    residual = df['daily_foc'].to_numpy() - predicted
    return max(0.0, float(np.mean(residual)))


def load_vessel_data() -> dict[str, list[dict]]:
    ships: dict[str, list[dict]] = {}
    with open(VT_FD_CSV, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            sid = row['De-identification Name'].strip()
            ships.setdefault(sid, []).append(row)
    return ships


def load_maintenance_data() -> dict[str, list[dict]]:
    maint: dict[str, list[dict]] = {}
    with open(MAINT_CSV, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            sid = row['ship_id'].strip()
            maint.setdefault(sid, []).append(row)
    return maint


# ── Core computation ──────────────────────────────────────────────────────────

def compute_summary(vessel_id: str, rows: list[dict], maint_rows: list[dict],
                     excess_model: RandomForestRegressor | None = None,
                     twd_per_litre: float = 28.8, twd_per_usd: float = 32.0,
                     recommended_action: str | None = None) -> dict:
    """Compute all summary stats for one vessel from raw CSV rows."""

    # ── Sort rows by NOON_UTC ──────────────────────────────────────────────
    rows_sorted = sorted(rows, key=lambda r: safe_float(r.get('NOON_UTC'), 0))
    latest_noon = safe_float(rows_sorted[-1].get('NOON_UTC'), 0) if rows_sorted else 0
    earliest_noon = safe_float(rows_sorted[0].get('NOON_UTC'), 0) if rows_sorted else 0

    # ── Speed-loss stats (precomputed SPEED_LOSS, sparse — only qualifying days) ──
    speed_loss_pts = [
        (safe_float(r.get('NOON_UTC')), safe_float(r.get('SPEED_LOSS')))
        for r in rows_sorted
    ]
    speed_loss_pts = [(d, s) for d, s in speed_loss_pts if d is not None and s is not None]

    all_speed_losses          = [s for _, s in speed_loss_pts]
    avg_speed_loss            = mean_or_none([s for _, s in speed_loss_pts[-90:]])
    valid_speed_loss_records  = len(all_speed_losses)

    if speed_loss_pts:
        latest_day, latest_speed_loss = speed_loss_pts[-1]
        prior_speed_loss = next(
            (s for d, s in reversed(speed_loss_pts[:-1]) if d <= latest_day - 90),
            None,
        )
        speed_loss_trend = round(latest_speed_loss - prior_speed_loss, 4) if prior_speed_loss is not None else None
    else:
        latest_speed_loss = None
        speed_loss_trend = None

    # Last 90 noon-report rows — same recency window as avg_speed_loss_pct
    # above, so every "avg_*" field in this summary reflects the vessel's
    # current condition, not its whole multi-year history.
    recent_rows = rows_sorted[-90:]

    # ── Speed / RPM ────────────────────────────────────────────────────────
    avg_speed_kn = mean_or_none([safe_float(r.get('AVG_SPEED')) for r in recent_rows])
    avg_stw_kn   = mean_or_none([safe_float(r.get('SPEED_THROUGH_WATER')) for r in recent_rows])
    avg_rpm      = mean_or_none([safe_float(r.get('ME_AVG_RPM')) for r in recent_rows])

    # ── Fuel / Engine performance ──────────────────────────────────────────
    avg_consumption  = mean_or_none([safe_float(r.get('ME_CONSUMPTION')) for r in recent_rows])
    avg_sfoc         = mean_or_none([safe_float(r.get('SFOC')) for r in recent_rows])
    avg_horse_power  = mean_or_none([safe_float(r.get('HORSE_POWER')) for r in recent_rows])
    avg_me_slip_pct  = mean_or_none([safe_float(r.get('ME_SLIP')) for r in recent_rows])
    avg_load_pct     = mean_or_none([safe_float(r.get('LOAD_PCT')) for r in recent_rows])

    # ── Environment ────────────────────────────────────────────────────────
    avg_wind_scale    = mean_or_none([safe_float(r.get('WIND_SCALE')) for r in recent_rows])
    avg_sea_height    = mean_or_none([safe_float(r.get('SEA_HEIGHT')) for r in recent_rows])
    avg_sea_water_temp= mean_or_none([safe_float(r.get('SEA_WATER_TEMP')) for r in recent_rows])

    # ── Loading condition ──────────────────────────────────────────────────
    avg_fore_draft    = mean_or_none([safe_float(r.get('FORE_DRAFT')) for r in recent_rows])
    avg_aft_draft     = mean_or_none([safe_float(r.get('AFTER_DRAFT')) for r in recent_rows])
    avg_mid_draft     = mean_or_none([safe_float(r.get('MID_DRAFT')) for r in recent_rows])
    avg_cargo         = mean_or_none([safe_float(r.get('CARGO_ON_BOARD')) for r in recent_rows])
    avg_displacement  = mean_or_none([safe_float(r.get('DISPLACEMENT')) for r in recent_rows])

    # ── Voyage coverage ────────────────────────────────────────────────────
    voyages = {r.get('VOYAGE', '').strip() for r in rows_sorted if r.get('VOYAGE', '').strip()}

    # ── Maintenance ────────────────────────────────────────────────────────
    sorted_maint = sorted(maint_rows, key=lambda x: safe_float(x.get('event_day'), 0))

    # Any event
    last_any = sorted_maint[-1] if sorted_maint else None
    last_event_day  = safe_float(last_any.get('event_day'), 0) if last_any else None
    last_event_type = str(last_any.get('event_type', '')).strip() if last_any else None
    days_since_maintenance = round(latest_noon - last_event_day) if (rows_sorted and last_event_day is not None) else None

    # Hull clean (DD / UWC / UWC+PP)
    last_hull = last_event_of_type(sorted_maint, HULL_CLEAN_TYPES)
    last_hull_clean_day  = safe_float(last_hull.get('event_day')) if last_hull else None
    last_hull_clean_type = str(last_hull.get('event_type', '')).strip() if last_hull else None
    days_since_hull_clean = round(latest_noon - last_hull_clean_day) if (rows_sorted and last_hull_clean_day is not None) else None

    # Propeller polish (PP / UWC+PP / UWI+PP / DD)
    last_prop = last_event_of_type(sorted_maint, PROP_POLISH_TYPES)
    last_prop_polish_day  = safe_float(last_prop.get('event_day')) if last_prop else None
    days_since_prop_polish = round(latest_noon - last_prop_polish_day) if (rows_sorted and last_prop_polish_day is not None) else None

    # DD specifically (not "any maintenance") — same distinction as
    # handler.py's get_maintenance_recommendation drydock_reminder.
    last_dd = last_event_of_type(sorted_maint, {'DD'})
    last_dd_day   = safe_float(last_dd.get('event_day')) if last_dd else None
    days_since_dd = round(latest_noon - last_dd_day) if (rows_sorted and last_dd_day is not None) else None
    dd_due = days_since_dd is not None and days_since_dd >= FLEET_DD_INTERVAL_DAYS

    # ── Urgency ────────────────────────────────────────────────────────────
    # Driven purely by speed_loss_trend (degradation over the last ~90 days),
    # not the absolute level and not dd_due/recommended_action/days-since-
    # maintenance — those remain as separate fields in the response, just no
    # longer fold into this classification.
    speed_loss_trend_val = speed_loss_trend or 0
    if speed_loss_trend_val >= 20:
        urgency = 'HIGH'
    elif speed_loss_trend_val >= 10:
        urgency = 'MEDIUM'
    else:
        urgency = 'LOW'

    # ── Excess fuel cost per day ───────────────────────────────────────────
    # Model-grounded: average (actual - baseline-model-expected) daily FOC
    # over this vessel's last 90 calm-condition days. See
    # vessel_excess_fuel_mt_per_day() docstring for why this replaced the old
    # avg_consumption * (slip%/100) * 1.8 heuristic. Priced the same way as
    # handler.py's fuel-anomaly-cause ROI (live CPC diesel price + USD/TWD
    # rate, not a fixed $/MT), so this KPI and that page's $ figures agree.
    excess_mt_per_day = vessel_excess_fuel_mt_per_day(excess_model, rows)
    excess_fuel_cost_usd_per_day = (
        round(_excess_fuel_usd_per_day(excess_mt_per_day, twd_per_litre, twd_per_usd), 2)
        if excess_mt_per_day is not None else None
    )

    # ── Position ───────────────────────────────────────────────────────────
    pos = SHIP_POSITIONS.get(vessel_id, {'lat': 0.0, 'lon': 0.0, 'heading_deg': 0})

    # speed_kt: use last noon report's AVG_SPEED (SOG) as current speed proxy
    last_speed_kt = safe_float(rows_sorted[-1].get('AVG_SPEED'), 0.0) if rows_sorted else 0.0

    return {
        # ── identification ────────────────────────────────────────────────
        'vessel_id':    vessel_id,
        'vessel_type':  'training' if vessel_id in TRAIN_VESSELS else 'prediction',
        'ship_class':   'W1' if vessel_id in W1_SHIPS else 'W2',

        # ── speed loss ────────────────────────────────────────────────────
        'avg_speed_loss_pct':       avg_speed_loss,
        'latest_speed_loss_pct':    latest_speed_loss,
        'speed_loss_trend':         speed_loss_trend,
        'valid_speed_loss_records': valid_speed_loss_records,

        # ── performance ───────────────────────────────────────────────────
        'avg_speed_kn':       avg_speed_kn,
        'avg_stw_kn':         avg_stw_kn,
        'avg_rpm':            avg_rpm,
        'avg_consumption_mt': avg_consumption,
        'avg_sfoc':           avg_sfoc,
        'avg_horse_power':    avg_horse_power,
        'avg_me_slip_pct':    avg_me_slip_pct,
        'avg_load_pct':       avg_load_pct,

        # ── environment ───────────────────────────────────────────────────
        'avg_wind_scale':      avg_wind_scale,
        'avg_sea_height_m':    avg_sea_height,
        'avg_sea_water_temp_c':avg_sea_water_temp,

        # ── loading ───────────────────────────────────────────────────────
        'avg_fore_draft_m':      avg_fore_draft,
        'avg_aft_draft_m':       avg_aft_draft,
        'avg_mid_draft_m':       avg_mid_draft,
        'avg_cargo_on_board_mt': avg_cargo,
        'avg_displacement_mt':   avg_displacement,

        # ── voyage coverage ───────────────────────────────────────────────
        'total_records':   len(rows),
        'total_voyages':   len(voyages),
        'day_range_min':   int(earliest_noon),
        'day_range_max':   int(latest_noon),
        'data_span_days':  int(latest_noon - earliest_noon),

        # ── maintenance ───────────────────────────────────────────────────
        'total_maint_events':       len(sorted_maint),
        'last_event_type':          last_event_type,
        'last_event_day':           int(last_event_day) if last_event_day is not None else None,
        'days_since_maintenance':   days_since_maintenance,
        'days_since_hull_clean':    days_since_hull_clean,
        'last_hull_clean_type':     last_hull_clean_type,
        'last_hull_clean_day':      int(last_hull_clean_day) if last_hull_clean_day is not None else None,
        'last_prop_polish_day':     int(last_prop_polish_day) if last_prop_polish_day is not None else None,
        'days_since_prop_polish':   days_since_prop_polish,
        'days_since_dd':            days_since_dd,
        'dd_due':                   dd_due,
        'recommended_action':       recommended_action,

        # ── cost ──────────────────────────────────────────────────────────
        'excess_fuel_cost_usd_per_day': excess_fuel_cost_usd_per_day,

        # ── urgency ───────────────────────────────────────────────────────
        'urgency': urgency,

        # ── position ──────────────────────────────────────────────────────
        'lat':         pos['lat'],
        'lon':         pos['lon'],
        'heading_deg': pos['heading_deg'],
        'speed_kt':    last_speed_kt,   # last noon report AVG_SPEED (SOG)

        # ── meta ──────────────────────────────────────────────────────────
        'last_updated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }


# ── DynamoDB helpers ──────────────────────────────────────────────────────────

def to_dynamo_item(summary: dict) -> dict:
    """Convert Python dict to DynamoDB-safe item (None removed, numbers → Decimal)."""
    item = {}
    for k, v in summary.items():
        if v is None:
            continue
        # bool is an int subclass in Python — must check before the int
        # branch, or True/False get stringified to "True"/"False" and fail
        # Decimal() conversion.
        if isinstance(v, bool):
            item[k] = v
        elif isinstance(v, (float, int)):
            item[k] = Decimal(str(v))
        else:
            item[k] = v
    return item


def create_table_if_not_exists(dynamodb):
    client = dynamodb.meta.client
    try:
        client.describe_table(TableName=TABLE_NAME)
        print(f"  Table '{TABLE_NAME}' already exists — skipping creation.")
        return
    except client.exceptions.ResourceNotFoundException:
        pass

    print(f"  Creating table '{TABLE_NAME}' ...")
    dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{'AttributeName': 'vessel_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'vessel_id', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST',
    )
    dynamodb.meta.client.get_waiter('table_exists').wait(TableName=TABLE_NAME)
    print(f"  Table '{TABLE_NAME}' created and active.")


def write_to_dynamodb(items: list[dict]):
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    create_table_if_not_exists(dynamodb)
    table = dynamodb.Table(TABLE_NAME)
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=to_dynamo_item(item))
    print(f"\n  Wrote {len(items)} items to '{TABLE_NAME}'.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Print items, skip DynamoDB write')
    args = parser.parse_args()

    print("Loading CSV data ...")
    vessel_data = load_vessel_data()
    maint_data  = load_maintenance_data()

    print("Training fleet-wide excess-fuel baseline model (calm-condition, training vessels only) ...")
    excess_model = build_baseline_model(vessel_data)

    print("Fetching live diesel price + USD/TWD rate (same source as handler.py ROI) ...")
    twd_per_litre = _get_cpc_diesel_price()
    twd_per_usd   = _get_usd_twd_exchange_rate()
    print(f"  {twd_per_litre} TWD/L, {twd_per_usd} TWD/USD")

    all_vessels = sorted(TRAIN_VESSELS | PRED_VESSELS)
    summaries   = []

    print(f"Computing summaries for {len(all_vessels)} vessels ...")
    for vid in all_vessels:
        rows               = vessel_data.get(vid, [])
        maint_rows         = maint_data.get(vid, [])
        latest_noon        = max((safe_float(r.get('NOON_UTC'), 0) for r in rows), default=0)
        recommended_action = fetch_recommended_action(vid, latest_noon)
        summary    = compute_summary(
            vid, rows, maint_rows, excess_model=excess_model,
            twd_per_litre=twd_per_litre, twd_per_usd=twd_per_usd,
            recommended_action=recommended_action,
        )
        summaries.append(summary)
        print(
            f"  {vid:4s}  records={summary['total_records']:4d}"
            f"  speed_loss={str(summary['avg_speed_loss_pct'] or '—'):6s}"
            f"  latest={str(summary['latest_speed_loss_pct'] or '—'):6s}"
            f"  maint={summary['days_since_maintenance']}d"
            f"  hull_clean={summary['days_since_hull_clean']}d"
            f"  action={str(summary['recommended_action'] or '—'):7s}"
            f"  urgency={summary['urgency']}"
        )

    if args.dry_run:
        print("\n[DRY RUN] Sample item (S1):")
        s1 = next((s for s in summaries if s['vessel_id'] == 'S1'), summaries[0])
        print(json.dumps(s1, indent=2, default=str))
        return

    print(f"\nWriting to DynamoDB '{TABLE_NAME}' (region={REGION}) ...")
    write_to_dynamodb(summaries)
    print("Done.")


if __name__ == '__main__':
    main()
