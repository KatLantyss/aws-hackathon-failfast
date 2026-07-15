#!/usr/bin/env python3
"""
precompute_fuel_anomaly.py

Computes per-day fuel-consumption anomaly root-cause classification from
vt_fd.csv + maintenance.csv directly (NOT via DynamoDB's vessel-data table,
which has duplicate noon-report items from an earlier double-upload — see
git history around 2026-07-16). Writes only the anomalous days (not all
~790 calm-condition days per vessel) into DynamoDB table:
  ship-analysis-dev-fuel-anomaly-cause

Method: same as backend-api/handler.py's get_fuel_anomaly_cause() /
_fleet_fuel_anomaly_models() — a baseline RandomForest (operating
conditions only, blind to maintenance state) predicts expected daily FOC;
the gap between actual and expected is classified by a second RandomForest
+ SHAP into hull / propeller / weather contributions. Full derivation and
validation: notebooks/anomaly_analysis.ipynb §6-9.

Table schema (PK = vessel_id, SK = noon_day):
  Using noon_day as the sort key is deliberate — re-running this script
  overwrites each day's item instead of appending a new snapshot, so the
  table can't accumulate the same kind of duplicate-row problem that hit
  vessel-data. Safe to re-run any time the source CSVs change.

  Each vessel also gets one extra sentinel item at noon_day=-1 holding
  total_days_analyzed / baseline_model_r2 — real noon_day values are large
  positive numbers, so -1 can't collide with an actual anomaly row. The API
  filters it out of `anomalies` and surfaces it in `summary` instead.

Usage:
    python3 precompute_fuel_anomaly.py           # write to DynamoDB
    python3 precompute_fuel_anomaly.py --dry-run # print without writing
"""

import argparse
import csv
import math
import os
from decimal import Decimal
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestRegressor

# ── Paths / constants ───────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent.parent
VT_FD_CSV = BASE_DIR / 'backend' / 'hackathon-data' / 'vt_fd.csv'
MAINT_CSV = BASE_DIR / 'backend' / 'hackathon-data' / 'maintenance.csv'

TABLE_NAME = os.environ.get('FUEL_ANOMALY_TABLE', 'ship-analysis-dev-fuel-anomaly-cause')
REGION     = os.environ.get('AWS_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-1'))

TRAIN_VESSELS = ['S1','S2','S3','S4','S5','S6','S7','S8','S9','S10','S11','S12']
PRED_VESSELS  = ['S21','S22','S23']
ALL_VESSELS   = TRAIN_VESSELS + PRED_VESSELS

HULL_CLEAN_TYPES  = {'DD', 'UWC', 'UWC+PP'}
PROP_POLISH_TYPES = {'DD', 'PP', 'UWI+PP', 'UWC+PP'}

FUEL_LCV = {
    'ME_FULLSPEED_CONSUMP_HSHFO': 40.2, 'ME_FULLSPEED_CONSUMP_VLSFO': 40.2,
    'ME_FULLSPEED_CONSUMP_ULSFO': 41.2, 'ME_FULLSPEED_CONSUMP_LSMGO': 42.7,
    'ME_FULLSPEED_CONSUMP_BIO_HSFO': 39.4,
}
FUEL_COLS = list(FUEL_LCV.keys())

OP_FEATURES = ['ME_AVG_RPM', 'SPEED_THROUGH_WATER', 'AVG_SPEED', 'FORE_DRAFT', 'AFTER_DRAFT',
               'CARGO_ON_BOARD', 'WIND_SCALE', 'SEA_HEIGHT', 'SWELL_HEIGHT', 'SEA_WATER_TEMP']
CAUSE_FEATURES = ['days_since_hull_clean', 'days_since_prop_polish', 'propeller_condition_code',
                   'WIND_SCALE', 'SEA_HEIGHT', 'SWELL_HEIGHT', 'SEA_WATER_TEMP']
