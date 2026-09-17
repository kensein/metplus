# Hasil test run METplus di DPU (17 Sep 2026)

## Temuan data INanWP

File: `/home/klimat/inanwp/wrfout_d01_2026-09-16_00:00:00`

| Metadata | Nilai |
|----------|-------|
| Nama file | seolah 16 Sep 2026 |
| `START_DATE` aktual | **2026-06-15_12:00:00** |
| Output interval | **3-jamannan** (XTIME 0,180,...,4320 menit) |
| Variable hujan | `RAINNC` (accumulated mm) |
| Domain | lat ~-15..10, lon ~94..144 |

## GSMAP

Sumber: `ftp://202.90.199.64/himawari6/GSMaP/netcdf/`

- Variable: `rainrate`
- File uji: `GSMaP_202606151200.nc` … `1400.nc` (dijumlah 3 jam)

## Test case

- Valid: **2026-06-15 15Z**
- Forecast: `RAINNC(t1)-RAINNC(t0)` → 3h precip
- Obs: sum GSMAP rainrate jam 12+13+14
- Tools: `regrid_data_plane` (BUDGET) + `grid_stat`

## Hasil

- Matched pairs: **192820**
- Output:
  - `/home/dpu/data/metplus/gridstat/2026061515/*.stat`
  - `/home/dpu/data/metplus/gridstat/2026061515/*_pairs.nc`
- CTS thresholds: `>0.1`, `>1`, `>5`, `>10` mm

## Path DPU yang dipakai

```
/home/dpu/data/wrfout/inanwp_precip3h_2026061515.nc
/home/dpu/data/gsmap/raw/
/home/dpu/data/gsmap/prepared/gsmap_precip3h_2026061515.nc
/home/dpu/data/metplus/
/home/dpu/apps/metplus-config/inanwp_system_dpu.conf
```

## Catatan

1. ACL: user `dpu` sudah diberi baca ke `/home/klimat/inanwp`
2. Nama file wrfout **menyesatkan** — selalu cek `START_DATE` / `XTIME`
3. Untuk operasional, perlu wrfout harian yang benar + otomasi pull GSMAP dari FTP
