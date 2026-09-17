#!/usr/bin/env python3
"""Inspect NetCDF files untuk menentukan variable METplus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import xarray as xr
except ImportError:
    print("Install xarray: pip install xarray netcdf4")
    sys.exit(1)


def inspect_file(path: Path) -> None:
    print(f"\n{'=' * 60}")
    print(f"File: {path}")
    print("=" * 60)

    ds = xr.open_dataset(path)
    print(f"\nDimensions: {dict(ds.dims)}")
    print(f"\nCoordinates: {list(ds.coords)}")
    print(f"\nData variables:")
    for var in ds.data_vars:
        da = ds[var]
        attrs = {k: da.attrs.get(k) for k in ("units", "long_name", "standard_name") if k in da.attrs}
        print(f"  {var}: shape={da.shape}, attrs={attrs}")

    if "time" in ds.coords or "Time" in ds.coords:
        tname = "time" if "time" in ds.coords else "Time"
        print(f"\nTime range: {ds[tname].values[0]} -> {ds[tname].values[-1]}")

    global_attrs = {k: ds.attrs[k] for k in ("Conventions", "title", "source") if k in ds.attrs}
    if global_attrs:
        print(f"\nGlobal attrs: {global_attrs}")

    ds.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect NetCDF for METplus config")
    parser.add_argument("files", nargs="+", help="Path to NetCDF file(s)")
    args = parser.parse_args()

    for f in args.files:
        inspect_file(Path(f))


if __name__ == "__main__":
    main()
