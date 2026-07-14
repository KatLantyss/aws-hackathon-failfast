"""
批次預測腳本：讀取 vt_fd.csv 的所有 PREDICT 標記列，
呼叫已部署的 POST /api/v1/predict/fuel-consumption，
輸出符合題目格式的提交 CSV。

使用方式：
    python3 predict_submit.py                          # 預設打 CloudFront
    python3 predict_submit.py --url http://localhost:8000
    python3 predict_submit.py --output my_submission.csv

提交格式：
    ship_id, day, fuel_type, predicted_value
"""

import argparse
import csv
import sys
import time
import urllib.request
import urllib.error
import json
import pathlib

# ── 設定 ──────────────────────────────────────────────────────────────────────

DEFAULT_API_URL = "https://d1yvzz0da29zvi.cloudfront.net"
DATA_PATH = pathlib.Path(__file__).parent.parent / "backend/hackathon-data/vt_fd.csv"
DEFAULT_OUTPUT = pathlib.Path(__file__).parent / "submission.csv"

FUEL_COLS = [
    "ME_FULLSPEED_CONSUMP_HSHFO",
    "ME_FULLSPEED_CONSUMP_ULSFO",
    "ME_FULLSPEED_CONSUMP_VLSFO",
    "ME_FULLSPEED_CONSUMP_LSMGO",
    "ME_FULLSPEED_CONSUMP_BIO_HSFO",
]


# ── Helper ────────────────────────────────────────────────────────────────────

def post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def read_predict_rows(csv_path: pathlib.Path) -> list[dict]:
    """Return all rows where any fuel col is 'PREDICT'."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fuel_col = next((c for c in FUEL_COLS if row.get(c) == "PREDICT"), None)
            if fuel_col:
                rows.append({
                    "ship_id":   row["De-identification Name"],
                    "noon_day":  float(row["NOON_UTC"]),
                    "fuel_type": fuel_col,
                    # extra A-class fields for debugging
                    "_avg_speed": row.get("AVG_SPEED"),
                    "_wind":      row.get("WIND_SCALE"),
                })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="批次預測 → 提交 CSV")
    parser.add_argument("--url",    default=DEFAULT_API_URL, help="API base URL")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="輸出 CSV 路徑")
    parser.add_argument("--delay",  type=float, default=0.1, help="每次 call 的間隔秒數（避免打爆 API）")
    parser.add_argument("--verbose", action="store_true", help="顯示每筆預測結果")
    args = parser.parse_args()

    predict_url = args.url.rstrip("/") + "/api/v1/predict/fuel-consumption"
    print(f"API endpoint : {predict_url}")
    print(f"Data source  : {DATA_PATH}")
    print(f"Output       : {args.output}")
    print()

    # 讀取所有 PREDICT 列
    predict_rows = read_predict_rows(DATA_PATH)
    total = len(predict_rows)
    print(f"Found {total} PREDICT rows to predict\n")

    results = []
    errors  = []

    for i, row in enumerate(predict_rows, 1):
        payload = {
            "vessel_id": row["ship_id"],
            "noon_day":  row["noon_day"],
        }

        try:
            resp = post_json(predict_url, payload)
            predicted = resp.get("predicted_consumption_mt")

            if predicted is None:
                raise ValueError(f"No predicted_consumption_mt in response: {resp}")

            # Clamp to physically plausible range (MT/day for main engine full speed)
            # Training data range is roughly 30–110 MT/day; anything outside is likely
            # a model artefact (edge case near dry-dock with extreme feature values).
            predicted_clamped = max(30.0, min(predicted, 120.0))
            if predicted != predicted_clamped:
                print(f"\n  ⚡ Clamped {row['ship_id']} day={int(row['noon_day'])}: "
                      f"{predicted:.2f} → {predicted_clamped:.2f}")
                predicted = predicted_clamped

            results.append({
                "ship_id":         row["ship_id"],
                "day":             int(row["noon_day"]),
                "fuel_type":       row["fuel_type"],
                "predicted_value": round(predicted, 4),
            })

            if args.verbose:
                print(f"[{i:3d}/{total}] {row['ship_id']}  day={int(row['noon_day']):4d}  "
                      f"{row['fuel_type']:<35s}  → {predicted:.2f} MT/day")
            else:
                # 進度條
                pct = i / total
                bar = "█" * int(pct * 30) + "░" * (30 - int(pct * 30))
                print(f"\r[{bar}] {i}/{total}  {row['ship_id']} day={int(row['noon_day'])}", end="", flush=True)

        except Exception as e:
            errors.append({"row": row, "error": str(e)})
            print(f"\n  ⚠️  [{i}/{total}] {row['ship_id']} day={int(row['noon_day'])} ERROR: {e}")

        if args.delay > 0:
            time.sleep(args.delay)

    print()  # newline after progress bar

    # 輸出 CSV
    out_path = pathlib.Path(args.output)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ship_id", "day", "fuel_type", "predicted_value"])
        writer.writeheader()
        writer.writerows(results)

    # 摘要
    print(f"\n{'='*50}")
    print(f"✅  成功預測: {len(results)}/{total}")
    if errors:
        print(f"❌  失敗: {len(errors)}")
        for e in errors:
            print(f"    - {e['row']['ship_id']} day={int(e['row']['noon_day'])}: {e['error']}")
    print(f"📄  輸出檔案: {out_path.resolve()}")

    # 預覽前 5 筆
    print(f"\n--- Preview (first 5 rows) ---")
    print(f"{'ship_id':<8} {'day':>5}  {'fuel_type':<35s}  predicted_value")
    print("-" * 65)
    for r in results[:5]:
        print(f"{r['ship_id']:<8} {r['day']:>5}  {r['fuel_type']:<35s}  {r['predicted_value']}")

    # 統計
    if results:
        vals = [r["predicted_value"] for r in results]
        print(f"\n--- Stats ---")
        print(f"  min  : {min(vals):.2f} MT/day")
        print(f"  max  : {max(vals):.2f} MT/day")
        print(f"  mean : {sum(vals)/len(vals):.2f} MT/day")
        by_ship = {}
        for r in results:
            by_ship.setdefault(r["ship_id"], []).append(r["predicted_value"])
        for ship, v in sorted(by_ship.items()):
            print(f"  {ship}: {len(v)} rows, mean={sum(v)/len(v):.2f}")


if __name__ == "__main__":
    main()
