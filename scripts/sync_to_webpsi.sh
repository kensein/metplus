#!/usr/bin/env bash
# Sync output METplus dari litbangweb ke server webpsi
# Edit variabel di bawah sebelum menjalankan
set -euo pipefail

# === KONFIGURASI — SESUAIKAN ===
LITBANGWEB_HOST="${LITBANGWEB_HOST:-litbangweb.bmkg.go.id}"
LITBANGWEB_USER="${LITBANGWEB_USER:-your_user}"
SOURCE_DIR="/mnt/wdd1/www/htdocs/wrf/metplus/dashboard"

WEBPSI_HOST="${WEBPSI_HOST:-webpsi.bmkg.go.id}"
WEBPSI_USER="${WEBPSI_USER:-your_user}"
TARGET_DIR="/var/www/verifikasi-inanwp/data/metplus"
# ================================

echo "=== Sync METplus dashboard data ==="
echo "From: ${LITBANGWEB_USER}@${LITBANGWEB_HOST}:${SOURCE_DIR}/"
echo "To:   ${WEBPSI_USER}@${WEBPSI_HOST}:${TARGET_DIR}/"

# Jalankan dari litbangweb (push) atau webpsi (pull)
MODE="${1:-push}"

if [ "$MODE" = "push" ]; then
    rsync -avz --delete \
        "${SOURCE_DIR}/" \
        "${WEBPSI_USER}@${WEBPSI_HOST}:${TARGET_DIR}/"
elif [ "$MODE" = "pull" ]; then
    rsync -avz --delete \
        "${LITBANGWEB_USER}@${LITBANGWEB_HOST}:${SOURCE_DIR}/" \
        "${TARGET_DIR}/"
else
    echo "Usage: $0 [push|pull]"
    exit 1
fi

echo "=== Sync selesai ==="
echo "Verifikasi di webpsi:"
echo "  ls -lh ${TARGET_DIR}/"
echo "  cat ${TARGET_DIR}/manifest.json"
