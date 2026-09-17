# Deploy Verifikasi InaNWP → webpsi

**Target:** `psimkg.bmkg.go.id/verifikasi-inanwp`  
**Host:** vm-webpsi (`vmhosting@103.169.3.180:65000`)  
**Path:** `/var/www/verifikasi-inanwp`  
**Ports:** FE `127.0.0.1:3018`, API `127.0.0.1:8018`  
**PM2 (root):** `verifikasi-inanwp-api`, `verifikasi-inanwp-web`

## Layout

```
/var/www/verifikasi-inanwp/
  ecosystem.config.cjs
  server-static.js
  frontend/
  server/          # Express API
  data/metplus/    # sync dari DPU /home/dpu/data/metplus
  logs/
```

## Apache

Sisipkan snippet `apache-snippet.conf` ke `bmkg-portal.conf` **sebelum** catch-all `ProxyPass /` ke `:3001`.  
Jangan ubah rule app lain yang sudah stabil.

```bash
sudo apache2ctl configtest && sudo systemctl reload apache2
```

## PM2

```bash
cd /var/www/verifikasi-inanwp/server && npm install --omit=dev
cd /var/www/verifikasi-inanwp
sudo pm2 startOrReload ecosystem.config.cjs
sudo pm2 save
```

## Sync data METplus (DPU → webpsi)

DPU: `dpu@192.168.15.139` path `/home/dpu/data/metplus`  
(reachable via jump host ymcserver bila perlu)

```bash
rsync -avz --delete \
  dpu@192.168.15.139:/home/dpu/data/metplus/ \
  /var/www/verifikasi-inanwp/data/metplus/
```

## Verify

```bash
curl -s http://127.0.0.1:8018/api/health
curl -s http://127.0.0.1:3018/verifikasi-inanwp/
curl -sI https://psimkg.bmkg.go.id/verifikasi-inanwp/
```
