#!/usr/bin/env python3
"""
build_fleet_summary.py

Computes per-vessel fleet summary statistics from vt_fd.csv + maintenance.csv
and writes them into DynamoDB table: ship-analysis-dev-fleet-summary

Usage:
    # With env vars already set:
    python3 build_fleet_summary.py

    # With explicit credentials:
    AWS_ACCESS_KEY_ID=xxx AWS_SECRET_ACCESS_KEY=yyy python3 build_fleet_summary.py

    # Dry-run (print items, don't write to DynamoDB):
    python3 build_fleet_summary.py --dry-run

Table schema (PK = vessel_id):
    vessel_id               String  e.g. "S1"
    vessel_type             String  "training" | "prediction"
    ship_class              String  "W1" | "W2"
    total_records           Number
    total_voyages           Number
    avg_slip_pct            Number  mean FULL_SPD_STW_SLIP (0-30% valid)
    recent_90d_slip_pct     Number  mean of last-90-record slip values
    slip_trend              Number  recent_90d - avg (positive = degrading)
    avg_consumption_mt      Number  mean ME_CONSUMPTION
    urgency                 String  "LOW" | "MEDIUM" | "HIGH"
    days_since_maintenance  Number  latest NOON_UTC - last event_day
    excess_fuel_cost_usd_mtd Number  estimated monthly excess fuel cost USD
    last_updated            String  ISO-8601 UTC timestamp
"""

import argparse
import csv
import json
import os
import sys
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent
VT_FD_CSV = BASE_DIR / 'backend' / 'hackathon-data' / 'vt_fd.csv'
MAINT_CSV = BASE_DIR / 'backend' / 'hackathon-data' / 'maintenance.csv'

# ── Constants ─────────────────────────────────────────────────────────────────
TABLE_NAME   = os.environ.get('FLEET_SUMMARY_TABLE', 'ship-analysis-dev-fleet-summary')
REGION       = os.environ.get('AWS_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-1'))

TRAIN_VESSELS = {'S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12'}
PRED_VESSELS  = {'S21','S22','S23'}
W1_SHIPS      = {'S1','S2','S3','S4','S5','S6','S7','S8','S21'}
W2_SHIPS      = {'S9','S10','S11','S12','S22','S23'}

FUEL_PRICE_USD_MT  = 620   # USD per MT
BASELINE_MT_DAY_W1 = 155   # W1 ship baseline daily consumption MT
BASELINE_MT_DAY_W2 = 92    # W2 ship baseline daily consumption MT

# Static AIS positions (no real-time AIS in competition data)
SHIP_POSITIONS: dict[str, dict] = {
    'S1':  {'lat': 22.28, 'lon': 114.17, 'heading_deg': 210, 'speed_kt': 19.2},
    'S2':  {'lat':  1.26, 'lon': 103.84, 'heading_deg':   0, 'speed_kt':  0.0},
    'S3':  {'lat': 13.45, 'lon':  56.32, 'heading_deg': 285, 'speed_kt': 17.8},
    'S4':  {'lat': 51.89, 'lon':   4.48, 'heading_deg':   0, 'speed_kt':  0.0},
    'S5':  {'lat': 35.32, 'lon':  29.78, 'heading_deg': 105, 'speed_kt': 18.5},
    'S6':  {'lat':  6.93, 'lon':  79.85, 'heading_deg':  70, 'speed_kt': 20.1},
    'S7':  {'lat': 25.28, 'lon':  55.32, 'heading_deg':   0, 'speed_kt':  0.0},
    'S8':  {'lat': 29.87, 'lon': 121.55, 'heading_deg': 180, 'speed_kt': 16.9},
    'S9':  {'lat': 34.05, 'lon':-118.25, 'heading_deg':   0, 'speed_kt':  0.0},
    'S10': {'lat': 33.73, 'lon':-140.22, 'heading_deg':  90, 'speed_kt': 19.7},
    'S11': {'lat': 22.62, 'lon': 120.30, 'heading_deg':   0, 'speed_kt':  0.0},
    'S12': {'lat': 37.47, 'lon':-165.88, 'heading_deg':  72, 'speed_kt': 18.3},
    'S21': {'lat': 10.24, 'lon':  75.82, 'heading_deg': 255, 'speed_kt': 19.4},
    'S22': {'lat': 25.02, 'lon': 170.54, 'heading_deg':  55, 'speed_kt': 17.6},
    'S23': {'lat': 31.23, 'lon': 121.47, 'heading_deg':   0, 'speed_kt':  0.0},
}


