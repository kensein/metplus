#!/usr/bin/env bash
# Jalankan regrid + GridStat untuk satu valid YYYYMMDDHH, lalu tulis summary + peta.
set -euo pipefail
VALID="${1:?usage: run_one_valid.sh YYYYMMDDHH [wrfout]}"
ROOT="${HOME}/apps/verifikasi-inanwp"
# shellcheck disable=SC1091
source "$HOME/apps/activate_metplus.sh"
# shellcheck disable=SC1091
[[ -f "$ROOT/webpsi.env" ]] && source "$ROOT/webpsi.env"

WRFOUT="${2:-}"
INANWP_DIR="${INANWP_DIR:-/home/klimat/inanwp}"
DATA="$HOME/data"
METPLUS="$DATA/metplus"
mkdir -p "$DATA/wrfout" "$DATA/gsmap/raw" "$DATA/gsmap/prepared" \
  "$METPLUS/gridstat/$VALID" "$METPLUS/gsmap_regrid" "$METPLUS/maps/$VALID" "$METPLUS/dashboard" "$DATA/tmp"

if [[ -z "$WRFOUT" ]]; then
  WRFOUT=$(ls -t "$INANWP_DIR"/wrfout_d01_* 2>/dev/null | head -1 || true)
fi
[[ -n "$WRFOUT" && -f "$WRFOUT" ]] || { echo "wrfout not found in $INANWP_DIR"; exit 1; }

FCST="$DATA/wrfout/inanwp_precip3h_${VALID}.nc"
OBS="$DATA/gsmap/prepared/gsmap_precip3h_${VALID}.nc"
OBS_RG="$METPLUS/gsmap_regrid/gsmap_regrid_${VALID}.nc"
OUTDIR="$METPLUS/gridstat/$VALID"
CFG="$METPLUS/GridStatConfig_oper"

python3 "$ROOT/prepare_precip3h.py" --wrfout "$WRFOUT" --valid "$VALID" --out "$FCST"
bash "$ROOT/fetch_gsmap.sh" "$VALID" "$DATA/gsmap/raw"
python3 "$ROOT/prepare_gsmap_3h.py" --raw-dir "$DATA/gsmap/raw" --valid "$VALID" --out "$OBS"

# Regrid obs to forecast grid
regrid_data_plane "$OBS" "$FCST" "$OBS_RG" \
  -field 'name="precip"; level="(*,*)";' \
  -method BUDGET -width 2 \
  -name precip \
  -v 1 | tee "$METPLUS/regrid_${VALID}.log"

cat > "$CFG" << CFG
model = "INANWP";
obtype = "GSMAP";
desc = "OPER_3H";
fcst = {
  field = [ { name = "precip"; level = "(*,*)"; cat_thresh = [ >0.1, >1.0, >5.0, >10.0 ]; } ];
};
obs = {
  field = [ { name = "precip"; level = "(*,*)"; cat_thresh = [ >0.1, >1.0, >5.0, >10.0 ]; } ];
};
regrid = { to_grid = NONE; };
mask = { grid = [ "FULL" ]; };
output_flag = { fho = NONE; ctc = STAT; cts = STAT; cnt = STAT; sl1l2 = STAT; };
nc_pairs_flag = { latlon = TRUE; raw = TRUE; diff = TRUE; };
output_prefix = "INANWP_vs_GSMAP";
tmp_dir = "$DATA/tmp";
CFG

grid_stat "$FCST" "$OBS_RG" "$CFG" -outdir "$OUTDIR" -v 2 | tee "$METPLUS/gridstat_${VALID}.log"

STAT=$(ls "$OUTDIR"/*.stat | head -1)
PAIRS=$(ls "$OUTDIR"/*_pairs.nc | head -1)
PAIRS_COUNT=$(python3 - << PY
from netCDF4 import Dataset
import numpy as np
ds=Dataset("$PAIRS")
# any FCST var
name=next(n for n in ds.variables if n.startswith("FCST_"))
a=np.array(ds.variables[name][:])
print(int(np.isfinite(a).sum()))
PY
)

python3 - << PY
import json
from pathlib import Path
from datetime import datetime, timezone
summary = {
  "generated_at": datetime.now(timezone.utc).isoformat(),
  "model": "INANWP",
  "observation": "GSMAP NRT",
  "valid": "${VALID:0:8}_${VALID:8:2}Z",
  "accum_hours": 3,
  "matched_pairs": $PAIRS_COUNT,
  "note": "auto pipeline DPU",
  "stat_file": "$STAT",
  "status": "SUCCESS",
  "source_wrfout": "$(basename "$WRFOUT")",
}
Path("$METPLUS/dashboard/summary.json").write_text(json.dumps(summary, indent=2))
# also per-run summary
Path("$METPLUS/dashboard/summary_${VALID}.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
PY

python3 "$ROOT/render_pairs_maps.py" --nc "$PAIRS" --out-dir "$METPLUS/maps/$VALID" --valid "${VALID:0:8}_${VALID:8:2}Z"
echo "DONE $VALID"
