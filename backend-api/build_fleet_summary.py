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

  Slip / Speed Loss  (FULL_SPD_STW_SLIP, valid 0–30%)
    avg_slip_pct           mean over all valid records
    recent_90d_slip_pct    mean of last 90 valid records
    slip_trend             recent_90d - avg  (+ = degrading)
    valid_slip_records     count of valid slip records

  Performance indicators
    avg_speed_kn           mean AVG_SPEED (SOG)
    avg_stw_kn             mean SPEED_THROUGH_WATER
    avg_rpm                mean ME_AVG_RPM
    avg_consumption_mt     mean ME_CONSUMPTION (MT/day)
    avg_sfoc               mean SFOC (g/kWh)  — may be null (hidden field)
    avg_horse_power        mean HORSE_POWER (kW) — may be null
    avg_me_slip_pct        mean ME_SLIP (%) — may be null

  Environmental conditions (average over all records)
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

  Cost
    excess_fuel_cost_usd_per_day  estimated daily excess cost from slip

  Urgency
    urgency                LOW / MEDIUM / HIGH

  Position (static — no AIS in competition data)
    lat, lon, speed_kt

  Meta
    last_updated           ISO-8601 UTC timestamp of this summary build
"""

import argparse
import csv
import json
import os
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent
VT_FD_CSV = BASE_DIR / 'backend' / 'hackathon-data' / 'vt_fd.csv'
MAINT_CSV = BASE_DIR / 'backend' / 'hackathon-data' / 'maintenance.csv'

# ── Constants ─────────────────────────────────────────────────────────────────
TABLE_NAME = os.environ.get('FLEET_SUMMARY_TABLE', 'ship-analysis-dev-fleet-summary')
REGION     = os.environ.get('AWS_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-1'))

TRAIN_VESSELS = {'S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12'}
PRED_VESSELS  = {'S21','S22','S23'}
W1_SHIPS      = {'S1','S2','S3','S4','S5','S6','S7','S8','S21'}
W2_SHIPS      = {'S9','S10','S11','S12','S22','S23'}

FUEL_PRICE_USD_MT  = 620   # USD per MT
BASELINE_MT_DAY_W1 = 155   # W1 baseline daily consumption MT
BASELINE_MT_DAY_W2 = 92    # W2 baseline daily consumption MT

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

def compute_summary(vessel_id: str, rows: list[dict], maint_rows: list[dict]) -> dict:
    """Compute all summary stats for one vessel from raw CSV rows."""

    # ── Sort rows by NOON_UTC ──────────────────────────────────────────────
    rows_sorted = sorted(rows, key=lambda r: safe_float(r.get('NOON_UTC'), 0))
    latest_noon = safe_float(rows_sorted[-1].get('NOON_UTC'), 0) if rows_sorted else 0
    earliest_noon = safe_float(rows_sorted[0].get('NOON_UTC'), 0) if rows_sorted else 0

    # ── Slip stats (FULL_SPD_STW_SLIP, valid 0–30%) ────────────────────────
    slip_pts = [
        (safe_float(r.get('NOON_UTC')), safe_float(r.get('FULL_SPD_STW_SLIP')))
        for r in rows_sorted
    ]
    slip_pts = [(d, s) for d, s in slip_pts if d is not None and s is not None and 0 <= s <= 30]

    all_slips    = [s for _, s in slip_pts]
    recent_slips = [s for _, s in slip_pts[-90:]]

    avg_slip           = mean_or_none(all_slips)
    recent_90d_slip    = mean_or_none(recent_slips) if recent_slips else avg_slip
    slip_trend         = round((recent_90d_slip or 0) - (avg_slip or 0), 4) if avg_slip is not None else None
    valid_slip_records = len(all_slips)

    # ── Speed / RPM ────────────────────────────────────────────────────────
    avg_speed_kn = mean_or_none([safe_float(r.get('AVG_SPEED')) for r in rows_sorted])
    avg_stw_kn   = mean_or_none([safe_float(r.get('SPEED_THROUGH_WATER')) for r in rows_sorted])
    avg_rpm      = mean_or_none([safe_float(r.get('ME_AVG_RPM')) for r in rows_sorted])

    # ── Fuel / Engine performance ──────────────────────────────────────────
    avg_consumption  = mean_or_none([safe_float(r.get('ME_CONSUMPTION')) for r in rows_sorted])
    avg_sfoc         = mean_or_none([safe_float(r.get('SFOC')) for r in rows_sorted])
    avg_horse_power  = mean_or_none([safe_float(r.get('HORSE_POWER')) for r in rows_sorted])
    avg_me_slip_pct  = mean_or_none([safe_float(r.get('ME_SLIP')) for r in rows_sorted])
    avg_load_pct     = mean_or_none([safe_float(r.get('LOAD_PCT')) for r in rows_sorted])

    # ── Environment ────────────────────────────────────────────────────────
    avg_wind_scale    = mean_or_none([safe_float(r.get('WIND_SCALE')) for r in rows_sorted])
    avg_sea_height    = mean_or_none([safe_float(r.get('SEA_HEIGHT')) for r in rows_sorted])
    avg_sea_water_temp= mean_or_none([safe_float(r.get('SEA_WATER_TEMP')) for r in rows_sorted])

    # ── Loading condition ──────────────────────────────────────────────────
    avg_fore_draft    = mean_or_none([safe_float(r.get('FORE_DRAFT')) for r in rows_sorted])
    avg_aft_draft     = mean_or_none([safe_float(r.get('AFTER_DRAFT')) for r in rows_sorted])
    avg_mid_draft     = mean_or_none([safe_float(r.get('MID_DRAFT')) for r in rows_sorted])
    avg_cargo         = mean_or_none([safe_float(r.get('CARGO_ON_BOARD')) for r in rows_sorted])
    avg_displacement  = mean_or_none([safe_float(r.get('DISPLACEMENT')) for r in rows_sorted])

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

    # ── Urgency ────────────────────────────────────────────────────────────
    slip_val = recent_90d_slip or avg_slip or 0
    if slip_val >= 10 or (days_since_maintenance is not None and days_since_maintenance > 365):
        urgency = 'HIGH'
    elif slip_val >= 6 or (days_since_maintenance is not None and days_since_maintenance > 270):
        urgency = 'MEDIUM'
    else:
        urgency = 'LOW'

    # ── Excess fuel cost per day ───────────────────────────────────────────
    baseline = BASELINE_MT_DAY_W1 if vessel_id in W1_SHIPS else BASELINE_MT_DAY_W2
    excess_fuel_cost_usd_per_day = round(baseline * (max(0.0, slip_val) / 100) * 1.8 * FUEL_PRICE_USD_MT, 2)

    # ── Position ───────────────────────────────────────────────────────────
    pos = SHIP_POSITIONS.get(vessel_id, {'lat': 0.0, 'lon': 0.0, 'heading_deg': 0})

    # speed_kt: use last noon report's AVG_SPEED (SOG) as current speed proxy
    last_speed_kt = safe_float(rows_sorted[-1].get('AVG_SPEED'), 0.0) if rows_sorted else 0.0

    return {
        # ── identification ────────────────────────────────────────────────
        'vessel_id':    vessel_id,
        'vessel_type':  'training' if vessel_id in TRAIN_VESSELS else 'prediction',
        'ship_class':   'W1' if vessel_id in W1_SHIPS else 'W2',

        # ── slip / speed loss ─────────────────────────────────────────────
        'avg_slip_pct':        avg_slip,
        'recent_90d_slip_pct': recent_90d_slip,
        'slip_trend':          slip_trend,
        'valid_slip_records':  valid_slip_records,

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
        if isinstance(v, float):
            item[k] = Decimal(str(v))
        elif isinstance(v, int):
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

    all_vessels = sorted(TRAIN_VESSELS | PRED_VESSELS)
    summaries   = []

    print(f"Computing summaries for {len(all_vessels)} vessels ...")
    for vid in all_vessels:
        rows       = vessel_data.get(vid, [])
        maint_rows = maint_data.get(vid, [])
        summary    = compute_summary(vid, rows, maint_rows)
        summaries.append(summary)
        print(
            f"  {vid:4s}  records={summary['total_records']:4d}"
            f"  slip={str(summary['avg_slip_pct'] or '—'):6s}"
            f"  recent90d={str(summary['recent_90d_slip_pct'] or '—'):6s}"
            f"  maint={summary['days_since_maintenance']}d"
            f"  hull_clean={summary['days_since_hull_clean']}d"
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
