/**
 * PM2 — Verifikasi InaNWP (METplus)
 * FE :3018  |  API :8018  |  bind 127.0.0.1
 */
module.exports = {
  apps: [
    {
      name: "verifikasi-inanwp-api",
      cwd: "/var/www/verifikasi-inanwp/server",
      script: "index.js",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_memory_restart: "256M",
      env: {
        NODE_ENV: "production",
        HOST: "127.0.0.1",
        PORT: 8018,
        CORS_ORIGIN: "https://psimkg.bmkg.go.id",
        METPLUS_DATA_DIR: "/var/www/verifikasi-inanwp/data/metplus",
      },
    },
    {
      name: "verifikasi-inanwp-web",
      cwd: "/var/www/verifikasi-inanwp",
      script: "server-static.js",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_memory_restart: "128M",
      env: {
        NODE_ENV: "production",
        HOSTNAME: "127.0.0.1",
        PORT: 3018,
        BASE_PATH: "/verifikasi-inanwp",
      },
    },
  ],
};
