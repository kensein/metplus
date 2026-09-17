# Panduan Deploy — Verifikasi INanWP vs GSMAP

Dokumen ini fokus pada **setup environment server**, bukan pembuatan aplikasi dashboard.
Ikuti urutan: **litbangweb dulu** (proses METplus), lalu **webpsi** (deploy & konsumsi output).

---

## Gambaran Arsitektur

```
┌──────────────────────────────────────────────┐
│  SERVER LITBANGWEB                           │
│  (komputasi verifikasi)                      │
│                                              │
│  Input:                                      │
│    /mnt/wdd1/www/htdocs/wrf/wrfout/          │  ← INanWP (update daily)
│    /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_*/     │  ← GSMAP NRT
│                                              │
│  Proses: METplus (RegridDataPlane+GridStat)  │
│                                              │
│  Output:                                     │
│    /mnt/wdd1/www/htdocs/wrf/metplus/         │
│      ├── gridstat/    (.stat files)          │
│      └── dashboard/   (JSON/CSV siap konsumsi)│
└──────────────────────┬───────────────────────┘
                       │ rsync / scp / NFS
                       ▼
┌──────────────────────────────────────────────┐
│  SERVER WEBPSI (psimkg.bmkg.go.id)           │
│  (tampilan publik)                           │
│                                              │
│  App path:  /var/www/verifikasi-inanwp/      │
│  Data path: /var/www/verifikasi-inanwp/data/ │
│  Publik:    https://psimkg.bmkg.go.id/       │
│             verifikasi-inanwp/               │
│                                              │
│  FE : 127.0.0.1:3013  (PM2)                  │
│  API: 127.0.0.1:8013  (PM2)                  │
│  Proxy: Apache vhost portal                  │
└──────────────────────────────────────────────┘
```

---

# BAGIAN A — Server litbangweb

Server ini menjalankan METplus. Data NC lokal Anda (download) **sama persis** penamaan dan strukturnya dengan server ini.

## A.1 — Prasyarat

| Item | Keterangan |
|------|------------|
| OS | Linux (CentOS/RHEL/Ubuntu) |
| Python | ≥ 3.9 |
| METplus | Terinstal, contoh `/opt/METplus` |
| MET | Terinstal, contoh `/opt/MET` |
| Akses data | Read ke `/mnt/wdd1/www/htdocs/wrf/` |
| Akses output | Write ke `/mnt/wdd1/www/htdocs/wrf/metplus/` |

Cek instalasi METplus:

```bash
ls /opt/METplus/METplus/scripts/run_metplus.py
ls /opt/MET/bin/grid_stat
```

Jika belum terinstal, ikuti: https://metplus.readthedocs.io/en/latest/Users_Guide/installation.html

## A.2 — Clone repo ke litbangweb

```bash
sudo mkdir -p /opt/metplus-verifikasi
sudo chown $USER:$USER /opt/metplus-verifikasi
cd /opt/metplus-verifikasi
git clone https://github.com/kensein/metplus.git .
git checkout cursor/inanwp-gsmap-dashboard-485a   # atau branch main setelah merge
```

## A.3 — Verifikasi data input ada

```bash
# INanWP — contoh file sesuai download lokal Anda
ls -lh /mnt/wdd1/www/htdocs/wrf/wrfout/2026070112-d01-asim.nc

# GSMAP NRT — periode 27-30 Juli 2026
ls -lh /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/

# Lihat semua file INanWP yang tersedia
ls /mnt/wdd1/www/htdocs/wrf/wrfout/*.nc | head -20
```

**Catatan penamaan file INanWP:** `{init}12-d01-asim.nc`
Contoh: `2026070112-d01-asim.nc` = init 2026-07-01 12Z, domain d01.

## A.4 — Inspect variable NetCDF (WAJIB, sekali)

Jalankan sebelum konfigurasi METplus agar variable name benar:

```bash
cd /opt/metplus-verifikasi

python3 scripts/inspect_nc.py \
    /mnt/wdd1/www/htdocs/wrf/wrfout/2026070112-d01-asim.nc

python3 scripts/inspect_nc.py \
    /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/*.nc | head -60
```

