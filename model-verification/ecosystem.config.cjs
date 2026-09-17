/**
 * PM2 — Model Verification @ /model-verification (webpsi)
 * Ports: API 8028 · static 3028
 */
const fs = require("fs");
const path = require("path");

function readDotEnv(file) {
  const out = {};
  try {
    const text = fs.readFileSync(path.resolve(__dirname, file), "utf8");
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith("#") || !line.includes("=")) continue;
      const i = line.indexOf("=");
      const k = line.slice(0, i).trim();
      const v = line.slice(i + 1).trim().replace(/^['"]|['"]$/g, "");
      if (k) out[k] = v;
    }
  } catch (_) { /* optional */ }
  return out;
}

const fileEnv = readDotEnv(".env");
const env = {
  ...fileEnv,
  SERVE_READONLY: fileEnv.SERVE_READONLY || "true",
  STORE_BACKEND: fileEnv.STORE_BACKEND || "f32",
  BASE_PATH: fileEnv.BASE_PATH || "/model-verification",
  API_PORT: fileEnv.API_PORT || "8028",
  FRONTEND_PORT: fileEnv.FRONTEND_PORT || "3028",
  DEFAULT_METHOD: fileEnv.DEFAULT_METHOD || "harp",
};

module.exports = {
  apps: [
    {
      name: "model-verification-api",
      cwd: "/var/www/model-verification",
      script: ".venv/bin/python",
      args: "-m uvicorn backend.main:app --host 127.0.0.1 --port 8028",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_memory_restart: "1G",
      env,
    },
    {
      name: "model-verification-web",
      cwd: "/var/www/model-verification",
      script: "server-static.js",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      env: {
        ...env,
        PORT: "3028",
        STATIC_ROOT: "frontend",
        BASE_PATH: "/model-verification",
      },
    },
  ],
};
