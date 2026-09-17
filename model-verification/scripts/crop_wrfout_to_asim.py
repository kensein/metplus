#!/usr/bin/env python3
"""Crop wrfout WRF mentah → NC tipis ala asim untuk HARP.

PENTING: nama file output memakai START_DATE di dalam wrfout (bukan timestamp
nama file). Contoh: wrfout_d01_2026-09-16_00:00:00 dengan
START_DATE=2026-06-15_12:00:00 → 2026061512-d01-asim.nc

Usage:
  python scripts/crop_wrfout_to_asim.py \\
    --src /home/klimat/inanwp/wrfout_d01_2026-09-16_00:00:00 \\
    --dst-dir /home/dpu/data/harp_nc
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np


def _parse_start_date(raw: str) -> datetime:
    s = str(raw).strip().replace("T", "_")
    for fmt in ("%Y-%m-%d_%H:%M:%S", "%Y-%m-%d_%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized START_DATE: {raw!r}")


def crop(src: Path, dst_dir: Path, force: bool = False) -> Path:
    from netCDF4 import Dataset

    dst_dir.mkdir(parents=True, exist_ok=True)
    with Dataset(str(src), "r") as ds:
        start_raw = getattr(ds, "START_DATE", None) or getattr(ds, "SIMULATION_START_DATE", None)
        if not start_raw:
            raise RuntimeError(f"No START_DATE in {src}")
        init = _parse_start_date(start_raw)
        tag = init.strftime("%Y%m%d%H")
        out = dst_dir / f"{tag}-d01-asim.nc"
        if out.is_file() and not force:
            print(f"SKIP exists: {out}")
            return out

        if "XTIME" not in ds.variables:
            raise RuntimeError("XTIME missing — bukan wrfout WRF?")
        xtime = np.asarray(ds.variables["XTIME"][:], dtype=float)  # minutes
        n_t = len(xtime)
        lat = np.asarray(ds.variables["XLAT"][0] if ds.variables["XLAT"].ndim == 3 else ds.variables["XLAT"][:], dtype=np.float32)
        lon = np.asarray(ds.variables["XLONG"][0] if ds.variables["XLONG"].ndim == 3 else ds.variables["XLONG"][:], dtype=np.float32)
        ny, nx = lat.shape

        def read2d(name: str) -> np.ndarray:
            v = ds.variables[name]
            arr = np.asarray(v[:], dtype=np.float32)
            if arr.ndim == 3:
                return arr
            raise RuntimeError(f"{name} unexpected shape {arr.shape}")

        print(f"Reading surface fields from {src} ({n_t} times, {ny}x{nx})…", flush=True)
        t2 = read2d("T2") - 273.15  # °C
        u10 = read2d("U10")
        v10 = read2d("V10")
        psfc = read2d("PSFC") / 100.0  # Pa → hPa
        rainc = read2d("RAINC")
        rainnc = read2d("RAINNC")
        rainsh = read2d("RAINSH") if "RAINSH" in ds.variables else np.zeros_like(rainc)
        q2 = read2d("Q2") if "Q2" in ds.variables else None

        ws10 = np.sqrt(u10 * u10 + v10 * v10).astype(np.float32)
        # Meteorological wind direction (from)
        wd10 = (270.0 - np.degrees(np.arctan2(v10, u10))) % 360.0
        wd10 = wd10.astype(np.float32)

        # Approx RH from Q2 + T2 + PSFC (Magnus)
        rh2m = None
        if q2 is not None:
            # vapor pressure e ≈ q * p / (0.622 + 0.378 q); p in hPa
            e = q2 * psfc / (0.622 + 0.378 * q2)
            es = 6.112 * np.exp((17.67 * t2) / (t2 + 243.5))
            rh2m = np.clip(100.0 * e / np.maximum(es, 1e-6), 0.0, 100.0).astype(np.float32)

        rain = (rainc + rainnc + rainsh).astype(np.float32)

        times = [init + timedelta(minutes=float(m)) for m in xtime]
        # CF time: hours since init
        time_hours = np.asarray([(t - init).total_seconds() / 3600.0 for t in times], dtype=np.float64)

        # 1D lat/lon if regular; else keep 2D and also write as data vars
        lat_1d = lat[:, 0]
        lon_1d = lon[0, :]
        regular = (
            np.allclose(lat, lat_1d[:, None], atol=1e-3)
            and np.allclose(lon, lon_1d[None, :], atol=1e-3)
        )

    tmp = out.with_suffix(".nc.tmp")
    if tmp.exists():
        tmp.unlink()
    print(f"Writing {out} …", flush=True)
    with Dataset(str(tmp), "w", format="NETCDF4") as out_ds:
        out_ds.createDimension("time", n_t)
        out_ds.createDimension("lat", ny)
        out_ds.createDimension("lon", nx)
        out_ds.setncattr("START_DATE", init.strftime("%Y-%m-%d_%H:%M:%S"))
        out_ds.setncattr("title", "InaNWP surface crop for HARP (from wrfout)")
        out_ds.setncattr("source_file", str(src))
        out_ds.setncattr("Conventions", "CF-1.7")

        tv = out_ds.createVariable("time", "f8", ("time",))
        tv.units = f"hours since {init.strftime('%Y-%m-%d %H:%M:%S')}"
        tv.calendar = "standard"
        tv.standard_name = "time"
        tv[:] = time_hours

        if regular:
            lav = out_ds.createVariable("lat", "f4", ("lat",))
            lov = out_ds.createVariable("lon", "f4", ("lon",))
            lav.units = "degrees_north"
            lov.units = "degrees_east"
            lav[:] = lat_1d.astype(np.float32)
            lov[:] = lon_1d.astype(np.float32)
            dims2 = ("time", "lat", "lon")
        else:
            lav = out_ds.createVariable("lat", "f4", ("lat", "lon"))
            lov = out_ds.createVariable("lon", "f4", ("lat", "lon"))
            lav.units = "degrees_north"
            lov.units = "degrees_east"
            lav[:] = lat
            lov[:] = lon
            dims2 = ("time", "lat", "lon")

        def put(name, data, units, long_name):
            v = out_ds.createVariable(name, "f4", dims2, zlib=True, complevel=4)
            v.units = units
            v.long_name = long_name
            v[:] = data

        put("t2m", t2, "degC", "2m air temperature")
        put("u10", u10, "m s-1", "10m U wind")
        put("v10", v10, "m s-1", "10m V wind")
        put("ws10", ws10, "m s-1", "10m wind speed")
        put("wd10", wd10, "degree", "10m wind direction")
        put("pres", psfc, "hPa", "surface pressure")
        put("mslp", psfc, "hPa", "surface pressure (proxy MSLP)")
        put("rain", rain, "mm", "accumulated precip RAINC+RAINNC+RAINSH")
        put("rainc", rainc, "mm", "accumulated convective precip")
        put("rainnc", rainnc, "mm", "accumulated non-convective precip")
        put("rainsh", rainsh, "mm", "accumulated shallow precip")
        if rh2m is not None:
            put("rh2m", rh2m, "%", "2m relative humidity (approx from Q2)")

    os.replace(tmp, out)
    size_mb = out.stat().st_size / 1e6
    print(f"OK {out} ({size_mb:.1f} MB) init={tag} leads={n_t}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Path wrfout")
    ap.add_argument("--dst-dir", required=True, help="Output folder for *-d01-asim.nc")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    src = Path(args.src)
    if not src.is_file():
        print(f"ERROR: missing {src}", file=sys.stderr)
        return 1
    crop(src, Path(args.dst_dir), force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
