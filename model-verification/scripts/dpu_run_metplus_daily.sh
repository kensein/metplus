#!/usr/bin/env bash
# METplus daily di DPU → tulis ke data/metplus lalu (opsional) push webpsi.
# Tanpa Docker. Memakai pipeline verifikasi-inanwp yang sudah ada.
set -euo pipefail
INANWP_VERIFY="${INANWP_VERIFY_DIR:-$HOME/apps/verifikasi-inanwp}"
if [[ -x "$INANWP_VERIFY/daily_verify_push.sh" ]]; then
  bash "$INANWP_VERIFY/daily_verify_push.sh"
else
  echo "Tidak menemukan $INANWP_VERIFY/daily_verify_push.sh"
  echo "Deploy dulu dpu-automation dari repo metplus ke $INANWP_VERIFY"
  exit 1
fi

# Mirror ke layout multi-model Model Verification
SRC="${METPLUS_DATA_DIR:-$HOME/data/metplus}"
DST="${MODEL_VERIFY_METPLUS:-$HOME/data/model-verification/metplus}"
mkdir -p "$DST/models/InaNWP"
rsync -a "$SRC/dashboard/" "$DST/models/InaNWP/dashboard/" 2>/dev/null || true
rsync -a "$SRC/maps/" "$DST/models/InaNWP/maps/" 2>/dev/null || true
# juga flat (default InaNWP)
mkdir -p "$DST/dashboard" "$DST/maps"
rsync -a "$SRC/dashboard/" "$DST/dashboard/"
rsync -a "$SRC/maps/" "$DST/maps/" 2>/dev/null || true
echo "METplus mirrored -> $DST"
