#!/usr/bin/env python3
"""Render FCST / OBS / DIFF maps from GridStat *_pairs.nc into data/metplus/maps/<valid>/."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap, TwoSlopeNorm
from netCDF4 import Dataset


RAIN_LEVELS = [0, 0.1, 0.5, 1, 2, 5, 10, 20, 40, 80]
RAIN_COLORS = [
    "#c6dbef",
    "#9ecae1",
    "#6baed6",
    "#4292c6",
    "#2171b5",
    "#08519c",
    "#08306b",
    "#fcbba1",
    "#fb6a4a",
    "#a50f15",
]


def find_var(ds, prefixes):
    for name in ds.variables:
        for p in prefixes:
            if name.startswith(p):
                return name
    return None


def clean(arr: np.ndarray) -> np.ndarray:
    out = np.array(arr, dtype=float)
    out[out < -9000] = np.nan
    out[out > 1e20] = np.nan
    return out


def plot_rain(lon, lat, data, title, outfile, kind="rain"):
    LON, LAT = np.meshgrid(lon, lat)
    fig, ax = plt.subplots(figsize=(10.5, 5.8), dpi=120)
    if kind == "rain":
        cmap = ListedColormap(RAIN_COLORS)
        norm = BoundaryNorm(RAIN_LEVELS, cmap.N)
        pcm = ax.pcolormesh(LON, LAT, np.ma.masked_invalid(data), cmap=cmap, norm=norm, shading="auto")
        cbar = fig.colorbar(pcm, ax=ax, pad=0.02, ticks=RAIN_LEVELS)
        cbar.set_label("mm / 3 jam")
    else:
        vmax = float(np.nanpercentile(np.abs(data), 98))
        vmax = max(vmax, 1.0)
        norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
        pcm = ax.pcolormesh(LON, LAT, np.ma.masked_invalid(data), cmap="RdBu_r", norm=norm, shading="auto")
        cbar = fig.colorbar(pcm, ax=ax, pad=0.02)
        cbar.set_label("FCST − OBS (mm)")
    ax.set_title(title, fontsize=12, pad=8)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_xlim(float(lon.min()), float(lon.max()))
    ax.set_ylim(float(lat.min()), float(lat.max()))
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.25, linewidth=0.4)
    fig.tight_layout()
    fig.savefig(outfile, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_one(nc_path: Path, out_dir: Path, valid_label: str | None = None):
    ds = Dataset(nc_path)
    lat = np.array(ds.variables["lat"][:])
    lon = np.array(ds.variables["lon"][:])
    fcst_name = find_var(ds, ("FCST_",))
    obs_name = find_var(ds, ("OBS_",))
    diff_name = find_var(ds, ("DIFF_",))
    if not fcst_name or not obs_name or not diff_name:
        raise RuntimeError(f"Missing FCST/OBS/DIFF in {nc_path}")
    fcst = clean(ds.variables[fcst_name][:])
    obs = clean(ds.variables[obs_name][:])
    diff = clean(ds.variables[diff_name][:])
    valid = valid_label or out_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_rain(lon, lat, fcst, f"InaNWP FCST — precip 3h ({valid})", out_dir / "fcst.png")
    plot_rain(lon, lat, obs, f"GSMAP OBS — precip 3h ({valid})", out_dir / "obs.png")
    plot_rain(lon, lat, diff, f"DIFF (FCST − OBS) — precip 3h ({valid})", out_dir / "diff.png", kind="diff")
    meta = {
        "valid": valid,
        "source_nc": nc_path.name,
        "lat_range": [float(lat.min()), float(lat.max())],
        "lon_range": [float(lon.min()), float(lon.max())],
        "shape": list(fcst.shape),
        "fcst_mm": {
            "min": float(np.nanmin(fcst)),
            "max": float(np.nanmax(fcst)),
            "mean": float(np.nanmean(fcst)),
        },
        "obs_mm": {
            "min": float(np.nanmin(obs)),
            "max": float(np.nanmax(obs)),
            "mean": float(np.nanmean(obs)),
        },
        "diff_mm": {
            "min": float(np.nanmin(diff)),
            "max": float(np.nanmax(diff)),
            "mean": float(np.nanmean(diff)),
        },
        "maps": ["fcst.png", "obs.png", "diff.png"],
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="webpsi-app/data/metplus")
    ap.add_argument("--nc", help="Single pairs.nc path")
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    maps_root = data_dir / "maps"
    if args.nc:
        nc = Path(args.nc)
        valid = nc.parent.name
        meta = render_one(nc, maps_root / valid, valid)
        print(json.dumps(meta, indent=2))
        return 0
    gridstat = data_dir / "gridstat"
    if not gridstat.exists():
        print("No gridstat dir", file=sys.stderr)
        return 1
    n = 0
    for valid_dir in sorted(p for p in gridstat.iterdir() if p.is_dir()):
        for nc in sorted(valid_dir.glob("*_pairs.nc")):
            meta = render_one(nc, maps_root / valid_dir.name, valid_dir.name)
            print("OK", nc, "->", maps_root / valid_dir.name)
            n += 1
            print(json.dumps(meta, indent=2))
    if n == 0:
        print("No *_pairs.nc found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
