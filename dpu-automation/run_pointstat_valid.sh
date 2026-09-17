#!/usr/bin/env bash
# METplus PointStat: InaNWP grid vs BMKG Soft/Sinoptik di seluruh stasiun (sama obs HARP).
# Parameter: precip 3h model (RAINNC+RAINC+RAINSH) vs Soft rainfall_last_mm (dll).
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

FCST="$DATA/wrfout/inanwp_precip3h_${VALID}.nc"
ASCII="$OUTDIR/stations_soft_${VALID}.ascii"
OBS_PT="$OUTDIR/stations_soft_${VALID}.nc"
CFG="$OUTDIR/PointStatConfig_oper"

# Forecast precip 3h (reuse GridStat prep bila ada)
if [[ ! -f "$FCST" ]]; then
  "$PYTHON" "$ROOT/prepare_precip3h.py" --wrfout "$WRFOUT" --valid "$VALID" --out "$FCST"
fi

"$PYTHON" "$ROOT/prepare_point_obs_soft.py" \
  --soft-json "${SOFT_JSONS[@]}" \
  --stations "$STATIONS" \
  --valid "$VALID" \
  --out-ascii "$ASCII"

# ASCII → NetCDF point obs (MET 11-column met_point)
ascii2nc "$ASCII" "$OBS_PT" -format met_point -v 1 | tee "$METPLUS/pointstat_ascii2nc_${VALID}.log"

cat > "$CFG" << CFG
model = "INANWP";
obtype = "BMKG_SOFT";
desc = "POINT_SOFT_3H";
fcst = {
  file_type = NETCDF_NCCF;
  field = [ { name = "precip"; level = "(0,*,*)"; cat_thresh = [ >0.1, >1.0, >5.0 ]; } ];
};
obs = {
  field = [ { name = "precip"; level = "Z0"; cat_thresh = [ >0.1, >1.0, >5.0 ]; } ];
};
message_type = [ "ADPSFC" ];
mask = { grid = [ "FULL" ]; poly = []; sid = []; };
output_flag = { fho = NONE; ctc = STAT; cts = STAT; cnt = STAT; mpr = STAT; };
output_prefix = "INANWP_vs_BMKG_SOFT_POINT";
tmp_dir = "$DATA/tmp";
CFG

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
  "obs_field": "rainfall_last_mm",
  "valid_yyyymmddhh": "$VALID",
  "accum_hours": 3,
  "precip_source": "RAINNC+RAINC+RAINSH",
  "stations_file": "$STATIONS",
  "n_stations_obs": int("$N_SOFT"),
  "n_stations_catalog": $(python3 -c "import json;print(len(json.load(open('$STATIONS'))))"),
  "soft_dir": "$SOFT_DIR",
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

echo "POINTSTAT DONE $VALID lead=${LEAD_HOURS:-NA} obs=BMKG_SOFT n=$N_SOFT"
