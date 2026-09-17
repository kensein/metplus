#!/usr/bin/env bash
# FSS (neighborhood / GridStat NBR*) + MODE object-based untuk satu valid.
# Input: fcst precip NC + obs regrid NC (dari run_one_valid / GridStat path).
set -euo pipefail
VALID="${1:?usage: run_fss_mode_valid.sh YYYYMMDDHH [lead] [init]}"
LEAD_HOURS="${2:-}"
INIT="${3:-}"
ROOT="${HOME}/apps/verifikasi-inanwp"
# shellcheck disable=SC1091
source "$HOME/apps/activate_metplus.sh"
PYTHON="${METPLUS_PYTHON:-$HOME/miniforge3/envs/metplus/bin/python3}"
DATA="$HOME/data"
METPLUS="$DATA/metplus"
FCST="$DATA/wrfout/inanwp_precip3h_${VALID}.nc"
OBS_RG="$METPLUS/gsmap_regrid/gsmap_regrid_${VALID}.nc"
FSS_DIR="$METPLUS/fss/$VALID"
MODE_DIR="$METPLUS/mode/$VALID"
mkdir -p "$FSS_DIR" "$MODE_DIR" "$DATA/tmp"

[[ -f "$FCST" ]] || { echo "missing fcst $FCST — run GridStat prepare first"; exit 1; }
[[ -f "$OBS_RG" ]] || { echo "missing regrid obs $OBS_RG — run GridStat first"; exit 1; }

# --- FSS via GridStat neighborhood ---
FSS_CFG="$FSS_DIR/GridStatConfig_fss"
cat > "$FSS_CFG" << CFG
model = "INANWP";
obtype = "GSMAP";
desc = "FSS_3H";
fcst = {
  file_type = NETCDF_NCCF;
  field = [ { name = "precip"; level = "(0,*,*)"; cat_thresh = [ >0.1, >1.0, >5.0, >10.0 ]; } ];
};
obs = {
  file_type = NETCDF_MET;
  field = [ { name = "precip"; level = "(*,*)"; cat_thresh = [ >0.1, >1.0, >5.0, >10.0 ]; } ];
};
regrid = { to_grid = NONE; };
mask = { grid = [ "FULL" ]; };
nbrhd = {
  width = [ 1, 3, 5, 7, 9, 11 ];
  shape = SQUARE;
  cov_thresh = [ >=0.5 ];
};
output_flag = {
  fho = NONE; ctc = NONE; cts = NONE; cnt = NONE; sl1l2 = NONE;
  nbrctc = STAT; nbrcts = STAT; nbrcnt = STAT;
};
nc_pairs_flag = { latlon = FALSE; raw = FALSE; diff = FALSE; };
output_prefix = "INANWP_vs_GSMAP_FSS";
tmp_dir = "$DATA/tmp";
CFG

rm -rf "$FSS_DIR"/grid_stat_* "$FSS_DIR"/*.stat
grid_stat "$FCST" "$OBS_RG" "$FSS_CFG" -outdir "$FSS_DIR" -v 2 | tee "$METPLUS/fss_${VALID}.log"
FSS_STAT=$(ls "$FSS_DIR"/*.stat 2>/dev/null | head -1 || true)
[[ -n "$FSS_STAT" ]] && cp -f "$FSS_STAT" "${FSS_STAT}.txt"

# --- MODE object-based (fcst converted to MET NetCDF plane) ---
MODE_CFG="$MODE_DIR/ModeConfig_oper"
FCST_MET="$METPLUS/gsmap_regrid/inanwp_precip_met_${VALID}.nc"
read -r TO_GRID < <("$PYTHON" - << PY
from netCDF4 import Dataset
import numpy as np
ds = Dataset("$FCST")
lat = np.array(ds.variables["lat"][:], dtype=float)
lon = np.array(ds.variables["lon"][:], dtype=float)
if lat.ndim == 2:
    lat = lat[:, 0]
    lon = lon[0, :]
print(
    f"latlon {len(lon)} {len(lat)} {float(lat[0])} {float(lon[0])} "
    f"{float(lat[1] - lat[0])} {float(lon[1] - lon[0])}"
)
ds.close()
PY
)
regrid_data_plane "$FCST" "$TO_GRID" "$FCST_MET" \
  -field 'name="precip"; level="(0,*,*)"; file_type=NETCDF_NCCF;' \
  -method NEAREST -width 1 -name precip -v 1 | tee "$METPLUS/mode_regrid_${VALID}.log"

cat > "$MODE_CFG" << CFG
model = "INANWP";
desc = "MODE_3H";
grid_res = 9;
fcst = {
  field = {
    name = "precip";
    level = "(*,*)";
  };
  censor_thresh = [ <0.1 ];
  censor_val = [ 0 ];
  conv_radius = 2;
  conv_thresh = >=1.0;
  merge_thresh = >=1.0;
  merge_flag = THRESH;
};
obs = {
  field = {
    name = "precip";
    level = "(*,*)";
  };
  censor_thresh = [ <0.1 ];
  censor_val = [ 0 ];
  conv_radius = 2;
  conv_thresh = >=1.0;
  merge_thresh = >=1.0;
  merge_flag = THRESH;
};
mask = {
  grid = "";
  grid_flag = NONE;
  poly = "";
  poly_flag = NONE;
};
match_flag = MERGE_BOTH;
max_centroid_dist = 800.0/grid_res;
total_interest_thresh = 0.7;
ps_plot_flag = TRUE;
ct_stats_flag = TRUE;
output_prefix = "INANWP_vs_GSMAP_MODE";
tmp_dir = "$DATA/tmp";
CFG

rm -rf "$MODE_DIR"/mode_* "$MODE_DIR"/*.ps "$MODE_DIR"/*.nc "$MODE_DIR"/*.txt 2>/dev/null || true
set +e
mode "$FCST_MET" "$OBS_RG" "$MODE_CFG" -outdir "$MODE_DIR" -v 2 | tee "$METPLUS/mode_${VALID}.log"
MODE_RC=$?
set -e

"$PYTHON" - << PY
import json
from pathlib import Path
from datetime import datetime, timezone
lead = "${LEAD_HOURS}"
init = "${INIT}"
base = {
  "generated_at": datetime.now(timezone.utc).isoformat(),
  "model": "INANWP",
  "observation": "GSMAP NRT",
  "valid_yyyymmddhh": "$VALID",
  "accum_hours": 3,
  "precip_source": "RAINNC+RAINC+RAINSH",
  "status": "SUCCESS",
}
if lead:
  base["lead_hours"] = int(lead)
if init:
  base["init"] = init

fss = dict(base)
fss["method"] = "metplus_fss"
fss["stat_file"] = "$FSS_STAT"
fss["nbrhd_widths"] = [1, 3, 5, 7, 9, 11]
Path("$FSS_DIR/run_meta.json").write_text(json.dumps(fss, indent=2))

mode_meta = dict(base)
mode_meta["method"] = "metplus_mode"
mode_meta["mode_rc"] = $MODE_RC
mode_meta["status"] = "SUCCESS" if $MODE_RC == 0 else "FAILED"
objs = sorted(Path("$MODE_DIR").glob("*_obj.*")) + sorted(Path("$MODE_DIR").glob("*.ps"))
mode_meta["n_obj_files"] = len(objs)
Path("$MODE_DIR/run_meta.json").write_text(json.dumps(mode_meta, indent=2))
print(json.dumps({"fss": fss, "mode": mode_meta}, indent=2))
PY

echo "FSS+MODE DONE $VALID rc_mode=$MODE_RC"