Catat output:
- **Variable forecast (INanWP):** biasanya `RAINNC`, `RAINC`, atau `APCP`
- **Variable observasi (GSMAP):** biasanya `hourlyPrecipRateGC` atau `hourlyPrecipRate`

Edit `config/inanwp_gsmap.conf` jika berbeda:

```bash
nano config/inanwp_gsmap.conf
# Ubah baris:
#   FCST_VAR1_NAME = RAINNC
#   OBS_VAR1_NAME  = hourlyPrecipRateGC
```

## A.5 — Siapkan direktori output

```bash
sudo mkdir -p /mnt/wdd1/www/htdocs/wrf/metplus/{gridstat,gsmap_regrid,dashboard,logs}
sudo chown -R $USER:$USER /mnt/wdd1/www/htdocs/wrf/metplus
```

## A.6 — Normalisasi nama file GSMAP

GSMAP perlu dinormalisasi ke pola `gsmap_YYYYMMDDHH.nc`:

```bash
cd /opt/metplus-verifikasi
bash scripts/prepare_gsmap.sh \
    /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730 \
    /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/prepared

# Verifikasi hasil
ls /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/prepared/ | head -10
```

Jika GSMAP sudah bernama `gsmap_YYYYMMDDHH.nc`, update `config/inanwp_system.conf`:

```ini
OBS_DIR = /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/prepared
```

## A.7 — Sesuaikan config sistem

Edit `config/inanwp_system.conf` — pastikan path benar:

```ini
METPLUS_BASE  = /opt/METplus        # sesuaikan instalasi Anda
MET_INSTALL_DIR = /opt/MET
FCST_DIR      = /mnt/wdd1/www/htdocs/wrf/wrfout
OBS_DIR       = /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/prepared
OUTPUT_BASE   = /mnt/wdd1/www/htdocs/wrf/metplus
TMP_DIR       = /tmp/metplus_inanwp
```

## A.8 — Jalankan verifikasi METplus (pertama kali)

Periode awal: 27–30 Juli 2026:

```bash
cd /opt/metplus-verifikasi

# Set periode di config (jika perlu)
# VALID_BEG=2026072700  VALID_END=2026073023  → sudah di inanwp_gsmap.conf

bash scripts/run_verification.sh 2026072700 2026073023
```

Atau manual:

```bash
python3 /opt/METplus/METplus/scripts/run_metplus.py \
    /opt/metplus-verifikasi/config/inanwp_gsmap.conf \
    /opt/metplus-verifikasi/config/inanwp_system.conf \
    2>&1 | tee /mnt/wdd1/www/htdocs/wrf/metplus/logs/run_$(date +%Y%m%d_%H%M%S).log
```

**Cek output:**

```bash
# File STAT (raw METplus)
find /mnt/wdd1/www/htdocs/wrf/metplus/gridstat -name "*.stat" | head -5

# File dashboard (JSON/CSV)
ls -lh /mnt/wdd1/www/htdocs/wrf/metplus/dashboard/
# Harus ada: summary.json, verification_stats.csv, manifest.json
```

## A.9 — Export data dashboard (jika belum otomatis)

```bash
python3 /opt/metplus-verifikasi/scripts/export_dashboard_data.py \
    --input-dir  /mnt/wdd1/www/htdocs/wrf/metplus/gridstat \
    --output-dir /mnt/wdd1/www/htdocs/wrf/metplus/dashboard
```

Verifikasi isi:

```bash
python3 -c "
import json
s = json.load(open('/mnt/wdd1/www/htdocs/wrf/metplus/dashboard/summary.json'))
print('Valid times:', len(s.get('valid_times',[])))
print('RMSE mean:', s.get('metrics',{}).get('overall',{}).get('rmse_mean'))
"
```

## A.10 — Otomasi harian (cron)

INanWP update daily. Tambahkan cron untuk proses otomatis setiap hari:

```bash
crontab -e
```

Tambahkan (sesuaikan path dan waktu):

