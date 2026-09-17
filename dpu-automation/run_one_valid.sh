#!/usr/bin/env bash
# Jalankan regrid + GridStat untuk satu valid YYYYMMDDHH (akumulasi 3 jam).
# Opsional: LEAD_HOURS dan INIT untuk meta seri H+3..H+72.
set -euo pipefail
VALID="${1:?usage: run_one_valid.sh YYYYMMDDHH [wrfout] [lead_hours] [init_YYYYMMDDHH]}"
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

"$PYTHON" "$ROOT/prepare_precip3h.py" --wrfout "$WRFOUT" --valid "$VALID" --out "$FCST"
bash "$ROOT/fetch_gsmap.sh" "$VALID" "$DATA/gsmap/raw"
"$PYTHON" "$ROOT/prepare_gsmap_3h.py" --raw-dir "$DATA/gsmap/raw" --valid "$VALID" --out "$OBS"

# MET to_grid via explicit latlon string (plain CF NC is not auto-opened as grid)
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

regrid_data_plane "$OBS" "$TO_GRID" "$OBS_RG" \
  -field 'name="precip"; level="(0,*,*)"; file_type=NETCDF_NCCF;' \
  -method BUDGET -width 2 \
  -name precip \
  -v 1 | tee "$METPLUS/regrid_${VALID}.log"

cat > "$CFG" << CFG
model = "INANWP";
obtype = "GSMAP";
desc = "OPER_3H";
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
output_flag = { fho = NONE; ctc = STAT; cts = STAT; cnt = STAT; sl1l2 = STAT; };
nc_pairs_flag = { latlon = TRUE; raw = TRUE; diff = TRUE; };
output_prefix = "INANWP_vs_GSMAP";
tmp_dir = "$DATA/tmp";
CFG

# Bersihkan output lama valid ini supaya .stat/.txt tidak campur
rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"

grid_stat "$FCST" "$OBS_RG" "$CFG" -outdir "$OUTDIR" -v 2 | tee "$METPLUS/gridstat_${VALID}.log"

STAT=$(ls "$OUTDIR"/*.stat | head -1)
PAIRS=$(ls "$OUTDIR"/*_pairs.nc | head -1)

# Salin output MET ke .txt (diminta untuk dashboard)
cp -f "$STAT" "${STAT}.txt"
# Ringkasan skor manusiawi
"$PYTHON" - << PY
from pathlib import Path
import math
stat = Path("$STAT")
lines = stat.read_text().splitlines()
out = []
out.append("# InaNWP vs GSMAP — skor GridStat")
out.append(f"# valid=${VALID} precip=RAINNC+RAINC+RAINSH accum=3h")
out.append(f"# source_stat={stat.name}")
out.append("")
for line in lines:
    parts = line.split()
    if len(parts) < 24:
        continue
    for t in ("CNT", "CTS", "CTC"):
        if t in parts:
            i = parts.index(t)
            thresh = parts[i-4]
            body = parts[i+1:]
            if t == "CNT" and body:
                mse = float(body[50]) if body[50] != "NA" else None
                rmse = math.sqrt(mse) if mse is not None and mse >= 0 else None
                out.append(f"CNT thresh={thresh} TOTAL={body[0]} FBAR={body[1]} OBAR={body[11]} ME={body[31]} MAE={body[44]} RMSE={rmse}")
            if t == "CTS" and len(body) > 52:
                out.append(
                    f"CTS thresh={thresh} ACC={body[11]} FBIAS={body[16]} POD={body[19]} "
                    f"FAR={body[34]} CSI={body[39]} ETS={body[44]} HSS={body[52]}"
                )
            if t == "CTC" and len(body) >= 5:
                out.append(f"CTC thresh={thresh} HIT={body[1]} FA={body[2]} MISS={body[3]} CN={body[4]}")
            break
Path("$OUTDIR/scores_${VALID}.txt").write_text("\n".join(out) + "\n")
print("wrote scores txt")
PY

PAIRS_COUNT=$("$PYTHON" - << PY
from netCDF4 import Dataset
import numpy as np
ds=Dataset("$PAIRS")
name=next(n for n in ds.variables if n.startswith("FCST_"))
a=np.array(ds.variables[name][:])
print(int(np.isfinite(a).sum()))
PY
)

"$PYTHON" - << PY
import json
from pathlib import Path
from datetime import datetime, timezone
lead = "${LEAD_HOURS}"
init = "${INIT}"
meta = {
  "generated_at": datetime.now(timezone.utc).isoformat(),
  "model": "INANWP",
  "observation": "GSMAP NRT",
  "valid": "${VALID:0:8}_${VALID:8:2}Z",
  "valid_yyyymmddhh": "${VALID}",
  "accum_hours": 3,
  "precip_source": "RAINNC+RAINC+RAINSH",
  "matched_pairs": $PAIRS_COUNT,
  "note": "auto pipeline DPU",
  "stat_file": "$STAT",
  "txt_file": "${STAT}.txt",
  "scores_txt": "$OUTDIR/scores_${VALID}.txt",
  "status": "SUCCESS",
  "source_wrfout": "$(basename "$WRFOUT")",
}
if lead:
  meta["lead_hours"] = int(lead)
if init:
  meta["init"] = init
Path("$OUTDIR/run_meta.json").write_text(json.dumps(meta, indent=2))
Path("$METPLUS/dashboard/summary.json").write_text(json.dumps(meta, indent=2))
Path("$METPLUS/dashboard/summary_${VALID}.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta, indent=2))
PY

"$PYTHON" "$ROOT/render_pairs_maps.py" --nc "$PAIRS" --out-dir "$METPLUS/maps/$VALID" --valid "${VALID:0:8}_${VALID:8:2}Z"
echo "DONE $VALID lead=${LEAD_HOURS:-NA}"
