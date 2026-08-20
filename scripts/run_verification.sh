#!/usr/bin/env bash
# Jalankan verifikasi METplus INanWP vs GSMAP di server litbangweb
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

METPLUS_BASE="${METPLUS_BASE:-/opt/METplus}"
CONFIG_USE_CASE="${PROJECT_DIR}/config/inanwp_gsmap.conf"
CONFIG_SYSTEM="${PROJECT_DIR}/config/inanwp_system.conf"

# Override dengan argumen opsional
VALID_BEG="${1:-2026072700}"
VALID_END="${2:-2026073023}"

echo "=== Verifikasi INanWP vs GSMAP ==="
echo "Valid time: ${VALID_BEG} - ${VALID_END}"
echo "METplus base: ${METPLUS_BASE}"

# Buat direktori output
OUTPUT_BASE="/mnt/wdd1/www/htdocs/wrf/metplus"
mkdir -p "${OUTPUT_BASE}/gridstat" "${OUTPUT_BASE}/gsmap_regrid" "${OUTPUT_BASE}/dashboard"

# Export override waktu valid
export METPLUS_VALID_BEG="${VALID_BEG}"
export METPLUS_VALID_END="${VALID_END}"

# Jalankan METplus
python3 "${METPLUS_BASE}/METplus/scripts/run_metplus.py" \
    "${CONFIG_USE_CASE}" \
    "${CONFIG_SYSTEM}" \
    2>&1 | tee "${OUTPUT_BASE}/logs/run_$(date +%Y%m%d_%H%M%S).log"

# Export data untuk dashboard
python3 "${SCRIPT_DIR}/export_dashboard_data.py" \
    --input-dir "${OUTPUT_BASE}/gridstat" \
    --output-dir "${OUTPUT_BASE}/dashboard"

echo "=== Selesai. Output dashboard: ${OUTPUT_BASE}/dashboard ==="
