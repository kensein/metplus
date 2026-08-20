/**
 * PM2 ecosystem — Verifikasi InaNWP PSIMKG
 * Deploy path: /var/www/verifikasi-inanwp
 *
 * Usage:
 *   cd /var/www/verifikasi-inanwp
 *   pm2 startOrReload ecosystem.config.cjs
 *   pm2 save
 */
module.exports = {
  apps: [
    {
      name: 'verifikasi-inanwp-api',
      cwd: '/var/www/verifikasi-inanwp/server',
      script: 'dist/index.js',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      max_restarts: 10,
      env: {
        NODE_ENV: 'production',
        HOST: '127.0.0.1',
        PORT: 8013,
        CORS_ORIGIN: 'https://psimkg.bmkg.go.id',
        DATA_DIR: '/var/www/verifikasi-inanwp/data',
        METPLUS_DATA_DIR: '/var/www/verifikasi-inanwp/data/metplus',
      },
    },
    {
      name: 'verifikasi-inanwp-web',
      cwd: '/var/www/verifikasi-inanwp',
      script: 'server-static.js',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      max_restarts: 10,
      env: {
        NODE_ENV: 'production',
        HOSTNAME: '127.0.0.1',
        PORT: 3013,
        BASE_PATH: '/verifikasi-inanwp',
      },
    },
  ],
};
