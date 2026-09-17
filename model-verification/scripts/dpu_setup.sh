#!/usr/bin/env bash
# Setup Model Verification compute di DPU (tanpa Docker / litbangweb).
# Jalankan sebagai dpu (sudo bila perlu untuk apt).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="${DPU_APPS_DIR:-$HOME/apps/model-verification}"
PY="${METPLUS_PYTHON:-$HOME/miniforge3/envs/metplus/bin/python3}"

echo "==> Sync app -> $APP_DIR"
mkdir -p "$APP_DIR"
rsync -a --exclude '.git' --exclude '.venv' --exclude 'data/artifacts' \
  --exclude 'data/cache' --exclude '__pycache__' \
  "$ROOT/" "$APP_DIR/"

echo "==> Python deps (metplus env bila ada, else venv)"
if [[ -x "$PY" ]]; then
  "$PY" -m pip install -q -r "$APP_DIR/requirements.txt"
else
  python3 -m venv "$APP_DIR/.venv"
  # shellcheck disable=SC1091
  source "$APP_DIR/.venv/bin/activate"
  pip install -q -U pip
  pip install -q -r "$APP_DIR/requirements.txt"
  PY="$APP_DIR/.venv/bin/python"
fi

mkdir -p "$HOME/data/model-verification"/{artifacts,obs,metplus,nc}
echo "==> Data dirs: $HOME/data/model-verification"
echo "OK. Gunakan: $PY $APP_DIR/scripts/dpu_run_metplus_daily.sh"
echo "HARP: $PY -m scripts.harp_compute (lihat AGENT_BRIEF / scripts)"
