#!/usr/bin/env python3
"""Sum GSMAP hourly rainrate files into 3h precip NetCDF (CF, MET NETCDF_NCCF)."""
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
    files = []
    raw = Path(args.raw_dir)
    for t in hours:
        candidates = [
            raw / f"GSMaP_{t.strftime('%Y%m%d%H')}00.nc",
            raw / f"GSMaP_{t.strftime('%Y%m%d%H')}.nc",
            raw / f"gsmap_{t.strftime('%Y%m%d%H')}.nc",
        ]
        hit = next((p for p in candidates if p.exists()), None)
        if not hit:
            raise SystemExit(
                f"Missing GSMAP for {t.strftime('%Y%m%d%H')}: "
                f"tried {[str(c) for c in candidates]}"
            )
        files.append(hit)

    arrays = []
    lat = lon = None
    varname = None
    for f in files:
        ds = Dataset(f)
        varname = varname or find_var(
            ds, ["rainrate", "hourlyPrecipRateGC", "precip", "precipRate"]
        )
        data = np.array(ds.variables[varname][:], dtype=np.float64)
        if data.ndim == 3:
            data = data[0]
        arrays.append(data)
        if lat is None:
            for la, lo in (
                ("lat", "lon"),
                ("latitude", "longitude"),
                ("LAT", "LON"),
            ):
                if la in ds.variables and lo in ds.variables:
                    lat = np.array(ds.variables[la][:], dtype=np.float64)
                    lon = np.array(ds.variables[lo][:], dtype=np.float64)
                    break
        ds.close()

    if lat is None or lon is None:
        raise SystemExit("No lat/lon found in GSMAP files")

    precip = np.sum(arrays, axis=0).astype(np.float32)
    # GSMaP missing often <= -9990; keep finite for MET
    precip = np.where(precip < -9000, np.float32(-9999.0), precip)

    # Prefer -180..180 so MET LatLon overlaps Indonesia domain cleanly
    if lon.ndim == 1 and float(np.nanmax(lon)) > 180.0:
        lon = np.where(lon > 180.0, lon - 360.0, lon)
        order = np.argsort(lon)
        lon = lon[order]
        precip = precip[:, order]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    # NETCDF3_CLASSIC is widely readable by MET NcCfFile
    nco = Dataset(out, "w", format="NETCDF3_CLASSIC")
    nco.createDimension("time", 1)
    if lat.ndim == 1:
        nco.createDimension("lat", lat.shape[0])
        nco.createDimension("lon", lon.shape[0])
        vlat = nco.createVariable("lat", "f4", ("lat",))
        vlon = nco.createVariable("lon", "f4", ("lon",))
        vlat[:] = lat.astype(np.float32)
        vlon[:] = lon.astype(np.float32)
        dims = ("time", "lat", "lon")
        precip_out = precip[np.newaxis, :, :]
    else:
        nco.createDimension("y", precip.shape[0])
        nco.createDimension("x", precip.shape[1])
        vlat = nco.createVariable("lat", "f4", ("y", "x"))
        vlon = nco.createVariable("lon", "f4", ("y", "x"))
        vlat[:] = lat.astype(np.float32)
        vlon[:] = lon.astype(np.float32)
        dims = ("time", "y", "x")
        precip_out = precip[np.newaxis, :, :]

    vlat.units = "degrees_north"
    vlat.long_name = "latitude"
    vlat.standard_name = "latitude"
    vlon.units = "degrees_east"
    vlon.long_name = "longitude"
    vlon.standard_name = "longitude"

    vtime = nco.createVariable("time", "f8", ("time",))
    # minutes since 1970-01-01 for MET valid time
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    vtime[:] = [(end - epoch).total_seconds() / 60.0]
    vtime.units = "minutes since 1970-01-01 00:00:00"
    vtime.calendar = "gregorian"
    vtime.standard_name = "time"
    vtime.long_name = "valid time (end of accumulation)"

    vp = nco.createVariable("precip", "f4", dims, fill_value=np.float32(-9999.0))
    vp.units = "mm"
    vp.long_name = f"GSMaP {args.hours}h rainrate sum ending {args.valid}"
    vp.standard_name = "precipitation_amount"
    vp.coordinates = "time lat lon"
    vp[:] = precip_out

    nco.setncattr("title", f"GSMaP {args.hours}h precip ending {args.valid}")
    nco.setncattr("source_files", ",".join(p.name for p in files))
    nco.setncattr("valid", args.valid)
    nco.setncattr("Conventions", "CF-1.6")
    nco.close()

    finite = precip[precip > -9000]
    print(
        f"OK wrote {out} from {[p.name for p in files]} "
        f"max={float(np.max(finite)) if finite.size else 0:.3f}"
    )


if __name__ == "__main__":
    main()