```cron
# Verifikasi INanWP vs GSMAP — setiap hari jam 07:00 WIB (00:00 UTC)
0 0 * * * /opt/metplus-verifikasi/scripts/run_verification.sh $(date -u -d 'yesterday' +\%Y\%m\%d)00 $(date -u -d 'yesterday' +\%Y\%m\%d)23 >> /mnt/wdd1/www/htdocs/wrf/metplus/logs/cron.log 2>&1
```

## A.11 — Sync output ke webpsi

Setelah verifikasi selesai, kirim data ke server webpsi.

**Opsi A — rsync via SSH (disarankan):**

```bash
# Di litbangweb — jalankan manual atau tambahkan ke cron setelah run_verification.sh
rsync -avz --delete \
    /mnt/wdd1/www/htdocs/wrf/metplus/dashboard/ \
    user@webpsi:/var/www/verifikasi-inanwp/data/metplus/
```

**Opsi B — scp:**

```bash
scp -r /mnt/wdd1/www/htdocs/wrf/metplus/dashboard/* \
    user@webpsi:/var/www/verifikasi-inanwp/data/metplus/
```

**Opsi C — NFS mount** (jika infrastruktur mendukung):
Mount `/mnt/wdd1/www/htdocs/wrf/metplus/dashboard` dari litbangweb ke webpsi.

Gunakan script bantu:

```bash
bash /opt/metplus-verifikasi/scripts/sync_to_webpsi.sh
# Edit WEBPSI_HOST dan WEBPSI_USER di script sebelum menjalankan
```

---

# BAGIAN B — Server webpsi (psimkg.bmkg.go.id)

Server ini menampilkan dashboard publik di subpath `/verifikasi-inanwp/`.
**Tidak menjalankan METplus** — hanya membaca output dari litbangweb.

## B.1 — Prasyarat

| Item | Nilai |
|------|-------|
| Node.js | 22 LTS (`node -v`) |
| PM2 | Terpasang (`pm2 -v`) |
| Apache | Reverse proxy aktif (vhost portal) |
| Deploy path | `/var/www/verifikasi-inanwp` |
| Port FE | 3013 (127.0.0.1 only) |
| Port API | 8013 (127.0.0.1 only) |
| Publik | `https://psimkg.bmkg.go.id/verifikasi-inanwp/` |

Cek port tidak bentrok:

```bash
ss -tlnp | grep -E '3013|8013'
# Harus kosong sebelum deploy
```

Port lain yang sudah dipakai di server ini:

| App | FE | API |
|-----|----|-----|
| Portal websitepsimkg | — | 3001 |
| P3DN | 3002 | — |
| PSIIDN | 3010 | 8010 |
| Instrument | 3011 | 8011 |
| Otomatisasi | 3012 | 8012 |
| **Verifikasi InaNWP** | **3013** | **8013** |

## B.2 — Buat direktori deploy

```bash
sudo mkdir -p /var/www/verifikasi-inanwp/data/metplus
sudo chown -R $USER:$USER /var/www/verifikasi-inanwp
```

Struktur target:

```
/var/www/verifikasi-inanwp/
├── data/
│   └── metplus/          ← data dari litbangweb (JANGAN dieksekusi)
│       ├── summary.json
│       ├── verification_stats.csv
│       └── manifest.json
├── server/               ← backend API (repo app verifikasi)
├── dist/                 ← frontend build
├── ecosystem.config.cjs  ← PM2 config
├── server-static.js      ← serve frontend static
└── .env                  ← env production (jangan commit)
```

## B.3 — Clone repo aplikasi verifikasi

```bash
cd /var/www/verifikasi-inanwp
git clone <URL-repo-aplikasi-verifikasi-inanwp> .
# Branch sesuai instruksi tim PSIMKG
```

> **Catatan:** Repo aplikasi dashboard verifikasi (`/var/www/verifikasi-inanwp`) adalah repo **terpisah**
> dari repo METplus pipeline ini (`kensein/metplus`). Repo METplus hanya untuk proses di litbangweb.
> Clone repo app verifikasi sesuai yang disediakan agent websitepsimkg.

## B.4 — Terima data pertama dari litbangweb

Dari **litbangweb**, jalankan sync (lihat A.11). Lalu di **webpsi** verifikasi:

