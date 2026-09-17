#!/usr/bin/env python3
"""Sample GSMaP (or prepared precip NC) at BMKG station lat/lon → MET ASCII point obs.

Used for METplus PointStat vs InaNWP at all Indonesian stations.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def load_stations(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for rec in data:
        try:
            lat = float(rec["lat"])
            lon = float(rec["lon"])
            sid = str(rec.get("wmo_id") or "").strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not sid or not np.isfinite(lat) or not np.isfinite(lon):
            continue
        out.append({
            "sid": sid,
            "lat": lat,
            "lon": lon,
            "name": str(rec.get("name") or sid),
            "elev": float(rec.get("elevation") or 0.0),
        })
    return out


def sample_field(lat2d, lon2d, field, plat, plon):
    """Nearest-neighbor sample on lat/lon grid (1D or 2D)."""
    lat = np.asarray(lat2d, dtype=float)
    lon = np.asarray(lon2d, dtype=float)
    fld = np.asarray(field, dtype=float)
    if lat.ndim == 1 and lon.ndim == 1:
        i = int(np.abs(lat - plat).argmin())
        j = int(np.abs(lon - plon).argmin())
        return float(fld[i, j]) if fld.ndim == 2 else float(fld[j, i])
    # 2D curvilinear / WRF-like
    dist = (lat - plat) ** 2 + (lon - plon) ** 2
    iy, ix = np.unravel_index(int(np.nanargmin(dist)), dist.shape)
    return float(fld[iy, ix])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nc", required=True, help="Prepared GSMaP precip NC")
    ap.add_argument("--stations", required=True)
    ap.add_argument("--valid", required=True, help="YYYYMMDDHH")
    ap.add_argument("--out-ascii", required=True)
    ap.add_argument("--varname", default="precip")
    args = ap.parse_args()

    stations = load_stations(Path(args.stations))
    if not stations:
        raise SystemExit("No stations loaded")

    ds = Dataset(args.nc)
    # flexible var / coord names
    var = None
    for cand in (args.varname, "precip", "precip3h", "rain", "pr"):
        if cand in ds.variables:
            var = ds.variables[cand]
            break
    if var is None:
        raise SystemExit(f"No precip var in {args.nc}: {list(ds.variables)}")

    lat = None
    lon = None
    for la, lo in (("lat", "lon"), ("latitude", "longitude"), ("XLAT", "XLONG")):
        if la in ds.variables and lo in ds.variables:
            lat = np.array(ds.variables[la][:], dtype=float)
            lon = np.array(ds.variables[lo][:], dtype=float)
            break
    if lat is None:
        raise SystemExit("No lat/lon in NC")

    data = np.array(var[:], dtype=float)
    while data.ndim > 2:
        data = data[0]

    if lat.ndim == 3:
        lat = lat[0]
        lon = lon[0]

    valid = datetime.strptime(args.valid, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    # MET met_point ASCII: 11 columns
    # typ sid vld lat lon elv var lvl hgt qc obs
    lines = []
    values = []
    for st in stations:
        try:
            v = sample_field(lat, lon, data, st["lat"], st["lon"])
        except Exception:
            continue
        if not np.isfinite(v):
            continue
        values.append(v)
        # Surface point precip (name/level chosen for PointStat match vs NetCDF_NCCF precip)
        lines.append(
            f"ADPSFC {st['sid']} {valid.strftime('%Y%m%d_%H%M%S')} "
            f"{st['lat']:.5f} {st['lon']:.5f} {st['elev']:.1f} "
            f"precip 0 0 0 {max(0.0, v):.4f}"
        )

    out = Path(args.out_ascii)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "wrote": str(out),
        "n_stations": len(lines),
        "valid": args.valid,
        "mean_precip": float(np.mean(values)) if values else None,
    }))
    ds.close()


if __name__ == "__main__":
    main()
