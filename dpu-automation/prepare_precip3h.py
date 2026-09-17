#!/usr/bin/env python3
"""Extract 3-hour precip (RAINNC diff) from wrfout into CF-ish NetCDF for GridStat."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def parse_wrf_times(ds):
    raw = ds.variables["Times"][:]
    out = []
    for row in raw:
        if hasattr(row, "tobytes"):
            s = row.tobytes().decode("ascii", "ignore")
        else:
            s = "".join(chr(int(c)) for c in row if int(c) > 0)
        s = s.strip().replace("_", " ")
        out.append(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wrfout", required=True)
    ap.add_argument("--valid", required=True, help="YYYYMMDDHH end of 3h window (UTC)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--hours", type=int, default=3)
    args = ap.parse_args()

    end = datetime.strptime(args.valid, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    start = end - timedelta(hours=args.hours)

    ds = Dataset(args.wrfout)
    times = parse_wrf_times(ds)
    rain = ds.variables["RAINNC"]
    lat = np.array(ds.variables["XLAT"][0])
    lon = np.array(ds.variables["XLONG"][0])

    try:
        i1 = times.index(end)
        i0 = times.index(start)
    except ValueError as e:
        raise SystemExit(
            f"Valid window {start}..{end} not in wrfout times "
            f"({times[0]} .. {times[-1]}): {e}"
        )

    precip = np.array(rain[i1], dtype=np.float32) - np.array(rain[i0], dtype=np.float32)
    precip = np.maximum(precip, 0.0)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    # Prefer 1D lat/lon if lat/lon are constant along axes; else keep 2D
    if np.allclose(lat[:, 0:1], lat) and np.allclose(lon[0:1, :], lon):
        lat1 = lat[:, 0]
        lon1 = lon[0, :]
        use_1d = True
    else:
        use_1d = False

    nco = Dataset(out, "w", format="NETCDF4")
    nco.createDimension("lat", precip.shape[0])
    nco.createDimension("lon", precip.shape[1])
    if use_1d:
        vlat = nco.createVariable("lat", "f4", ("lat",))
        vlon = nco.createVariable("lon", "f4", ("lon",))
        vlat[:] = lat1
        vlon[:] = lon1
    else:
        vlat = nco.createVariable("lat", "f4", ("lat", "lon"))
        vlon = nco.createVariable("lon", "f4", ("lat", "lon"))
        vlat[:] = lat
        vlon[:] = lon
    vlat.units = "degrees_north"
    vlon.units = "degrees_east"
    vp = nco.createVariable("precip", "f4", ("lat", "lon"), zlib=True)
    vp.units = "mm"
    vp.long_name = f"{args.hours}-hour precipitation accumulation ending {args.valid}"
    vp[:] = precip
    nco.setncattr("valid", args.valid)
    nco.setncattr("source_wrfout", str(Path(args.wrfout).name))
    nco.close()
    print(f"OK wrote {out} shape={precip.shape} max={float(precip.max()):.3f}")


if __name__ == "__main__":
    main()