CAUSE_GROUPS = {
    '船殼汙損': ['days_since_hull_clean'],
    '螺旋槳汙損': ['days_since_prop_polish', 'propeller_condition_code'],
    '天候': ['WIND_SCALE', 'SEA_HEIGHT', 'SWELL_HEIGHT', 'SEA_WATER_TEMP'],
}
PROPELLER_CONDITION_CODE = {'Poor': 0, 'Fair': 1, 'Good': 2, 'Unknown': -1}
ANOMALY_THRESHOLD_PCT = 15


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def _days_since_maint_type(maint_rows, noon_day, type_set):
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


def fuel_anomaly_rows(rows: list[dict], maint_rows: list[dict]) -> list[dict]:
    """Same feature definitions as handler.py's _fuel_anomaly_rows(), reading
    CSV dict rows (De-identification Name / NOON_UTC keys) instead of the
    DynamoDB row shape."""
    out = []
    for r in rows:
        ws  = safe_float(r.get('WIND_SCALE'))
        hfs = safe_float(r.get('HOURS_FULL_SPEED'))
        day = safe_float(r.get('NOON_UTC'))
        if ws is None or hfs is None or day is None or ws > 4 or hfs < 22:
            continue
        daily_foc = get_daily_foc(r)
        if daily_foc is None or daily_foc < 10:
            continue
        op_vals = {f: safe_float(r.get(f)) for f in OP_FEATURES}
        if any(v is None for v in op_vals.values()):
            continue
        prop_cond = _last_propeller_condition(maint_rows, day)
        out.append({
            'noon_day': day,
            'daily_foc': daily_foc,
            'days_since_hull_clean':  _days_since_maint_type(maint_rows, day, HULL_CLEAN_TYPES),
            'days_since_prop_polish': _days_since_maint_type(maint_rows, day, PROP_POLISH_TYPES),
            'propeller_condition_code': PROPELLER_CONDITION_CODE.get(prop_cond, -1),
            **op_vals,
        })
    return out


# ── Model training (fleet-wide, training vessels only) ─────────────────────

def train_models(vessel_data, maint_data):
    all_rows = []
    for vid in TRAIN_VESSELS:
        all_rows.extend(fuel_anomaly_rows(vessel_data.get(vid, []), maint_data.get(vid, [])))
    print(f"  Pooled {len(all_rows)} calm-condition rows across {len(TRAIN_VESSELS)} training vessels")

    df = pd.DataFrame(all_rows)
    baseline_model = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=42, n_jobs=-1)
    baseline_model.fit(df[OP_FEATURES], df['daily_foc'])
    r2 = round(float(baseline_model.score(df[OP_FEATURES], df['daily_foc'])), 4)

    df['predicted_foc'] = baseline_model.predict(df[OP_FEATURES])
    df['residual_pct'] = (df['daily_foc'] - df['predicted_foc']) / df['predicted_foc'] * 100

    cause_model = RandomForestRegressor(n_estimators=300, max_depth=6, random_state=42, n_jobs=-1)
    cause_model.fit(df[CAUSE_FEATURES], df['residual_pct'])
    explainer = shap.TreeExplainer(cause_model)

    print(f"  baseline_model_r2={r2}")
    return baseline_model, cause_model, explainer, r2


# ── Per-vessel classification ───────────────────────────────────────────────

