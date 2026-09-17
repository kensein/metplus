#!/usr/bin/env bash
# Otomasi DPU: GridStat + PointStat + FSS/MODE InaNWP vs GSMAP H+3..H+72, lalu PUSH webpsi.
# Env:
#   WIPE_FIRST=1          hapus kalkulasi lama sebelum jalan
#   RUN_GRIDSTAT=1        (default) spasial grid
#   RUN_POINTSTAT=1       (default) verifikasi titik semua stasiun ID
#   RUN_FSS_MODE=1        (default) FSS neighborhood + MODE object-based
#   FORCE_RERUN=1         jangan skip valid yang sudah ada
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

WIPE_FIRST="${WIPE_FIRST:-0}"
RUN_GRIDSTAT="${RUN_GRIDSTAT:-1}"
RUN_POINTSTAT="${RUN_POINTSTAT:-1}"
RUN_FSS_MODE="${RUN_FSS_MODE:-1}"
FORCE_RERUN="${FORCE_RERUN:-0}"

if [[ "$WIPE_FIRST" == "1" ]]; then
  bash "$ROOT/wipe_metplus.sh"
fi

INANWP_DIR="${INANWP_DIR:-/home/klimat/inanwp}"
MAX_LEAD="${MAX_LEAD_HOURS:-72}"
STEP="${LEAD_STEP_HOURS:-3}"
WRFOUT=$(ls -t "$INANWP_DIR"/wrfout_d01_* 2>/dev/null | head -1 || true)
if [[ -z "$WRFOUT" ]]; then
  echo "No wrfout in $INANWP_DIR"
  exit 0
fi
echo "Using wrfout: $WRFOUT wipe=$WIPE_FIRST force=$FORCE_RERUN grid=$RUN_GRIDSTAT point=$RUN_POINTSTAT fss_mode=$RUN_FSS_MODE"

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
echo "INIT=$INIT max_lead=$MAX_LEAD step=$STEP n_leads=$(( ${#PLAN[@]} - 1 ))"

PROCESSED=0
FAILED=0
for row in "${PLAN[@]:1}"; do
  LEAD="${row%%,*}"
  VALID="${row##*,}"
  echo "---- H+${LEAD} valid=$VALID ----"

  if [[ "$RUN_GRIDSTAT" == "1" ]]; then
    STAT_DIR="$HOME/data/metplus/gridstat/$VALID"
    if [[ "$FORCE_RERUN" != "1" && -d "$STAT_DIR" ]] && ls "$STAT_DIR"/*.stat >/dev/null 2>&1 && [[ -f "$STAT_DIR/run_meta.json" ]]; then
      if grep -q 'RAINNC+RAINC+RAINSH' "$STAT_DIR/run_meta.json" 2>/dev/null; then
        echo "skip gridstat existing H+${LEAD}"
      else
        bash "$ROOT/run_one_valid.sh" "$VALID" "$WRFOUT" "$LEAD" "$INIT" || { echo "FAILED gridstat"; FAILED=$((FAILED+1)); continue; }
        PROCESSED=$((PROCESSED + 1))
      fi
    else
      if bash "$ROOT/run_one_valid.sh" "$VALID" "$WRFOUT" "$LEAD" "$INIT"; then
        PROCESSED=$((PROCESSED + 1))
      else
        echo "FAILED gridstat H+${LEAD}"
        FAILED=$((FAILED + 1))
        continue
      fi
    fi
  fi

  if [[ "$RUN_POINTSTAT" == "1" ]]; then
    PT_DIR="$HOME/data/metplus/pointstat/$VALID"
    NEED_PT=1
    if [[ "$FORCE_RERUN" != "1" && -f "$PT_DIR/run_meta.json" ]] && ls "$PT_DIR"/*.stat >/dev/null 2>&1; then
      if grep -q '"multi_param": true' "$PT_DIR/run_meta.json" 2>/dev/null; then
        echo "skip pointstat existing multi-param H+${LEAD}"
        NEED_PT=0
      else
        echo "re-run pointstat (upgrade to multi-param) H+${LEAD}"
      fi
    fi
    if [[ "$NEED_PT" == "1" ]]; then
      bash "$ROOT/run_pointstat_valid.sh" "$VALID" "$WRFOUT" "$LEAD" "$INIT" || echo "WARN pointstat failed H+${LEAD}"
    fi
  fi

  if [[ "$RUN_FSS_MODE" == "1" ]]; then
    FSS_META="$HOME/data/metplus/fss/$VALID/run_meta.json"
    if [[ "$FORCE_RERUN" != "1" && -f "$FSS_META" ]]; then
      echo "skip fss/mode existing H+${LEAD}"
    else
      bash "$ROOT/run_fss_mode_valid.sh" "$VALID" "$LEAD" "$INIT" || echo "WARN fss/mode failed H+${LEAD}"
    fi
  fi
done

"$PYTHON" "$ROOT/export_series.py" --metplus-dir "$HOME/data/metplus" --init "$INIT" --max-lead "$MAX_LEAD" --step "$STEP"
# Mirror ke layout multi-model (Model Verification)
DST="${MODEL_VERIFY_METPLUS:-$HOME/data/model-verification/metplus}"
mkdir -p "$DST/models/InaNWP/dashboard" "$DST/dashboard" "$DST/maps"
rsync -a "$HOME/data/metplus/dashboard/" "$DST/models/InaNWP/dashboard/" 2>/dev/null || true
rsync -a "$HOME/data/metplus/dashboard/" "$DST/dashboard/" 2>/dev/null || true
rsync -a "$HOME/data/metplus/maps/" "$DST/models/InaNWP/maps/" 2>/dev/null || true
rsync -a "$HOME/data/metplus/maps/" "$DST/maps/" 2>/dev/null || true
for sub in pointstat fss mode; do
  mkdir -p "$DST/$sub" "$DST/models/InaNWP/$sub"
  rsync -a "$HOME/data/metplus/$sub/" "$DST/$sub/" 2>/dev/null || true
  rsync -a "$HOME/data/metplus/$sub/" "$DST/models/InaNWP/$sub/" 2>/dev/null || true
done

bash "$ROOT/push_to_webpsi.sh" || echo "WARN push_to_webpsi failed"
echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) DONE processed=$PROCESSED failed=$FAILED init=$INIT ===="
