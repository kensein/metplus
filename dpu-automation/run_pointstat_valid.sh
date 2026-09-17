#!/usr/bin/env bash
# METplus PointStat: InaNWP surface vs BMKG Soft/Sinoptik (multi-param = HARP Soft set).
# Params: temp, dewpoint, RH, QFF, QFE, wind speed/dir, rainfall_last (3h).
set -euo pipefail
VALID="${1:?usage: run_pointstat_valid.sh YYYYMMDDHH [wrfout] [lead] [init]}"
ROOT="${HOME}/apps/verifikasi-inanwp"
# shellcheck disable=SC1091
source "$HOME/apps/activate_metplus.sh"
# shellcheck disable=SC1091
[[ -f "$ROOT/webpsi.env" ]] && source "$ROOT/webpsi.env"
PYTHON="${METPLUS_PYTHON:-$HOME/miniforge3/envs/metplus/bin/python3}"

WRFOUT="${2:-}"
LEAD_HOURS="${3:-}"
INIT="${4:-}"
INANWP_DIR="${INANWP_DIR:-/home/klimat/inanwp}"
DATA="$HOME/data"
METPLUS="$DATA/metplus"
STATIONS="${STATIONS_JSON:-$ROOT/resources/stations_bmkg.json}"
SOFT_DIR="${SOFT_OBS_DIR:-$DATA/obs_export}"
OUTDIR="$METPLUS/pointstat/$VALID"
mkdir -p "$OUTDIR" "$DATA/wrfout" "$DATA/tmp" "$SOFT_DIR"

if [[ -z "$WRFOUT" ]]; then
  WRFOUT=$(ls -t "$INANWP_DIR"/wrfout_d01_* 2>/dev/null | head -1 || true)
fi
[[ -n "$WRFOUT" && -f "$WRFOUT" ]] || { echo "wrfout not found"; exit 1; }
[[ -f "$STATIONS" ]] || { echo "stations json missing: $STATIONS"; exit 1; }