def classify_vessel(vessel_id, rows, maint_rows, baseline_model, cause_model, explainer):
    vessel_rows = fuel_anomaly_rows(rows, maint_rows)
    if not vessel_rows:
        return [], 0

    df = pd.DataFrame(vessel_rows)
    total_days_analyzed = len(df)
    df['predicted_foc'] = baseline_model.predict(df[OP_FEATURES])
    df['residual_pct'] = (df['daily_foc'] - df['predicted_foc']) / df['predicted_foc'] * 100
    df['direction'] = np.select(
        [df['residual_pct'] > ANOMALY_THRESHOLD_PCT, df['residual_pct'] < -ANOMALY_THRESHOLD_PCT],
        ['over', 'under'], default='normal',
    )

    anomalies = df[df['direction'] != 'normal'].copy()
    if anomalies.empty:
        return [], total_days_analyzed

    X_cause = anomalies[CAUSE_FEATURES]
    cause_pred = cause_model.predict(X_cause)
    anomalies['cause_model_agrees'] = np.sign(cause_pred) == np.sign(anomalies['residual_pct'])

    shap_values = explainer.shap_values(X_cause)
    shap_df = pd.DataFrame(shap_values, columns=CAUSE_FEATURES, index=anomalies.index)
    group_shap = pd.DataFrame({g: shap_df[cols].sum(axis=1) for g, cols in CAUSE_GROUPS.items()})
    primary_cause = group_shap.abs().idxmax(axis=1)
    primary_cause_shap = group_shap.apply(lambda row: row[primary_cause[row.name]], axis=1)
    anomalies['primary_cause'] = primary_cause
    anomalies['primary_cause_shap'] = primary_cause_shap

    items = []
    for _, r in anomalies.sort_values('noon_day').iterrows():
        items.append({
            'vessel_id': vessel_id,
            'noon_day': int(r['noon_day']),
            'daily_foc_actual': round(float(r['daily_foc']), 2),
            'daily_foc_expected': round(float(r['predicted_foc']), 2),
            'residual_pct': round(float(r['residual_pct']), 2),
            'direction': r['direction'],
            'primary_cause': r['primary_cause'],
            'primary_cause_contribution_pct': round(float(r['primary_cause_shap']), 2),
            'cause_model_agrees': bool(r['cause_model_agrees']),
            'days_since_hull_clean': int(r['days_since_hull_clean']),
            'days_since_prop_polish': int(r['days_since_prop_polish']),
        })
    return items, total_days_analyzed


# ── DynamoDB ─────────────────────────────────────────────────────────────────

def to_dynamo_item(item: dict) -> dict:
    out = {}
    for k, v in item.items():
        if v is None:
            continue
        out[k] = Decimal(str(v)) if isinstance(v, float) else v
    return out


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
        KeySchema=[
            {'AttributeName': 'vessel_id', 'KeyType': 'HASH'},
            {'AttributeName': 'noon_day', 'KeyType': 'RANGE'},
        ],
        AttributeDefinitions=[
            {'AttributeName': 'vessel_id', 'AttributeType': 'S'},
            {'AttributeName': 'noon_day', 'AttributeType': 'N'},
        ],
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

    print("Training fleet-wide baseline + cause models (training vessels, calm-condition only) ...")
    baseline_model, cause_model, explainer, r2 = train_models(vessel_data, maint_data)

    print(f"\nClassifying anomalies for {len(ALL_VESSELS)} vessels ...")
    all_items = []
    for vid in ALL_VESSELS:
        items, total_days_analyzed = classify_vessel(
            vid, vessel_data.get(vid, []), maint_data.get(vid, []),
            baseline_model, cause_model, explainer,
        )
        all_items.append({
            'vessel_id': vid,
            'noon_day': -1,
            'total_days_analyzed': total_days_analyzed,
            'baseline_model_r2': round(float(r2), 4),
        })
        all_items.extend(items)
        breakdown: dict[str, int] = {}
        for it in items:
            breakdown[it['primary_cause']] = breakdown.get(it['primary_cause'], 0) + 1
        print(f"  {vid:4s}  anomalies={len(items):3d}  {breakdown}")

    if args.dry_run:
        print(f"\n[DRY RUN] {len(all_items)} total items. Sample:")
        print(all_items[0] if all_items else '(none)')
        return

    print(f"\nWriting to DynamoDB '{TABLE_NAME}' (region={REGION}) ...")
    write_to_dynamodb(all_items)
    print("Done.")


if __name__ == '__main__':
    main()