```bash
ls -lh /var/www/verifikasi-inanwp/data/metplus/
# summary.json  verification_stats.csv  manifest.json

# Cek isi valid
python3 -c "
import json
s=json.load(open('/var/www/verifikasi-inanwp/data/metplus/summary.json'))
print('Records:', s.get('total_records'))
print('Period:', s.get('valid_times',[])[:2], '...', s.get('valid_times',[])[-2:])
"
```

## B.5 — Konfigurasi environment (.env)

Buat `/var/www/verifikasi-inanwp/.env`:

```bash
cp .env.example .env
nano .env
```

Isi production:

```env
# Frontend
PORT=3013
HOSTNAME=127.0.0.1
BASE_PATH=/verifikasi-inanwp

# Backend API
API_PORT=8013
HOST=127.0.0.1
CORS_ORIGIN=https://psimkg.bmkg.go.id
DATA_DIR=/var/www/verifikasi-inanwp/data
METPLUS_DATA_DIR=/var/www/verifikasi-inanwp/data/metplus
NODE_ENV=production
```

Buat juga env backend di `server/.env`:

```env
HOST=127.0.0.1
PORT=8013
CORS_ORIGIN=https://psimkg.bmkg.go.id
DATA_DIR=/var/www/verifikasi-inanwp/data
METPLUS_DATA_DIR=/var/www/verifikasi-inanwp/data/metplus
NODE_ENV=production
```

## B.6 — Build aplikasi

```bash
cd /var/www/verifikasi-inanwp

# Install dependencies
npm install
cd server && npm install && cd ..

# Build frontend + backend
npm run build
cd server && npm run build && cd ..
```

## B.7 — PM2 — jalankan aplikasi

Salin `deploy/ecosystem.config.cjs` dari repo METplus sebagai referensi, atau gunakan:

```bash
cd /var/www/verifikasi-inanwp
pm2 startOrReload ecosystem.config.cjs
pm2 save
pm2 status
```

Verifikasi proses listen di localhost saja:

```bash
ss -tlnp | grep -E '3013|8013'
# Harus menunjukkan 127.0.0.1:3013 dan 127.0.0.1:8013
```

Test lokal (di webpsi):

```bash
curl -sI http://127.0.0.1:3013/verifikasi-inanwp/ | head -5
curl -s http://127.0.0.1:8013/health
curl -s http://127.0.0.1:8013/api/summary | python3 -m json.tool | head -20
```

## B.8 — Apache reverse proxy

Tambahkan blok berikut ke **vhost portal** Apache (`websitepsimkg`).
**PENTING:** Tambahkan **SEBELUM** catch-all `ProxyPass /` ke `:3001`.

```apache
# === Verifikasi InaNWP (sub-app) ===
# API lebih spesifik — HARUS di atas rule /verifikasi-inanwp
ProxyPass        /verifikasi-inanwp/api http://127.0.0.1:8013/
ProxyPassReverse /verifikasi-inanwp/api http://127.0.0.1:8013/

# Frontend static
ProxyPass        /verifikasi-inanwp     http://127.0.0.1:3013/verifikasi-inanwp
ProxyPassReverse /verifikasi-inanwp     http://127.0.0.1:3013/verifikasi-inanwp
# === end Verifikasi InaNWP ===

# (rule existing portal — jangan ubah)
# ProxyPass        / http://127.0.0.1:3001/
# ProxyPassReverse / http://127.0.0.1:3001/
```

Validasi dan reload:

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

File referensi lengkap: `deploy/apache-verifikasi-inanwp.conf`

## B.9 — Uji akses publik

```bash
# Frontend
curl -sI https://psimkg.bmkg.go.id/verifikasi-inanwp/ | head -10

# API health
curl -s https://psimkg.bmkg.go.id/verifikasi-inanwp/api/health

# API data summary
curl -s https://psimkg.bmkg.go.id/verifikasi-inanwp/api/summary | python3 -m json.tool | head -20
```

Pastikan:
- HTTP 200 (bukan 404 atau 502)
- Asset JS/CSS load dari `/verifikasi-inanwp/assets/...` (bukan `/assets/...` di root)
- Tidak ada mixed content (semua HTTPS)

## B.10 — Otomasi sync data harian (webpsi)

