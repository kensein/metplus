# DPU automation — InaNWP vs GSMAP (GridStat + PointStat + FSS + MODE)

Scripts di folder ini di-deploy ke `dpu@192.168.15.139:~/apps/verifikasi-inanwp`.

## Metode

| Script | Output | Deskripsi |
|--------|--------|-----------|
| `run_one_valid.sh` | `gridstat/` + `maps/` | GridStat spasial |
| `run_pointstat_valid.sh` | `pointstat/` | PointStat vs **BMKG Soft/Sinoptik** (sama obs HARP) |
| `run_fss_mode_valid.sh` | `fss/` + `mode/` | FSS neighborhood + MODE objects |
| `export_series.py` | `dashboard/series*.json` | Export ranking/grafik |
| `wipe_metplus.sh` | — | Hapus kalkulasi lama |
| `daily_verify_push.sh` | + push webpsi | Orkestrasi H+3…H+72 |

## Jalankan ulang dari awal

```bash
source ~/apps/activate_metplus.sh
cd ~/apps/verifikasi-inanwp
WIPE_FIRST=1 FORCE_RERUN=1 bash daily_verify_push.sh
# log: ~/data/metplus/logs/daily_YYYYMMDD.log
```

Wrfout terbaru: `/home/klimat/inanwp/wrfout_d01_*` (pakai `START_DATE` di dalam file).
