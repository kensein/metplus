#!/usr/bin/env bash
# Otomasi harian di DPU: proses valid 3-jam terbaru dari wrfout InaNWP, lalu PUSH ke webpsi.
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

INANWP_DIR="${INANWP_DIR:-/home/klimat/inanwp}"
WRFOUT=$(ls -t "$INANWP_DIR"/wrfout_d01_* 2>/dev/null | head -1 || true)
if [[ -z "$WRFOUT" ]]; then
  echo "No wrfout in $INANWP_DIR"
  exit 0
fi
echo "Using wrfout: $WRFOUT"

# Tentukan kandidat valid 3-jam dari Times di wrfout (ambil hingga 8 slot terakhir yang berakhir %H in 00,03,06,09,12,15,18,21)
mapfile -t VALIDS < <(python3 - << PY
from netCDF4 import Dataset
from datetime import datetime
ds=Dataset("$WRFOUT")
raw=ds.variables["Times"][:]
times=[]
for row in raw:
    s=row.tobytes().decode("ascii","ignore").strip().replace("_"," ")
    times.append(datetime.strptime(s, "%Y-%m-%d %H:%M:%S"))
# 3h ends: keep hours divisible by 3, skip first time (need previous)
cands=[]
for t in times[1:]:
    if t.hour % 3 == 0:
        cands.append(t.strftime("%Y%m%d%H"))
# newest first, unique
seen=set(); out=[]
for v in reversed(cands):
    if v not in seen:
        seen.add(v); out.append(v)
print("\n".join(out[:8]))
PY
)

PROCESSED=0
for VALID in "${VALIDS[@]}"; do
  STAT_DIR="$HOME/data/metplus/gridstat/$VALID"
  if [[ -d "$STAT_DIR" ]] && ls "$STAT_DIR"/*.stat >/dev/null 2>&1; then
    echo "skip existing $VALID"
    continue
  fi
  echo "run $VALID"
  if bash "$ROOT/run_one_valid.sh" "$VALID" "$WRFOUT"; then
    PROCESSED=$((PROCESSED + 1))
  else
    echo "FAILED $VALID (continue)"
  fi
done

# Selalu push (termasuk jika hanya sync ulang)
bash "$ROOT/push_to_webpsi.sh"
echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) DONE processed=$PROCESSED ===="
