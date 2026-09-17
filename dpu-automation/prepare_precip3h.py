#!/usr/bin/env python3
"""Extract 3-hour total precip (RAINNC+RAINC+RAINSH) from wrfout for GridStat."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def parse_wrf_times(ds):
    """Build UTC times from Times or XTIME + START_DATE."""
    if "Times" in ds.variables:
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

    if "XTIME" not in ds.variables:
        raise SystemExit("wrfout has neither Times nor XTIME")
    start_raw = None
    for key in ("START_DATE", "SIMULATION_START_DATE"):
        if key in ds.ncattrs():
            start_raw = getattr(ds, key)
            break
    if not start_raw:
        units = getattr(ds.variables["XTIME"], "units", "")
        # minutes since YYYY-mm-dd HH:MM:SS
        if "since" in units:
            start_raw = units.split("since", 1)[1].strip().replace(" ", "_", 1)
    if not start_raw:
        raise SystemExit("Cannot determine START_DATE")
    start = datetime.strptime(str(start_raw).strip(), "%Y-%m-%d_%H:%M:%S").replace(tzinfo=timezone.utc)
    xt = np.array(ds.variables["XTIME"][:], dtype=float)
    return [start + timedelta(minutes=float(m)) for m in xt]


def total_rain(ds, idx):
    """Accumulated total precip at time index: RAINNC + RAINC + RAINSH."""
    total = np.array(ds.variables["RAINNC"][idx], dtype=np.float64)
    for name in ("RAINC", "RAINSH"):
        if name in ds.variables:
            total = total + np.array(ds.variables[name][idx], dtype=np.float64)
    return total.astype(np.float32)


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
    xlat = np.array(ds.variables["XLAT"][:])
    xlon = np.array(ds.variables["XLONG"][:])
    # WRF often has time dim on XLAT/XLONG
    if xlat.ndim == 3:
        lat = xlat[0]
        lon = xlon[0]
    else:
        lat = xlat
        lon = xlon

    try:
        i1 = times.index(end)
        i0 = times.index(start)
    except ValueError as e:
        raise SystemExit(
            f"Valid window {start}..{end} not in wrfout times "
            f"({times[0]} .. {times[-1]}): {e}"
        )

    precip = total_rain(ds, i1) - total_rain(ds, i0)
    precip = np.maximum(precip, 0.0)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    use_1d = False
    lat1 = lon1 = None
    if lat.ndim == 1 and lon.ndim == 1:
        use_1d = True
        lat1, lon1 = lat, lon
    elif lat.ndim == 2 and lon.ndim == 2:
        if np.allclose(lat[:, 0:1], lat) and np.allclose(lon[0:1, :], lon):
            use_1d = True
            lat1 = lat[:, 0]
            lon1 = lon[0, :]
    else:
        raise SystemExit(f"Unexpected lat/lon shapes: {lat.shape} {lon.shape}")

    # NETCDF3_CLASSIC + CF attrs so MET opens via NETCDF_NCCF
    nco = Dataset(out, "w", format="NETCDF3_CLASSIC")
    nco.createDimension("time", 1)
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
    vlat.long_name = "latitude"
    vlat.standard_name = "latitude"
    vlon.units = "degrees_east"
    vlon.long_name = "longitude"
    vlon.standard_name = "longitude"

    vtime = nco.createVariable("time", "f8", ("time",))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    vtime[:] = [(end - epoch).total_seconds() / 60.0]
    vtime.units = "minutes since 1970-01-01 00:00:00"
    vtime.calendar = "gregorian"
    vtime.standard_name = "time"
    vtime.long_name = "valid time (end of accumulation)"

    vp = nco.createVariable(
        "precip", "f4", ("time", "lat", "lon"), fill_value=np.float32(-9999.0)
    )
    vp.units = "mm"
    vp.long_name = (
        f"{args.hours}-hour total precip (RAINNC+RAINC+RAINSH) ending {args.valid}"
    )
    vp.standard_name = "precipitation_amount"
    vp.coordinates = "time lat lon"
    vp[0, :, :] = precip
    nco.setncattr("valid", args.valid)
    nco.setncattr("precip_components", "RAINNC+RAINC+RAINSH")
    nco.setncattr("source_wrfout", str(Path(args.wrfout).name))
    nco.setncattr("title", "InaNWP 3h total precip from RAINNC+RAINC+RAINSH")
    nco.setncattr("Conventions", "CF-1.6")
    nco.close()
    print(
        f"OK wrote {out} shape={precip.shape} max={float(precip.max()):.3f} "
        f"(RAINNC+RAINC+RAINSH)"
    )


if __name__ == "__main__":
    main()
