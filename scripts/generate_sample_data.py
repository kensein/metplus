#!/usr/bin/env python3
"""Generate sample METplus STAT output and dashboard JSON for testing."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from lib.stat_parser import StatParser, aggregate_daily_stats  # noqa: E402


def generate_stat_line(
    valid: datetime,
    line_type: str,
    fcst_thresh: str = "gt5",
    extra: str = "",
) -> str:
    """Generate one STAT file line."""
    valid_str = valid.strftime("%Y%m%d_%H%M%S")
    init_str = (valid - timedelta(hours=12)).strftime("%Y%m%d_%H%M%S")
    base = (
        f"STAT V12.0.0 {datetime.now().strftime('%Y%m%d_%H%M%S')} "
        f"INANWP NA 000000 {valid_str} 000000 {valid_str} "
        f"{init_str} {init_str} NA RAINNC \"(*,*)\" hourlyPrecipRateGC \"(*,*)\" "
        f"mm mm {fcst_thresh} {fcst_thresh} NA 0.05 {line_type}"
    )
    return base + " " + extra


def generate_sample_stats(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stat_dir = output_dir / "gridstat"
    stat_dir.mkdir(exist_ok=True)

    # Generate 4 days x 24 hours = 96 valid times (27-30 July 2026)
    start = datetime(2026, 7, 27, 0, 0, 0)
    thresholds = ["gt0.1", "gt1", "gt5", "gt10", "gt20", "gt50"]

    all_lines = []
    for day in range(4):
        for hour in range(24):
            valid = start + timedelta(days=day, hours=hour)
            # Simulate diurnal cycle + some random variation
            base_rmse = 3.5 + 1.5 * abs(hour - 14) / 14
            base_me = 0.5 + 0.3 * (hour - 12) / 12
            base_acc = 0.65 + 0.1 * (1 - abs(hour - 14) / 14)
            base_ets = 0.35 + 0.05 * (1 - abs(hour - 14) / 14)

            for thresh in thresholds:
                thresh_val = float(thresh.replace("gt", ""))
                ets = max(0, base_ets - thresh_val * 0.005)

                # CNT line
                all_lines.append(generate_stat_line(
                    valid, "CNT", thresh,
                    f"10000 {base_me/5:.3f} {base_rmse+2:.3f} {base_rmse:.3f} "
                    f"{base_rmse-1:.3f} {base_rmse-0.5:.3f} {base_rmse:.3f} "
                    f"{base_rmse-0.8:.3f} {base_acc:.4f} {base_rmse**2:.3f} "
                    f"{base_rmse:.3f} 0.5 {base_rmse*0.8:.3f} {base_me:.3f} "
                    f"0.9 0.1 1.0 0.5 0.2 0.1 0.05 0.04 0.03",
                ))

                # CTS line
                all_lines.append(generate_stat_line(
                    valid, "CTS", thresh,
                    f"10000 {base_me/10:.3f} 0.45 {ets:.4f} 0.85 0.15 0.20 "
                    f"{ets+0.1:.4f} 0.30 0.40",
                ))

                # CTC line
                hits = int(500 + ets * 200)
                fa = int(200 - ets * 50)
                miss = int(300 - ets * 80)
                cn = int(8900 + ets * 100)
                all_lines.append(generate_stat_line(
                    valid, "CTC", thresh,
                    f"10000 {hits} {fa} {miss} {cn}",
                ))

    # Write per-day stat files
    for day in range(4):
        day_start = start + timedelta(days=day)
        day_str = day_start.strftime("%Y%m%d")
        day_lines = [l for l in all_lines if f" {day_str}_" in l]
        stat_file = stat_dir / f"{day_str}00" / f"grid_stat_{day_str}.stat"
        stat_file.parent.mkdir(parents=True, exist_ok=True)
        stat_file.write_text("\n".join(day_lines) + "\n")
        print(f"  Day {day_str}: {len(day_lines)} lines")

    print(f"Generated {len(all_lines)} STAT lines in {stat_dir}")

    # Export dashboard data
    parser = StatParser()
    stat_files = sorted(stat_dir.rglob("*.stat"))
    records = parser.parse_files(stat_files)

    dash_dir = output_dir / "dashboard"
    dash_dir.mkdir(exist_ok=True)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "INANWP",
        "observation": "GSMAP NRT",
        "domain": "Indonesia",
        "valid_times": sorted({r["valid"] for r in records}),
        "total_records": len(records),
        "metrics": aggregate_daily_stats(records),
    }

    with open(dash_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    import pandas as pd
    df = pd.DataFrame(records)
    df.to_csv(dash_dir / "verification_stats.csv", index=False)

    manifest = {
        "version": "1.0",
        "updated_at": summary["generated_at"],
        "files": {
            "summary": "summary.json",
            "stats": "verification_stats.csv",
        },
    }
    with open(dash_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Dashboard data exported to {dash_dir}")


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "sample_data"
    generate_sample_stats(out)
