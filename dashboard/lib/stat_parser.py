"""Parser untuk file output METplus GridStat (.stat)."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

# Header kolom STAT file MET (GridStat) - termasuk record type "STAT"
STAT_HEADER = [
    "record_type", "version", "gen_date", "model", "desc", "fcst_lead", "fcst_valid",
    "obs_lead", "obs_valid", "fcst_init", "obs_init", "mode", "fcst_var",
    "fcst_lev", "obs_var", "obs_lev", "fcst_units", "obs_units",
    "fcst_thresh", "obs_thresh", "cov_thresh", "alpha", "line_type",
]

# Kolom tambahan per line type
LINE_TYPE_COLUMNS: dict[str, list[str]] = {
    "FHO": ["total", "f_rate", "o_rate", "min_thresh", "max_thresh"],
    "CTC": ["total", "fy_oy", "fy_on", "fn_oy", "fn_on"],
    "CTS": ["total", "bias", "hss", "ets", "acc", "mr", "far", "csi", "gerrity", "hss_ec"],
    "MCTC": ["total", "fy_oy", "fy_on", "fn_oy", "fn_on"],
    "MCTS": ["total", "bias", "hss", "ets", "acc", "mr", "far", "csi", "gerrity", "hss_ec"],
    "CNT": [
        "total", "fbias", "fbar", "obar", "fbar_ncl", "obar_ncl",
        "fbar_tcl", "obar_tcl", "acc", "mse", "rmse", "mse_ss",
        "mae", "me", "cop", "add", "mul", "sdbar", "me2",
        "anom_corr", "me_tss", "me_tss_acc", "me_tss_rmse",
    ],
    "SL1L2": ["total", "fbar", "obar", "fobar", "ffbar", "oobar", "ffo3", "ffo"],
    "VL1L2": ["total", "fbias", "fbar", "obar", "fbar_ncl", "obar_ncl", "fbar_tcl", "obar_tcl"],
    "VCNT": ["total", "fbias", "fbar", "obar", "fbar_ncl", "obar_ncl", "fbar_tcl", "obar_tcl", "acc", "rmse", "me"],
    "NBRCTC": ["total", "fy_oy", "fy_on", "fn_oy", "fn_on"],
    "NBRCTS": ["total", "bias", "hss", "ets", "acc", "mr", "far", "csi", "gerrity", "hss_ec"],
    "NBRCNT": ["total", "fbias", "fbar", "obar", "fbar_ncl", "obar_ncl", "acc", "rmse", "me"],
    "DMAP": ["total", "med", "pmed", "ratio"],
    "GRAD": ["total", "fgbar", "ogbar", "fgoba", "fgbar_o", "fgbar_n", "ogbar_o", "ogbar_n"],
}


class StatParser:
    """Parse METplus GridStat STAT output files."""

    @staticmethod
    def _split_line(line: str) -> list[str]:
        """Split STAT line respecting quoted fields."""
        return shlex.split(line)

    def parse_file(self, path: Path) -> list[dict[str, Any]]:
        records = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = self._split_line(line)
                if len(parts) < len(STAT_HEADER):
                    continue

                header_vals = parts[: len(STAT_HEADER)]
                record = dict(zip(STAT_HEADER, header_vals))

                line_type = record["line_type"]
                extra_cols = LINE_TYPE_COLUMNS.get(line_type, [])
                extra_vals = parts[len(STAT_HEADER) : len(STAT_HEADER) + len(extra_cols)]

                for col, val in zip(extra_cols, extra_vals):
                    try:
                        record[col] = float(val)
                    except ValueError:
                        record[col] = val

                record["source_file"] = path.name
                record["valid"] = record.get("fcst_valid", "")
                records.append(record)

        return records

    def parse_files(self, paths: list[Path]) -> list[dict[str, Any]]:
        all_records = []
        for p in paths:
            all_records.extend(self.parse_file(p))
        return all_records


def aggregate_daily_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Agregasi metrik CNT per hari untuk summary dashboard."""
    cnt_records = [r for r in records if r.get("line_type") == "CNT"]
    if not cnt_records:
        return {}

    by_date: dict[str, list[dict]] = {}
    for r in cnt_records:
        valid = r.get("valid", "")
        if len(valid) >= 8:
            date = valid[:8]
            by_date.setdefault(date, []).append(r)

    daily = {}
    for date, recs in sorted(by_date.items()):
        rmse_vals = [r["rmse"] for r in recs if isinstance(r.get("rmse"), float)]
        me_vals = [r["me"] for r in recs if isinstance(r.get("me"), float)]
        acc_vals = [r["acc"] for r in recs if isinstance(r.get("acc"), float)]

        daily[date] = {
            "n_hours": len(recs),
            "rmse_mean": round(sum(rmse_vals) / len(rmse_vals), 3) if rmse_vals else None,
            "me_mean": round(sum(me_vals) / len(me_vals), 3) if me_vals else None,
            "acc_mean": round(sum(acc_vals) / len(acc_vals), 3) if acc_vals else None,
        }

    # Overall
    all_rmse = [r["rmse"] for r in cnt_records if isinstance(r.get("rmse"), float)]
    all_me = [r["me"] for r in cnt_records if isinstance(r.get("me"), float)]
    all_acc = [r["acc"] for r in cnt_records if isinstance(r.get("acc"), float)]

    return {
        "overall": {
            "rmse_mean": round(sum(all_rmse) / len(all_rmse), 3) if all_rmse else None,
            "me_mean": round(sum(all_me) / len(all_me), 3) if all_me else None,
            "acc_mean": round(sum(all_acc) / len(all_acc), 3) if all_acc else None,
            "n_records": len(cnt_records),
        },
        "daily": daily,
    }