Tambahkan cron di webpsi untuk tarik data terbaru dari litbangweb:

```bash
crontab -e
```

```cron
# Tarik output METplus dari litbangweb — 30 menit setelah cron litbangweb
30 0 * * * rsync -avz --delete litbangweb:/mnt/wdd1/www/htdocs/wrf/metplus/dashboard/ /var/www/verifikasi-inanwp/data/metplus/ >> /var/log/sync-metplus.log 2>&1
```

---

# BAGIAN C — Checklist Deploy

## litbangweb

- [ ] METplus terinstal dan `run_metplus.py` bisa dijalankan
- [ ] Data INanWP ada di `/mnt/wdd1/www/htdocs/wrf/wrfout/`
- [ ] Data GSMAP ada di `/mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/`
- [ ] `inspect_nc.py` sudah dijalankan, variable name dikonfirmasi
- [ ] `config/inanwp_gsmap.conf` dan `inanwp_system.conf` sudah disesuaikan
- [ ] Verifikasi METplus berhasil (`*.stat` files ada)
- [ ] Export dashboard berhasil (`summary.json`, `verification_stats.csv`, `manifest.json`)
- [ ] Cron harian aktif
- [ ] rsync ke webpsi berhasil

## webpsi

- [ ] Node 22 + PM2 terpasang
- [ ] Port 3013 dan 8013 kosong
- [ ] `/var/www/verifikasi-inanwp/data/metplus/` berisi data dari litbangweb
- [ ] `.env` production sudah dibuat (tidak di-commit)
- [ ] `npm run build` sukses
- [ ] PM2 running: `verifikasi-inanwp-web` + `verifikasi-inanwp-api`
- [ ] Listen hanya `127.0.0.1:3013` dan `127.0.0.1:8013`
- [ ] Apache ProxyPass ditambahkan **sebelum** catch-all `:3001`
- [ ] `curl https://psimkg.bmkg.go.id/verifikasi-inanwp/` → 200
- [ ] `curl https://psimkg.bmkg.go.id/verifikasi-inanwp/api/health` → OK
- [ ] Cron sync data harian aktif

---

# BAGIAN D — Troubleshooting

| Gejala | Kemungkinan | Solusi |
|--------|-------------|--------|
| METplus error "file not found" | Template nama file salah | Cek `FCST_GRID_STAT_INPUT_TEMPLATE` vs nama file aktual di `wrfout/` |
| METplus error variable | Variable NetCDF berbeda | Jalankan `inspect_nc.py`, update `FCST_VAR1_NAME` / `OBS_VAR1_NAME` |
| GSMAP tidak match waktu | Format timestamp berbeda | Jalankan `prepare_gsmap.sh`, cek folder `prepared/` |
| Dashboard kosong di webpsi | Data belum di-sync | Jalankan rsync dari litbangweb, cek `/data/metplus/summary.json` |
| 502 Bad Gateway | PM2 tidak jalan | `pm2 status`, `pm2 logs verifikasi-inanwp-api` |
| 404 assets JS/CSS | Base path Vite salah | Pastikan `base: '/verifikasi-inanwp/'` di vite.config |
| API 404 | Urutan ProxyPass salah | `/verifikasi-inanwp/api` harus **di atas** `/verifikasi-inanwp` |
| Port conflict | Port sudah dipakai app lain | `ss -tlnp`, jangan pakai 3001/3010/3011/3012 |

---

# BAGIAN E — Path Referensi Cepat

```
LITBANGWEB
  Input INanWP : /mnt/wdd1/www/htdocs/wrf/wrfout/
  Input GSMAP  : /mnt/wdd1/www/htdocs/wrf/gsmap_nrt_20260727_20260730/
  Output       : /mnt/wdd1/www/htdocs/wrf/metplus/dashboard/
  Repo pipeline: /opt/metplus-verifikasi/

WEBPSI
  App          : /var/www/verifikasi-inanwp/
  Data         : /var/www/verifikasi-inanwp/data/metplus/
  Publik       : https://psimkg.bmkg.go.id/verifikasi-inanwp/
  PM2 FE       : 127.0.0.1:3013
  PM2 API      : 127.0.0.1:8013
```