def safe_float(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def load_vessel_data() -> dict[str, list[dict]]:
    """Load vt_fd.csv grouped by De-identification Name."""
    ships: dict[str, list[dict]] = {}
    with open(VT_FD_CSV, newline='') as f:
        for row in csv.DictReader(f):
            sid = row['De-identification Name'].strip()
            if sid not in ships:
                ships[sid] = []
            ships[sid].append(row)
    return ships


def load_maintenance_data() -> dict[str, list[dict]]:
    """Load maintenance.csv grouped by ship_id."""
    maint: dict[str, list[dict]] = {}
    with open(MAINT_CSV, newline='') as f:
        for row in csv.DictReader(f):
            sid = row['ship_id'].strip()
            if sid not in maint:
                maint[sid] = []
            maint[sid].append(row)
    return maint


def compute_summary(vessel_id: str, rows: list[dict], maint_rows: list[dict]) -> dict:
    """Compute all summary stats for one vessel."""
    # ── slip stats ────────────────────────────────────────────────────────────
    slip_timeline = []
    for r in rows:
        day  = safe_float(r.get('NOON_UTC'))
        slip = safe_float(r.get('FULL_SPD_STW_SLIP'))
        if day is not None and slip is not None and 0 <= slip <= 30:
            slip_timeline.append((day, slip))

    slip_timeline.sort(key=lambda x: x[0])
    all_slips    = [s for _, s in slip_timeline]
    recent_slips = [s for _, s in slip_timeline[-90:]]

    avg_slip    = round(statistics.mean(all_slips), 4)    if all_slips    else None
    recent_90d  = round(statistics.mean(recent_slips), 4) if recent_slips else avg_slip
    slip_trend  = round((recent_90d or 0) - (avg_slip or 0), 4)

    # ── consumption ──────────────────────────────────────────────────────────
    cons_list = [safe_float(r.get('ME_CONSUMPTION')) for r in rows if safe_float(r.get('ME_CONSUMPTION')) is not None]
    avg_consumption = round(statistics.mean(cons_list), 4) if cons_list else None

    # ── voyages ───────────────────────────────────────────────────────────────
    voyages = {r.get('VOYAGE', '').strip() for r in rows if r.get('VOYAGE', '').strip()}

    # ── days since last maintenance ───────────────────────────────────────────
    sorted_maint  = sorted(maint_rows, key=lambda x: safe_float(x.get('event_day'), 0))
    last_event_day = safe_float(sorted_maint[-1].get('event_day'), 0) if sorted_maint else 0
    latest_noon    = max((safe_float(r.get('NOON_UTC'), 0) for r in rows), default=0)
    days_since     = round(latest_noon - last_event_day) if rows else None

    # ── urgency ───────────────────────────────────────────────────────────────
    slip_val = recent_90d or avg_slip or 0
    if slip_val >= 10 or (days_since is not None and days_since > 365):
        urgency = 'HIGH'
    elif slip_val >= 6 or (days_since is not None and days_since > 270):
        urgency = 'MEDIUM'
    else:
        urgency = 'LOW'

    # ── excess fuel cost per day ──────────────────────────────────────────────
    baseline = BASELINE_MT_DAY_W1 if vessel_id in W1_SHIPS else BASELINE_MT_DAY_W2
    excess_fuel_cost_usd_per_day = round(baseline * (max(0, slip_val) / 100) * 1.8 * FUEL_PRICE_USD_MT, 2)

    pos = SHIP_POSITIONS.get(vessel_id, {'lat': 0.0, 'lon': 0.0, 'heading_deg': 0, 'speed_kt': 0.0})

    return {
        'vessel_id':               vessel_id,
        'vessel_type':             'training' if vessel_id in TRAIN_VESSELS else 'prediction',
        'ship_class':              'W1' if vessel_id in W1_SHIPS else 'W2',
        'total_records':           len(rows),
        'total_voyages':           len(voyages),
        'avg_slip_pct':            avg_slip,
        'recent_90d_slip_pct':     recent_90d,
        'slip_trend':              slip_trend,
        'avg_consumption_mt':      avg_consumption,
        'urgency':                 urgency,
        'days_since_maintenance':  days_since,
        'excess_fuel_cost_usd_per_day': excess_fuel_cost_usd_per_day,
        'lat':                     pos['lat'],
        'lon':                     pos['lon'],
        'heading_deg':             pos['heading_deg'],
        'speed_kt':                pos['speed_kt'],
        'last_updated':            datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }


def to_dynamo_item(summary: dict) -> dict:
    """Convert Python dict to DynamoDB-safe item (floats → Decimal)."""
    item = {}
    for k, v in summary.items():
        if v is None:
            continue  # skip None — DynamoDB doesn't accept null via resource API
        if isinstance(v, float):
            item[k] = Decimal(str(v))
        elif isinstance(v, int):
            item[k] = Decimal(str(v))
        else:
            item[k] = v
    return item


def create_table_if_not_exists(dynamodb):
    """Create the fleet-summary table if it doesn't already exist."""
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
        KeySchema=[
            {'AttributeName': 'vessel_id', 'KeyType': 'HASH'},
        ],
        AttributeDefinitions=[
            {'AttributeName': 'vessel_id', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST',
    )
    # Wait until active
    waiter = dynamodb.meta.client.get_waiter('table_exists')
    waiter.wait(TableName=TABLE_NAME)
    print(f"  Table '{TABLE_NAME}' created and active.")


def write_to_dynamodb(items: list[dict]):
    """Batch-write all items to DynamoDB."""
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    create_table_if_not_exists(dynamodb)
    table = dynamodb.Table(TABLE_NAME)

    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=to_dynamo_item(item))

    print(f"\n  Wrote {len(items)} items to '{TABLE_NAME}'.")


def main():
    parser = argparse.ArgumentParser(description='Build fleet summary DynamoDB table from CSV data.')
    parser.add_argument('--dry-run', action='store_true', help='Print items without writing to DynamoDB')
    args = parser.parse_args()

    print("Loading vessel data from CSV ...")
    vessel_data = load_vessel_data()
    maint_data  = load_maintenance_data()

    all_vessels = sorted(TRAIN_VESSELS | PRED_VESSELS)
    summaries   = []

    print(f"Computing summaries for {len(all_vessels)} vessels ...")
    for vid in all_vessels:
        rows        = vessel_data.get(vid, [])
        maint_rows  = maint_data.get(vid, [])
        summary     = compute_summary(vid, rows, maint_rows)
        summaries.append(summary)
        print(f"  {vid:4s}: records={summary['total_records']:4d}  "
              f"slip={str(summary['avg_slip_pct']):6s}  "
              f"recent_90d={str(summary['recent_90d_slip_pct']):6s}  "
              f"urgency={summary['urgency']}")

    if args.dry_run:
        print("\n[DRY RUN] Items that would be written:")
        print(json.dumps(summaries, indent=2, default=str))
        return

    print(f"\nWriting to DynamoDB table '{TABLE_NAME}' (region={REGION}) ...")
    write_to_dynamodb(summaries)
    print("Done.")


if __name__ == '__main__':
    main()
