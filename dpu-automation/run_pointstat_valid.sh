#!/usr/bin/env bash
# METplus PointStat: InaNWP grid vs GSMaP-sampled points at ALL BMKG stations (Indonesia).
# Parameter: precip 3h (RAINNC+RAINC+RAINSH) — sama keluarga dengan HARP rainfall / METplus grid.
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
OUTDIR="$METPLUS/pointstat/$VALID"
mkdir -p "$OUTDIR" "$DATA/wrfout" "$DATA/gsmap/prepared" "$DATA/tmp"

if [[ -z "$WRFOUT" ]]; then
  WRFOUT=$(ls -t "$INANWP_DIR"/wrfout_d01_* 2>/dev/null | head -1 || true)
fi
[[ -n "$WRFOUT" && -f "$WRFOUT" ]] || { echo "wrfout not found"; exit 1; }
[[ -f "$STATIONS" ]] || { echo "stations json missing: $STATIONS"; exit 1; }

FCST="$DATA/wrfout/inanwp_precip3h_${VALID}.nc"
OBS_NC="$DATA/gsmap/prepared/gsmap_precip3h_${VALID}.nc"
ASCII="$OUTDIR/stations_gsmap_${VALID}.ascii"
OBS_PT="$OUTDIR/stations_gsmap_${VALID}.nc"
CFG="$OUTDIR/PointStatConfig_oper"

# Reuse prepared grids from GridStat path when present
if [[ ! -f "$FCST" ]]; then
  "$PYTHON" "$ROOT/prepare_precip3h.py" --wrfout "$WRFOUT" --valid "$VALID" --out "$FCST"
fi
if [[ ! -f "$OBS_NC" ]]; then
  bash "$ROOT/fetch_gsmap.sh" "$VALID" "$DATA/gsmap/raw"
  "$PYTHON" "$ROOT/prepare_gsmap_3h.py" --raw-dir "$DATA/gsmap/raw" --valid "$VALID" --out "$OBS_NC"
fi

"$PYTHON" "$ROOT/prepare_point_obs_gsmap.py" \
  --nc "$OBS_NC" --stations "$STATIONS" --valid "$VALID" --out-ascii "$ASCII"

# Convert ASCII → NetCDF point obs (MET 11-column met_point)
ascii2nc "$ASCII" "$OBS_PT" -format met_point -v 1 | tee "$METPLUS/pointstat_ascii2nc_${VALID}.log"

cat > "$CFG" << CFG
model = "INANWP";
obtype = "GSMAP_PT";
desc = "POINT_ID_3H";
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
output_prefix = "INANWP_vs_GSMAP_POINT";
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

"$PYTHON" - << PY
import json
from pathlib import Path
from datetime import datetime, timezone
meta = {
  "generated_at": datetime.now(timezone.utc).isoformat(),
  "method": "metplus_point",
  "model": "INANWP",
  "observation": "GSMAP@stations",
  "valid_yyyymmddhh": "$VALID",
  "accum_hours": 3,
  "precip_source": "RAINNC+RAINC+RAINSH",
  "stations_file": "$STATIONS",
  "n_stations_catalog": $(python3 -c "import json;print(len(json.load(open('$STATIONS'))))"),
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

echo "POINTSTAT DONE $VALID lead=${LEAD_HOURS:-NA}"
