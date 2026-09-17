#!/usr/bin/env bash
# Otomasi harian DPU: verifikasi 3-jam InaNWP (RAINNC+RAINC+RAINSH) sampai H+72, lalu PUSH ke webpsi.
set -euo pipefail
ROOT="${HOME}/apps/verifikasi-inanwp"
LOG_DIR="${HOME}/data/metplus/logs"
mkdir -p "$LOG_DIR" "$ROOT"
LOG="$LOG_DIR/daily_$(date -u +%Y%m%d).log"
exec >>"$LOG" 2>&1
echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) START ===="

# shellcheck disable=SC1091
source "$HOME/apps/activate_metplus.sh"
# shellcheck disable=SC1091
source "$ROOT/webpsi.env"
PYTHON="${METPLUS_PYTHON:-$HOME/miniforge3/envs/metplus/bin/python3}"

INANWP_DIR="${INANWP_DIR:-/home/klimat/inanwp}"
MAX_LEAD="${MAX_LEAD_HOURS:-72}"
STEP="${LEAD_STEP_HOURS:-3}"
WRFOUT=$(ls -t "$INANWP_DIR"/wrfout_d01_* 2>/dev/null | head -1 || true)
if [[ -z "$WRFOUT" ]]; then
  echo "No wrfout in $INANWP_DIR"
  exit 0
fi
echo "Using wrfout: $WRFOUT"

# Init + daftar valid H+3..H+72 dari XTIME/Times
mapfile -t PLAN < <("$PYTHON" - << PY
from netCDF4 import Dataset
from datetime import datetime, timedelta, timezone
import numpy as np
ds = Dataset("$WRFOUT")
if "Times" in ds.variables:
    times = []
    for row in ds.variables["Times"][:]:
        s = row.tobytes().decode("ascii", "ignore").strip().replace("_", " ")
        times.append(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc))
else:
    start_raw = getattr(ds, "START_DATE", None) or getattr(ds, "SIMULATION_START_DATE", None)
    start = datetime.strptime(str(start_raw), "%Y-%m-%d_%H:%M:%S").replace(tzinfo=timezone.utc)
    xt = np.array(ds.variables["XTIME"][:], dtype=float)
    times = [start + timedelta(minutes=float(m)) for m in xt]
init = times[0]
print(init.strftime("%Y%m%d%H"))  # line0 = INIT
tset = set(times)
for lead in range($STEP, $MAX_LEAD + 1, $STEP):
    end = init + timedelta(hours=lead)
    start = end - timedelta(hours=$STEP)
    if end in tset and start in tset:
        print(f"{lead},{end.strftime('%Y%m%d%H')}")
PY
)

INIT="${PLAN[0]}"
echo "INIT=$INIT max_lead=$MAX_LEAD step=$STEP"

PROCESSED=0
FAILED=0
for row in "${PLAN[@]:1}"; do
  LEAD="${row%%,*}"
  VALID="${row##*,}"
  STAT_DIR="$HOME/data/metplus/gridstat/$VALID"
  if [[ -d "$STAT_DIR" ]] && ls "$STAT_DIR"/*.stat >/dev/null 2>&1 && [[ -f "$STAT_DIR/run_meta.json" ]]; then
    # re-run if precip_source bukan total
    if grep -q 'RAINNC+RAINC+RAINSH' "$STAT_DIR/run_meta.json" 2>/dev/null; then
      echo "skip existing H+${LEAD} valid=$VALID"
      continue
    fi
    echo "reprocess (update precip source) H+${LEAD} valid=$VALID"
  fi
  echo "run H+${LEAD} valid=$VALID"
  if bash "$ROOT/run_one_valid.sh" "$VALID" "$WRFOUT" "$LEAD" "$INIT"; then
    PROCESSED=$((PROCESSED + 1))
  else
    echo "FAILED H+${LEAD} valid=$VALID"
    FAILED=$((FAILED + 1))
  fi
done

"$PYTHON" "$ROOT/export_series.py" --metplus-dir "$HOME/data/metplus" --init "$INIT" --max-lead "$MAX_LEAD" --step "$STEP"
bash "$ROOT/push_to_webpsi.sh"
echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) DONE processed=$PROCESSED failed=$FAILED init=$INIT ===="
