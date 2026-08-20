#!/usr/bin/env python3
"""
Export output METplus (STAT files) ke format JSON/CSV untuk dashboard.

Dijalankan di server litbangweb setelah run_verification.sh selesai.
Output disimpan di /mnt/wdd1/www/htdocs/wrf/metplus/dashboard/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow import from dashboard lib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

from lib.stat_parser import StatParser, aggregate_daily_stats  # noqa: E402


def export_dashboard(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    parser = StatParser()
    stat_files = sorted(input_dir.rglob("*.stat"))
    if not stat_files:
        print(f"Tidak ada file .stat di {input_dir}")
        return

    print(f"Memproses {len(stat_files)} file STAT...")
    records = parser.parse_files(stat_files)

    # Summary JSON (untuk dashboard)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "INANWP",
        "observation": "GSMAP NRT",
        "domain": "Indonesia",
        "valid_times": sorted({r["valid"] for r in records if r.get("valid")}),
        "total_records": len(records),
        "metrics": aggregate_daily_stats(records),
    }

    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  -> {summary_path}")

    # Full records CSV
    import pandas as pd

    df = pd.DataFrame(records)
    csv_path = output_dir / "verification_stats.csv"
    df.to_csv(csv_path, index=False)
    print(f"  -> {csv_path}")

    # CNT metrics per valid time (untuk time series)
    cnt_df = df[df["line_type"] == "CNT"].copy()
    if not cnt_df.empty:
        ts_path = output_dir / "timeseries_cnt.json"
        ts_data = cnt_df.groupby("valid").apply(
            lambda g: g[["fcst_thresh", "rmse", "me", "acc", "ets", "bias"]].to_dict("records")
        ).to_dict()
        with open(ts_path, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in ts_data.items()}, f, indent=2)
        print(f"  -> {ts_path}")

    # Metadata manifest
    manifest = {
        "version": "1.0",
        "updated_at": summary["generated_at"],
        "files": {
            "summary": "summary.json",
            "stats": "verification_stats.csv",
            "timeseries": "timeseries_cnt.json",
        },
    }
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"  -> {manifest_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, help="Direktori gridstat METplus")
    ap.add_argument("--output-dir", required=True, help="Direktori output dashboard")
    args = ap.parse_args()
    export_dashboard(Path(args.input_dir), Path(args.output_dir))


if __name__ == "__main__":
    main()
