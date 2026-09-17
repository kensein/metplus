# Otomasi DPU → webpsi

Pipeline di server DPU (`dpu@192.168.15.139`):

1. Baca wrfout terbaru di `/home/klimat/inanwp`
2. Untuk setiap valid 3 jam yang belum ada output: siapkan precip, unduh GSMAP, GridStat, render peta
3. **Push** hasil ke webpsi via rsync/SSH (`push_to_webpsi.sh`)

Jangan pull dari webpsi ke DPU.

## Cron (user dpu)

```
30 1 * * * /home/dpu/apps/verifikasi-inanwp/daily_verify_push.sh
```

Sehari sekali (01:30 UTC), selaras dengan InaNWP yang jalan harian.
## Manual

```bash
source ~/apps/activate_metplus.sh
bash ~/apps/verifikasi-inanwp/daily_verify_push.sh
# atau hanya push:
bash ~/apps/verifikasi-inanwp/push_to_webpsi.sh
```
