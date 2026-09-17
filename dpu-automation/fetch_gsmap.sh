#!/usr/bin/env bash
# Unduh GSMAP jam-jaman untuk jendela 3 jam sebelum VALID (YYYYMMDDHH).
# Path FTP: himawari6/GSMaP/netcdf/YYYY/MM/DD/GSMaP_YYYYMMDDHH00.nc
set -euo pipefail
VALID="${1:?usage: fetch_gsmap.sh YYYYMMDDHH}"
RAW_DIR="${2:-$HOME/data/gsmap/raw}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
if [[ -f "$ROOT/webpsi.env" ]]; then
  source "$ROOT/webpsi.env"
fi

FTP_HOST="${GSMAP_FTP_HOST:-202.90.199.64}"
FTP_ROOT="${GSMAP_FTP_PATH:-himawari6/GSMaP/netcdf}"
FTP_USER="${GSMAP_FTP_USER:-}"
FTP_PASS="${GSMAP_FTP_PASSWORD:-}"

mkdir -p "$RAW_DIR"
END=$(date -u -d "${VALID:0:4}-${VALID:4:2}-${VALID:6:2} ${VALID:8:2}:00:00" +%s)
for h in 3 2 1; do
  TS=$((END - h * 3600))
  STAMP=$(date -u -d "@$TS" +%Y%m%d%H)
  Y=${STAMP:0:4}; M=${STAMP:4:2}; D=${STAMP:6:2}
  NAME="GSMaP_${STAMP}00.nc"
  DEST="${RAW_DIR}/${NAME}"
  if [[ -f "$DEST" ]]; then
    echo "exists $NAME"
    continue
  fi
  REMOTE_PATH="${FTP_ROOT}/${Y}/${M}/${D}/${NAME}"
  echo "fetch $NAME <- ${REMOTE_PATH}"
  if [[ -z "$FTP_USER" || -z "$FTP_PASS" ]]; then
    echo "ERROR: set GSMAP_FTP_USER and GSMAP_FTP_PASSWORD in webpsi.env" >&2
    exit 1
  fi
  curl -fsSL --connect-timeout 60 --max-time 300 \
    --user "${FTP_USER}:${FTP_PASS}" \
    "ftp://${FTP_HOST}/${REMOTE_PATH}" \
    -o "${DEST}.partial"
  mv "${DEST}.partial" "$DEST"
done
