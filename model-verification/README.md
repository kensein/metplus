# Model Verification

Satu dashboard (pola UI **Monas**) untuk verifikasi multi-model NWP dengan pilihan metode:

| Metode | Domain | Engine |
|--------|--------|--------|
| **HARP** | Titik stasiun | Artefak f32 Monas / compute DPU |
| **METplus** | Spasial / grid | GridStat vs GSMAP (repo metplus `dpu-automation`) |

Produksi target: `https://psimkg.bmkg.go.id/model-verification/`

## Arsitektur (update 2026)

```
Obs BMKG Soft + NC per model NWP
        │
        ▼
   DPU (compute, internet OK)
   · HARP point (tanpa Docker)
   · METplus GridStat H+3…H+72
        │  rsync / push artifact
        ▼
   webpsi SERVE_READONLY
   UI: ranking · scores vs lead · peta stasiun · peta spasial
```

**Tidak memakai litbangweb / Docker** — kalkulasi di DPU.

## Fitur UI

- Pilih **metode** HARP | METplus
- Centang **model** (InaNWP, InaCAWO, GFS, IFS) — per input NWP
- Overview & **ranking**
- Scores vs lead time
- Peta stasiun (HARP) + **peta spasial** METplus (fcst/obs/diff)
- Detail stasiun (HARP)

## Deploy webpsi (ringkas)

```bash
sudo mkdir -p /var/www/model-verification
rsync -a model-verification/ /var/www/model-verification/
cd /var/www/model-verification
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # sesuaikan
# Symlink data yang sudah ada:
ln -sfn /var/www/monas/data/artifacts data/artifacts
ln -sfn /var/www/verifikasi-inanwp/data/metplus data/metplus
pm2 startOrReload ecosystem.config.cjs
```

Apache (sebelum catch-all):

```
ProxyPass        /model-verification/api http://127.0.0.1:8028/api
ProxyPassReverse /model-verification/api http://127.0.0.1:8028/api
ProxyPass        /model-verification     http://127.0.0.1:3028/model-verification
ProxyPassReverse /model-verification     http://127.0.0.1:3028/model-verification
```

## DPU

```bash
bash scripts/dpu_setup.sh
bash scripts/dpu_run_metplus_daily.sh   # pakai verifikasi-inanwp + mirror
```

## Repo terkait

- UI/HARP asal: https://github.com/kensein/monas
- METplus pipeline: `dpu-automation/` di repo ini (`kensein/metplus`)
