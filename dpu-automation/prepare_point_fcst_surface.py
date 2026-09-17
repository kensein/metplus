#!/usr/bin/env python3
"""Extract multi-parameter surface fields from wrfout for METplus PointStat.

Field names match HARP VERIFY_PARAMETERS ids so Soft obs ASCII and STAT
FCST_VAR align with the dashboard parameter selector.

Available (wrfout surface):
  temp_drybulb_c_tttttt, temp_dewpoint_c_tdtdtd, relative_humidity_pc,
  pressure_qff_mb_derived, pressure_qfe_mb_derived,
  wind_speed_ff, wind_dir_deg_dd, rainfall_last_mm (3h accum delta).

Cloud / Tmax / Tmin / visibility are omitted — not present on this wrfout.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


# HARP id → (units, long_name)
PARAM_META = {
    "temp_drybulb_c_tttttt": ("degC", "2m air temperature"),
    "temp_dewpoint_c_tdtdtd": ("degC", "2m dewpoint (from Q2)"),
    "relative_humidity_pc": ("%", "2m relative humidity (from Q2)"),
    "pressure_qff_mb_derived": ("hPa", "surface pressure (MSLP proxy)"),
    "pressure_qfe_mb_derived": ("hPa", "surface pressure"),
    "wind_speed_ff": ("m/s", "10m wind speed"),
    "wind_dir_deg_dd": ("degree", "10m wind direction (from)"),
    "rainfall_last_mm": ("mm", "3h total precip RAINNC+RAINC+RAINSH"),
}


def parse_wrf_times(ds):
    if "Times" in ds.variables:
        out = []
        for row in ds.variables["Times"][:]:
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
        if "since" in units:
            start_raw = units.split("since", 1)[1].strip().replace(" ", "_", 1)
    if not start_raw:
        raise SystemExit("Cannot determine START_DATE")
    start = datetime.strptime(str(start_raw).strip(), "%Y-%m-%d_%H:%M:%S").replace(tzinfo=timezone.utc)
    xt = np.array(ds.variables["XTIME"][:], dtype=float)
    return [start + timedelta(minutes=float(m)) for m in xt]


def total_rain(ds, idx):
    total = np.array(ds.variables["RAINNC"][idx], dtype=np.float64)
    for name in ("RAINC", "RAINSH"):
        if name in ds.variables:
            total = total + np.array(ds.variables[name][idx], dtype=np.float64)
    return total.astype(np.float32)


def magnus_rh_td(t2_c, q2, psfc_hpa):
    """RH (%) and dewpoint (°C) from T2, Q2, PSFC."""
    e = q2 * psfc_hpa / (0.622 + 0.378 * q2)
    e = np.maximum(e, 1e-6)
    es = 6.112 * np.exp((17.67 * t2_c) / (t2_c + 243.5))
    rh = np.clip(100.0 * e / np.maximum(es, 1e-6), 0.0, 100.0).astype(np.float32)
    ln = np.log(e / 6.112)
    td = (243.5 * ln / (17.67 - ln)).astype(np.float32)
    return rh, td


def lat_lon(ds):
    xlat = np.array(ds.variables["XLAT"][:])
    xlon = np.array(ds.variables["XLONG"][:])
    if xlat.ndim == 3:
        return xlat[0], xlon[0]
    return xlat, xlon


def main() -> int:
    ap = argparse.ArgumentParser(description="wrfout → multi-param surface NC for PointStat")
    ap.add_argument("--wrfout", required=True)
    ap.add_argument("--valid", required=True, help="YYYYMMDDHH valid time (UTC)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--precip-hours", type=int, default=3)
    args = ap.parse_args()

    valid = datetime.strptime(args.valid, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    precip_start = valid - timedelta(hours=args.precip_hours)

    ds = Dataset(args.wrfout)
    times = parse_wrf_times(ds)
    try:
        i1 = times.index(valid)
    except ValueError as e:
        raise SystemExit(f"valid {valid} not in wrfout ({times[0]}..{times[-1]}): {e}") from e
    try:
        i0 = times.index(precip_start)
    except ValueError as e:
        raise SystemExit(
            f"precip window start {precip_start} not in wrfout: {e}"
        ) from e

    lat, lon = lat_lon(ds)
    t2 = np.array(ds.variables["T2"][i1], dtype=np.float32) - 273.15
    u10 = np.array(ds.variables["U10"][i1], dtype=np.float32)
    v10 = np.array(ds.variables["V10"][i1], dtype=np.float32)
    psfc = np.array(ds.variables["PSFC"][i1], dtype=np.float32) / 100.0
    ws = np.sqrt(u10 * u10 + v10 * v10).astype(np.float32)
    wd = ((270.0 - np.degrees(np.arctan2(v10, u10))) % 360.0).astype(np.float32)
    precip = np.maximum(total_rain(ds, i1) - total_rain(ds, i0), 0.0)

    fields = {
        "temp_drybulb_c_tttttt": t2,
        "pressure_qff_mb_derived": psfc,
        "pressure_qfe_mb_derived": psfc,
        "wind_speed_ff": ws,
        "wind_dir_deg_dd": wd,
        "rainfall_last_mm": precip,
    }
    if "Q2" in ds.variables:
        q2 = np.array(ds.variables["Q2"][i1], dtype=np.float32)
        rh, td = magnus_rh_td(t2, q2, psfc)
        fields["relative_humidity_pc"] = rh
        fields["temp_dewpoint_c_tdtdtd"] = td
    ds.close()

    use_1d = False
    lat1 = lon1 = None
    if lat.ndim == 2 and lon.ndim == 2:
        if np.allclose(lat[:, 0:1], lat, atol=1e-3) and np.allclose(lon[0:1, :], lon, atol=1e-3):
            use_1d = True
            lat1, lon1 = lat[:, 0], lon[0, :]
    elif lat.ndim == 1 and lon.ndim == 1:
        use_1d = True
        lat1, lon1 = lat, lon

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    nco = Dataset(out, "w", format="NETCDF3_CLASSIC")
    nco.createDimension("time", 1)
    nco.createDimension("lat", fields["temp_drybulb_c_tttttt"].shape[0])
    nco.createDimension("lon", fields["temp_drybulb_c_tttttt"].shape[1])
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
    vlat.standard_name = "latitude"
    vlon.units = "degrees_east"
    vlon.standard_name = "longitude"

    vtime = nco.createVariable("time", "f8", ("time",))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    vtime[:] = [(valid - epoch).total_seconds() / 60.0]
    vtime.units = "minutes since 1970-01-01 00:00:00"
    vtime.calendar = "gregorian"
    vtime.standard_name = "time"

    written = []
    for name, data in fields.items():
        units, long_name = PARAM_META[name]
        vv = nco.createVariable(name, "f4", ("time", "lat", "lon"), fill_value=np.float32(-9999.0))
        vv.units = units
        vv.long_name = long_name
        vv.coordinates = "time lat lon"
        vv[0, :, :] = data
        written.append(name)

    nco.setncattr("valid", args.valid)
    nco.setncattr("source_wrfout", str(Path(args.wrfout).name))
    nco.setncattr("title", "InaNWP surface multi-param for PointStat (HARP ids)")
    nco.setncattr("Conventions", "CF-1.6")
    nco.setncattr("parameters", ",".join(written))
    nco.close()

    meta = {
        "wrote": str(out),
        "valid": args.valid,
        "parameters": written,
        "shape": list(fields["temp_drybulb_c_tttttt"].shape),
        "precip_hours": args.precip_hours,
    }
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
