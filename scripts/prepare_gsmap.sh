#!/usr/bin/env bash
# Siapkan data GSMAP NRT untuk METplus (rename/symlink ke template)
set -euo pipefail

OBS_DIR="${1:-/mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730}"
OUTPUT_DIR="${2:-${OBS_DIR}/prepared}"

mkdir -p "${OUTPUT_DIR}"

echo "Menyiapkan GSMAP dari: ${OBS_DIR}"
echo "Output: ${OUTPUT_DIR}"

# GSMAP NRT biasanya berformat berbeda per sumber download
# Script ini menormalisasi nama file ke gsmap_YYYYMMDDHH.nc

for f in "${OBS_DIR}"/*.nc "${OBS_DIR}"/*/*.nc; do
    [ -f "$f" ] || continue

    # Ekstrak timestamp dari nama file (sesuaikan pattern jika perlu)
    basename_f="$(basename "$f")"

    # Pattern umum: YYYYMMDDHH atau YYYYMMDD_HH
    if [[ "$basename_f" =~ ([0-9]{10}) ]]; then
        ts="${BASH_REMATCH[1]}"
    elif [[ "$basename_f" =~ ([0-9]{8})[_-]?([0-9]{2}) ]]; then
        ts="${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
    else
        echo "  Skip (tidak dikenali): ${basename_f}"
        continue
    fi

    target="${OUTPUT_DIR}/gsmap_${ts}.nc"
    if [ ! -e "$target" ]; then
        ln -sf "$(realpath "$f")" "$target"
        echo "  Linked: gsmap_${ts}.nc"
    fi
done

echo "Selesai. ${OUTPUT_DIR}"
