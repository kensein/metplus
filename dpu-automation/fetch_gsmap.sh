#!/usr/bin/env bash
# Unduh GSMAP jam-jaman untuk jendela 3 jam sebelum VALID (YYYYMMDDHH).
set -euo pipefail
VALID="${1:?usage: fetch_gsmap.sh YYYYMMDDHH}"
RAW_DIR="${2:-$HOME/data/gsmap/raw}"
FTP_BASE="${GSMAP_FTP:-ftp://202.90.199.64/himawari6/GSMaP/netcdf}"
mkdir -p "$RAW_DIR"
END=$(date -u -d "${VALID:0:4}-${VALID:4:2}-${VALID:6:2} ${VALID:8:2}:00:00" +%s)
for h in 3 2 1; do
  TS=$((END - h * 3600))
  STAMP=$(date -u -d "@$TS" +%Y%m%d%H)
  NAME="GSMaP_${STAMP}00.nc"
  DEST="${RAW_DIR}/${NAME}"
  if [[ -f "$DEST" ]]; then
    echo "exists $NAME"
    continue
  fi
  echo "fetch $NAME"
  curl -fsSL --connect-timeout 30 "${FTP_BASE}/${NAME}" -o "${DEST}.partial"
  mv "${DEST}.partial" "$DEST"
done