mapfile -t SOFT_JSONS < <(ls -1 "$SOFT_DIR"/sinoptik_*.json 2>/dev/null || true)
if [[ ${#SOFT_JSONS[@]} -eq 0 ]]; then
  echo "ERROR: no Soft/Sinoptik JSON in $SOFT_DIR (sync dari HARP obs_export)"
  echo "  expected: sinoptik_YYYYMMDD_YYYYMMDD_*.json"
  exit 1
fi

FCST="$DATA/wrfout/inanwp_surface_${VALID}.nc"
ASCII="$OUTDIR/stations_soft_${VALID}.ascii"
OBS_PT="$OUTDIR/stations_soft_${VALID}.nc"
CFG="$OUTDIR/PointStatConfig_oper"

"$PYTHON" "$ROOT/prepare_point_fcst_surface.py" \
  --wrfout "$WRFOUT" --valid "$VALID" --out "$FCST"

"$PYTHON" "$ROOT/prepare_point_obs_soft.py" \
  --soft-json "${SOFT_JSONS[@]}" \
  --stations "$STATIONS" \
  --valid "$VALID" \
  --out-ascii "$ASCII"

# ASCII → NetCDF point obs (MET 11-column met_point)
ascii2nc "$ASCII" "$OBS_PT" -format met_point -v 1 | tee "$METPLUS/pointstat_ascii2nc_${VALID}.log"

# Multi-field PointStat — names = HARP Soft param ids
cat > "$CFG" << 'CFG'
model = "INANWP";
obtype = "BMKG_SOFT";
desc = "POINT_SOFT_MULTI";
fcst = {
  file_type = NETCDF_NCCF;
  field = [
    { name = "temp_drybulb_c_tttttt"; level = "(0,*,*)"; },
    { name = "temp_dewpoint_c_tdtdtd"; level = "(0,*,*)"; },
    { name = "relative_humidity_pc"; level = "(0,*,*)"; },
    { name = "pressure_qff_mb_derived"; level = "(0,*,*)"; },
    { name = "pressure_qfe_mb_derived"; level = "(0,*,*)"; },
    { name = "wind_speed_ff"; level = "(0,*,*)"; },
    { name = "wind_dir_deg_dd"; level = "(0,*,*)"; },
    { name = "rainfall_last_mm"; level = "(0,*,*)"; cat_thresh = [ >0.1, >1.0, >5.0 ]; }
  ];
};
obs = {
  field = [
    { name = "temp_drybulb_c_tttttt"; level = "Z0"; },
    { name = "temp_dewpoint_c_tdtdtd"; level = "Z0"; },
    { name = "relative_humidity_pc"; level = "Z0"; },
    { name = "pressure_qff_mb_derived"; level = "Z0"; },
    { name = "pressure_qfe_mb_derived"; level = "Z0"; },
    { name = "wind_speed_ff"; level = "Z0"; },
    { name = "wind_dir_deg_dd"; level = "Z0"; },
    { name = "rainfall_last_mm"; level = "Z0"; cat_thresh = [ >0.1, >1.0, >5.0 ]; }
  ];
};
message_type = [ "ADPSFC" ];
mask = { grid = [ "FULL" ]; poly = []; sid = []; };
output_flag = { fho = NONE; ctc = STAT; cts = STAT; cnt = STAT; mpr = STAT; };
output_prefix = "INANWP_vs_BMKG_SOFT_POINT";
tmp_dir = "TMPDIR_PLACEHOLDER";
CFG
# inject tmp_dir (heredoc quoted above)
sed -i "s|TMPDIR_PLACEHOLDER|$DATA/tmp|g" "$CFG"

rm -rf "$OUTDIR"/point_stat_* "$OUTDIR"/*.stat
point_stat "$FCST" "$OBS_PT" "$CFG" -outdir "$OUTDIR" -v 2 | tee "$METPLUS/pointstat_${VALID}.log"

STAT=$(ls "$OUTDIR"/*.stat 2>/dev/null | head -1 || true)
if [[ -z "$STAT" ]]; then
  echo "PointStat produced no .stat for $VALID"
  exit 1
fi
cp -f "$STAT" "${STAT}.txt"

N_SOFT=$(wc -l < "$ASCII" | tr -d ' ')
"$PYTHON" - << PY
import json
from pathlib import Path
from datetime import datetime, timezone
meta = {
  "generated_at": datetime.now(timezone.utc).isoformat(),
  "method": "metplus_point",
  "model": "INANWP",
  "observation": "BMKG_SOFT",
  "multi_param": True,
  "parameters": [
    "temp_drybulb_c_tttttt",
    "temp_dewpoint_c_tdtdtd",
    "relative_humidity_pc",
    "pressure_qff_mb_derived",
    "pressure_qfe_mb_derived",
    "wind_speed_ff",
    "wind_dir_deg_dd",
    "rainfall_last_mm",
  ],
  "obs_field": "multi",
  "valid_yyyymmddhh": "$VALID",
  "accum_hours": 3,
  "precip_source": "RAINNC+RAINC+RAINSH",
  "stations_file": "$STATIONS",
  "n_obs_lines": int("$N_SOFT"),
  "n_stations_catalog": $(python3 -c "import json;print(len(json.load(open('$STATIONS'))))"),
  "soft_dir": "$SOFT_DIR",
  "fcst_file": "$FCST",
  "stat_file": "$STAT",
  "status": "SUCCESS",
  "source_wrfout": "$(basename "$WRFOUT")",
}
lead = "${LEAD_HOURS}"
init = "${INIT}"
if lead:
  meta["lead_hours"] = int(lead)
if init:
  meta["init"] = init
Path("$OUTDIR/run_meta.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta, indent=2))
PY

echo "POINTSTAT DONE $VALID lead=${LEAD_HOURS:-NA} obs=BMKG_SOFT multi-param n_lines=$N_SOFT"
