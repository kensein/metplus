#!/usr/bin/env python3
"""Sum GSMAP hourly rainrate files into 3h precip NetCDF."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def find_var(ds, names):
    for n in names:
        if n in ds.variables:
            return n
    # fuzzy
    for n in ds.variables:
        low = n.lower()
        if "rain" in low or "precip" in low:
            return n
    raise KeyError(f"No rain var in {list(ds.variables)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--valid", required=True, help="YYYYMMDDHH end of window")
    ap.add_argument("--out", required=True)
    ap.add_argument("--hours", type=int, default=3)
    args = ap.parse_args()

    end = datetime.strptime(args.valid, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    hours = [end - timedelta(hours=h) for h in range(args.hours, 0, -1)]
    # For valid 15Z with 3h accum of hours 12,13,14: end-3 .. end-1
    files = []
    raw = Path(args.raw_dir)
    for t in hours:
        # GSMaP_YYYYMMDDHH00.nc patterns seen on DPU
        candidates = [
            raw / f"GSMaP_{t.strftime('%Y%m%d%H')}00.nc",
            raw / f"GSMaP_{t.strftime('%Y%m%d%H')}.nc",
            raw / f"gsmap_{t.strftime('%Y%m%d%H')}.nc",
        ]
        hit = next((p for p in candidates if p.exists()), None)
        if not hit:
            raise SystemExit(f"Missing GSMAP for {t.strftime('%Y%m%d%H')}: tried {[str(c) for c in candidates]}")
        files.append(hit)

    arrays = []
    lat = lon = None
    varname = None
    for f in files:
        ds = Dataset(f)
        varname = varname or find_var(ds, ["rainrate", "hourlyPrecipRateGC", "precip", "precipRate"])
        data = np.array(ds.variables[varname][:], dtype=np.float64)
        if data.ndim == 3:
            data = data[0]
        arrays.append(data)
        if lat is None:
            for la, lo in (("lat", "lon"), ("latitude", "longitude"), ("LAT", "LON")):
                if la in ds.variables and lo in ds.variables:
                    lat = np.array(ds.variables[la][:])
                    lon = np.array(ds.variables[lo][:])
                    break
        ds.close()

    precip = np.sum(arrays, axis=0).astype(np.float32)
    precip[precip < -9000] = np.nan

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    nco = Dataset(out, "w", format="NETCDF4")
    if lat.ndim == 1:
        nco.createDimension("lat", lat.shape[0])
        nco.createDimension("lon", lon.shape[0])
        vlat = nco.createVariable("lat", "f4", ("lat",))
        vlon = nco.createVariable("lon", "f4", ("lon",))
        vlat[:] = lat
        vlon[:] = lon
        dims = ("lat", "lon")
    else:
        nco.createDimension("y", precip.shape[0])
        nco.createDimension("x", precip.shape[1])
        vlat = nco.createVariable("lat", "f4", ("y", "x"))
        vlon = nco.createVariable("lon", "f4", ("y", "x"))
        vlat[:] = lat
        vlon[:] = lon
        dims = ("y", "x")
    vlat.units = "degrees_north"
    vlon.units = "degrees_east"
    vp = nco.createVariable("precip", "f4", dims, zlib=True)
    vp.units = "mm"
    vp.long_name = f"GSMaP {args.hours}h rainrate sum ending {args.valid}"
    vp[:] = precip
    nco.setncattr("source_files", ",".join(p.name for p in files))
    nco.close()
    print(f"OK wrote {out} from {[p.name for p in files]} max={float(np.nanmax(precip)):.3f}")


if __name__ == "__main__":
    main()
