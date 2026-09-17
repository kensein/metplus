# METplus di Server DPU

Install selesai di `dpu@192.168.15.139` (via jump `meteo@202.90.199.129`).

## Versi terpasang

| Komponen | Path | Versi |
|----------|------|-------|
| MET | `/home/dpu/apps/MET` | V12.2.1 |
| METplus wrappers | `/home/dpu/apps/METplus` | 5.1.0 |
| Conda env | `/home/dpu/miniforge3/envs/metplus` | Python 3.11 |

## Cara pakai

```bash
# SSH ke DPU (via jump host)
ssh -J meteo@202.90.199.129 dpu@192.168.15.139

# Aktifkan (sudah juga di .bashrc)
source ~/apps/activate_metplus.sh

grid_stat -version
run_metplus.py -h
```

## Path data pipeline (siapkan)

```
/home/dpu/data/wrfout/     # INanWP NC
/home/dpu/data/gsmap/      # GSMAP
/home/dpu/data/metplus/    # output METplus
```

Config sistem DPU: `/home/dpu/apps/metplus-config/inanwp_system_dpu.conf`

## Catatan build

- Ubuntu 26.04 + GCC 15 butuh `CFLAGS=-std=gnu11` untuk NetCDF lama
- CMake system 4.x diganti conda CMake 3.28 untuk PROJ 7.1.0
- `compile_MET_all.sh` path `MET_DIR` bermasalah; MET dibuild manual setelah library deps siap
