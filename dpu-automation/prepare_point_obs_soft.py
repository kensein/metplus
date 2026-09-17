#!/usr/bin/env python3
"""Build MET point-obs ASCII from BMKG Soft / Sinoptik JSON (sama sumber HARP).

Multi-parameter: field names = HARP VERIFY_PARAMETERS ids (match fcst NC
from prepare_point_fcst_surface.py). Tidak memakai GSMaP sample di lat/lon.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

# Soft sentinel (selaras backend/services/obs_qc.py)
SENTINELS = {8888.0, 9999.0, -9999.0, 99999.0, -8888.0}

# HARP Soft params that PointStat verifies (overlap with wrfout surface)
POINTSTAT_PARAMS = [
    "temp_drybulb_c_tttttt",
    "temp_dewpoint_c_tdtdtd",
    "relative_humidity_pc",
    "pressure_qff_mb_derived",
    "pressure_qfe_mb_derived",
    "wind_speed_ff",
    "wind_dir_deg_dd",
    "rainfall_last_mm",
]


def load_stations(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    by_name: dict[str, str] = {}
    for rec in data:
        sid = str(rec.get("wmo_id") or "").strip()
        if not sid:
            continue
        try:
            lat = float(rec["lat"])
            lon = float(rec["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(lat) or not math.isfinite(lon):
            continue
        name = str(rec.get("name") or sid).strip()
        out[sid] = {
            "sid": sid,
            "lat": lat,
            "lon": lon,
            "name": name,
            "elev": float(rec.get("elevation") or 0.0),
        }
        if name:
            by_name[name.lower()] = sid
    out["_by_name"] = by_name  # type: ignore[assignment]
    return out


def resolve_sid(rec: dict, stations: dict[str, dict]) -> str:
    for key in ("station_wmo_id", "wmo_id", "station_id", "stationWmoId", "wmo"):
        if rec.get(key):
            return str(rec[key]).strip()
    name = str(rec.get("station_name") or "").strip().lower()
    by_name = stations.get("_by_name") or {}
    if name and name in by_name:
        return by_name[name]
    return ""


def flatten_records(raw):
    """Minimal flatten — selaras monas/obs_format untuk dict & list-of-list."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        if "records" in raw and isinstance(raw["records"], list):
            return flatten_records(raw["records"])
        for key in ("data", "results", "items", "observations", "rows"):
            if isinstance(raw.get(key), list):
                return flatten_records(raw[key])
        return [raw]
    if not isinstance(raw, list) or not raw:
        return []
    if isinstance(raw[0], dict):
        return raw
    return []


def parse_ts(val) -> datetime | None:
    if not val:
        return None
    s = str(val).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H"):
            try:
                dt = datetime.strptime(str(val)[:19], fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def soft_value(rec: dict, param: str) -> float | None:
    """Extract one Soft numeric field with HARP-like QC."""
    keys = [param]
    # light aliases / fallbacks
    if param == "rainfall_last_mm":
        keys = ["rainfall_last_mm", "rainfall_6h_rrr", "rainfall_24h_rrrr"]
    for key in keys:
        v = rec.get(key)
        if v in (None, "", "-"):
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(fv) or fv in SENTINELS:
            continue
        if param.startswith("rainfall") and fv >= 888.0:
            continue
        # Soft wind speed sometimes in knots-ish outliers; keep finite values
        if param == "relative_humidity_pc" and (fv < 0 or fv > 105):
            continue
        if param == "wind_dir_deg_dd":
            fv = fv % 360.0
        if param.startswith("rainfall"):
            fv = max(0.0, fv)
        return fv
    return None


def load_soft_obs(paths: list[Path], params: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        raw = json.loads(p.read_text(encoding="utf-8"))
        for rec in flatten_records(raw):
            if not isinstance(rec, dict):
                continue
            dt = parse_ts(rec.get("data_timestamp") or rec.get("valid_time") or rec.get("timestamp"))
            if not dt:
                continue
            vals = {}
            for param in params:
                fv = soft_value(rec, param)
                if fv is not None:
                    vals[param] = fv
            if not vals:
                continue
            rows.append({"rec": rec, "dt": dt, "vals": vals})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Soft/Sinoptik → MET met_point ASCII (multi-param)")
    ap.add_argument("--soft-json", nargs="+", required=True, help="sinoptik_*.json (HARP obs_export)")
    ap.add_argument("--stations", required=True, help="stations_bmkg.json")
    ap.add_argument("--valid", required=True, help="YYYYMMDDHH")
    ap.add_argument("--out-ascii", required=True)
    ap.add_argument(
        "--params",
        nargs="+",
        default=POINTSTAT_PARAMS,
        help="HARP param ids to emit (default: surface set)",
    )
    ap.add_argument("--tolerance-min", type=int, default=0, help="match obs within ±N minutes of valid")
    args = ap.parse_args()

    stations = load_stations(Path(args.stations))
    by_name = stations.pop("_by_name", {})
    stations["_by_name"] = by_name
    if len(stations) <= 1:
        print("ERROR: no stations in catalog", file=sys.stderr)
        return 1

    paths = [Path(p) for p in args.soft_json]
    for p in paths:
        if not p.is_file():
            print(f"ERROR: missing Soft JSON {p}", file=sys.stderr)
            return 1

    valid = datetime.strptime(args.valid, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    tol = abs(int(args.tolerance_min))
    params = list(args.params)
    rows = load_soft_obs(paths, params)

    by_sid: dict[str, dict] = {}
    for r in rows:
        sid = resolve_sid(r["rec"], stations)
        if not sid:
            continue
        if abs((r["dt"] - valid).total_seconds()) > tol * 60:
            if r["dt"].strftime("%Y%m%d%H") != args.valid:
                continue
        prev = by_sid.get(sid)
        if prev is None or abs((r["dt"] - valid).total_seconds()) < abs((prev["dt"] - valid).total_seconds()):
            by_sid[sid] = {**r, "sid": sid}

    lines = []
    counts: dict[str, int] = {p: 0 for p in params}
    matched_catalog = 0
    for sid, r in sorted(by_sid.items()):
        st = stations.get(sid)
        if not st or sid == "_by_name":
            continue
        matched_catalog += 1
        for param, v in r["vals"].items():
            if param not in params:
                continue
            counts[param] = counts.get(param, 0) + 1
            lines.append(
                f"ADPSFC {sid} {valid.strftime('%Y%m%d_%H%M%S')} "
                f"{st['lat']:.5f} {st['lon']:.5f} {st['elev']:.1f} "
                f"{param} 0 0 0 {float(v):.4f}"
            )

    out = Path(args.out_ascii)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    meta = {
        "wrote": str(out),
        "observation": "BMKG_SOFT",
        "parameters": params,
        "n_lines": len(lines),
        "n_stations": matched_catalog,
        "n_soft_hits": len(by_sid),
        "counts_by_param": counts,
        "valid": args.valid,
        "soft_files": [str(p) for p in paths],
    }
    print(json.dumps(meta, indent=2))
    if not lines:
        print("ERROR: no Soft values matched valid time", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
