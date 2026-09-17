#!/usr/bin/env bash
# Hapus kalkulasi METplus lama (GridStat / PointStat / FSS / MODE) — mulai dari awal.
set -euo pipefail
METPLUS="${METPLUS_DATA_DIR:-$HOME/data/metplus}"
KEEP_GSMAP_RAW="${KEEP_GSMAP_RAW:-1}"

echo "[wipe] METPLUS=$METPLUS"
rm -rf \
  "$METPLUS/gridstat" \
  "$METPLUS/maps" \
  "$METPLUS/dashboard" \
  "$METPLUS/gsmap_regrid" \
  "$METPLUS/pointstat" \
  "$METPLUS/fss" \
  "$METPLUS/mode" \
  "$HOME/data/wrfout"/inanwp_precip3h_*.nc \
  "$HOME/data/wrfout"/inanwp_point_*.nc
rm -f "$METPLUS"/gridstat_*.log "$METPLUS"/regrid_*.log "$METPLUS"/pointstat_*.log \
  "$METPLUS"/fss_*.log "$METPLUS"/mode_*.log

if [[ "$KEEP_GSMAP_RAW" != "1" ]]; then
  rm -rf "$HOME/data/gsmap/raw" "$HOME/data/gsmap/prepared"
fi

mkdir -p \
  "$METPLUS"/{gridstat,maps,dashboard,gsmap_regrid,pointstat,fss,mode,logs} \
  "$HOME/data/wrfout" "$HOME/data/gsmap/raw" "$HOME/data/gsmap/prepared"

echo "[wipe] done"
du -sh "$METPLUS" "$HOME/data/gsmap" 2>/dev/null || true
