#!/usr/bin/env bash
# Push output METplus dari DPU ke webpsi (bukan pull).
set -euo pipefail

ROOT="${HOME}/apps/verifikasi-inanwp"
# shellcheck disable=SC1091
source "${ROOT}/webpsi.env"

SRC="${METPLUS_DATA_DIR:-$HOME/data/metplus}/"
DEST="${WEBPSI_USER}@${WEBPSI_HOST}:${WEBPSI_DATA_DIR}/"
SSH_OPTS=(-o StrictHostKeyChecking=no -o IdentitiesOnly=yes -p "${WEBPSI_PORT:-65000}")

if [[ -n "${WEBPSI_SSH_KEY:-}" && -f "${WEBPSI_SSH_KEY}" ]]; then
  SSH_OPTS+=(-i "${WEBPSI_SSH_KEY}")
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] PUSH ${SRC} -> ${DEST}"
rsync -avz --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  -e "ssh ${SSH_OPTS[*]}" \
  --exclude '*.log' \
  "${SRC}" "${DEST}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] PUSH OK"
