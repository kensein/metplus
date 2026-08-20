# Dashboard Verifikasi INanWP vs GSMAP

Dashboard verifikasi model **INanWP** terhadap observasi satelit **GSMAP NRT** menggunakan framework [METplus](https://dtcenter.org/software-tools/metplus).

## Deploy Production

**Panduan lengkap step-by-step deploy di server litbangweb dan webpsi:**

→ **[docs/DEPLOY.md](docs/DEPLOY.md)**

Ringkasan:
- **litbangweb** — jalankan METplus, export output ke `/mnt/wdd1/www/htdocs/wrf/metplus/dashboard/`
- **webpsi** — sync data ke `/var/www/verifikasi-inanwp/data/metplus/`, deploy app di port 3013/8013 via PM2 + Apache

File referensi deploy: `deploy/ecosystem.config.cjs`, `deploy/apache-verifikasi-inanwp.conf`, `deploy/.env.example`

## Arsitektur

```
┌─────────────────────┐     METplus GridStat     ┌──────────────────────┐
│  Server litbangweb  │ ────────────────────────> │  Output METplus      │
│  (webpsi)           │                           │  /wrf/metplus/       │
│                     │                           │    ├── gridstat/     │
│  INanWP: wrfout/    │                           │    └── dashboard/    │
│  GSMAP: gsmap_nrt/  │                           └──────────┬───────────┘
└─────────────────────┘                                      │
                                                               │ HTTP / NFS
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │  Dashboard Server    │
                                                    │  (deploy terpisah)   │
                                                    │  Streamlit app       │
                                                    └──────────────────────┘
```

## Path Data

| Sumber | Path Server (litbangweb) | Path Lokal (testing) |
|--------|--------------------------|----------------------|
| INanWP | `/mnt/wdd1/www/htdocs/wrf/wrfout` | `C:\Users\husei\Downloads\2026070112-d01-asim.nc` |
| GSMAP | `/mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730` | `C:\Users\husei\Downloads\gsmap_nrt_20260727_20260730` |
| METplus Output | `/mnt/wdd1/www/htdocs/wrf/metplus` | — |
| Dashboard Data | `/mnt/wdd1/www/htdocs/wrf/metplus/dashboard` | `sample_data/dashboard/` |

## Setup di Server litbangweb (webpsi)

### 1. Inspect data NetCDF

Sebelum menjalankan METplus, periksa variable name di file NetCDF:

```bash
python3 scripts/inspect_nc.py \
    /mnt/wdd1/www/htdocs/wrf/wrfout/2026072712-d01-asim.nc \
    /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/*.nc
```

Sesuaikan `FCST_VAR1_NAME` dan `OBS_VAR1_NAME` di `config/inanwp_gsmap.conf`.

### 2. Siapkan data GSMAP

```bash
bash scripts/prepare_gsmap.sh \
    /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730
```

### 3. Jalankan verifikasi METplus

```bash
bash scripts/run_verification.sh 2026072700 2026073023
```

Atau manual:

```bash
python3 /opt/METplus/METplus/scripts/run_metplus.py \
    config/inanwp_gsmap.conf \
    config/inanwp_system.conf
```

### 4. Export data untuk dashboard

```bash
python3 scripts/export_dashboard_data.py \
    --input-dir /mnt/wdd1/www/htdocs/wrf/metplus/gridstat \
    --output-dir /mnt/wdd1/www/htdocs/wrf/metplus/dashboard
```

Pastikan folder `dashboard/` dapat diakses via HTTP dari server deploy.

## Deploy Dashboard (Server Terpisah)

### 1. Clone repo

```bash
git clone https://github.com/kensein/metplus.git
cd metplus/dashboard
```

### 2. Konfigurasi sumber data

```bash
cp ../config/dashboard.env.example .env
```

Edit `.env`:

```env
# Ambil data dari server webpsi via HTTP
DATA_SOURCE_URL=https://webpsi.bmkg.go.id/wrf/metplus/dashboard

MODEL_NAME=INanWP
OBS_NAME=GSMAP NRT
DOMAIN_NAME=Indonesia
REFRESH_INTERVAL=3600
```

### 3. Install dan jalankan

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

### Alternatif: mount NFS/SMB

Jika server dashboard terhubung via NFS:

```env
DATA_SOURCE_PATH=/mnt/webpsi/metplus/dashboard
```

## Testing Lokal (Windows)

### 1. Generate sample data

```bash
python scripts/generate_sample_data.py
```

### 2. Konfigurasi dashboard

Buat `dashboard/.env`:

```env
DATA_SOURCE_PATH=../sample_data/dashboard
```

### 3. Jalankan dashboard

```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

### Inspect file NetCDF lokal

```bash
python scripts/inspect_nc.py "C:\Users\husei\Downloads\2026070112-d01-asim.nc"
```

## Konfigurasi METplus

File konfigurasi utama:

- `config/inanwp_gsmap.conf` — use case verifikasi (RegridDataPlane + GridStat)
- `config/inanwp_system.conf` — path server litbangweb
- `config/inanwp_system_local.conf` — path lokal untuk testing

### Variable yang perlu disesuaikan

| Parameter | Default | Keterangan |
|-----------|---------|------------|
| `FCST_VAR1_NAME` | `RAINNC` | Variable presipitasi INanWP |
| `OBS_VAR1_NAME` | `hourlyPrecipRateGC` | Variable GSMAP gauge-calibrated |
| `FCST_GRID_STAT_INPUT_TEMPLATE` | `{valid?fmt=%Y%m%d%H}-d01-asim.nc` | Pattern nama file forecast |
| `VALID_BEG` / `VALID_END` | `2026072700` / `2026073023` | Periode verifikasi |

### Threshold presipitasi (mm)

`gt0.1, gt1, gt5, gt10, gt20, gt50`

### Statistik output

- **CNT** — Continuous (RMSE, ME, ACC)
- **CTS** — Categorical (ETS, Bias, CSI, FAR)
- **CTC** — Contingency table counts
- **NBR\*** — Neighborhood statistics

## Struktur Proyek

```
metplus/
├── config/
│   ├── inanwp_gsmap.conf          # METplus use case
│   ├── inanwp_system.conf         # Path server
│   ├── inanwp_system_local.conf   # Path lokal
│   └── dashboard.env.example      # Config dashboard
├── scripts/
│   ├── run_verification.sh        # Jalankan METplus
│   ├── prepare_gsmap.sh           # Normalisasi GSMAP
│   ├── inspect_nc.py              # Inspect NetCDF
│   ├── export_dashboard_data.py   # Export ke JSON/CSV
│   └── generate_sample_data.py    # Sample data testing
├── dashboard/
│   ├── app.py                     # Main Streamlit app
│   ├── pages/
│   │   ├── 1_Overview.py
│   │   ├── 2_Time_Series.py
│   │   └── 3_Threshold_Analysis.py
│   ├── lib/
│   │   ├── stat_parser.py
│   │   ├── data_loader.py
│   │   └── plots.py
│   └── requirements.txt
└── sample_data/                   # Data sample untuk testing
```

## Update Harian

INanWP di-update daily di server. Untuk otomasi:

```bash
# Crontab di server litbangweb (contoh: setiap hari jam 06:00 UTC)
0 6 * * * /path/to/metplus/scripts/run_verification.sh $(date -u -d 'yesterday' +%Y%m%d)00 $(date -u -d 'yesterday' +%Y%m%d)23
```

Dashboard akan otomatis mengambil data terbaru sesuai `REFRESH_INTERVAL` di `.env`.

## Referensi

- [METplus Documentation](https://metplus.readthedocs.io/)
- [GridStat Precipitation Use Case](https://metplus.readthedocs.io/en/develop/generated/model_applications/precipitation/GridStat_fcstHREFmean_obsStgIV_NetCDF.html)
- [GSMaP NRT Dataset](https://developers.google.com/earth-engine/datasets/catalog/JAXA_GPM_L3_GSMaP_v8_operational)
