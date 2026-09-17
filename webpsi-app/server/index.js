#!/usr/bin/env node
/**
 * API Verifikasi InaNWP — METplus GridStat output
 * Bind 127.0.0.1:8018 — publik via /verifikasi-inanwp/api
 */
const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");

const HOST = process.env.HOST || "127.0.0.1";
const PORT = parseInt(process.env.PORT || "8018", 10);
const DATA_DIR = process.env.METPLUS_DATA_DIR || path.join(__dirname, "..", "data", "metplus");
const CORS_ORIGIN = process.env.CORS_ORIGIN || "https://psimkg.bmkg.go.id";

const app = express();
app.use(cors({ origin: [CORS_ORIGIN, "http://127.0.0.1:3018"] }));
app.use(express.json());

function readJsonSafe(file) {
  const p = path.join(DATA_DIR, file);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function findStatFiles() {
  const root = path.join(DATA_DIR, "gridstat");
  if (!fs.existsSync(root)) return [];
  const out = [];
  for (const dir of fs.readdirSync(root)) {
    const full = path.join(root, dir);
    if (!fs.statSync(full).isDirectory()) continue;
    for (const f of fs.readdirSync(full)) {
      if (f.endsWith(".stat")) out.push(path.join(full, f));
    }
  }
  return out.sort();
}

function parseStatFile(filePath) {
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/).filter(Boolean);
  const records = [];
  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length < 24) continue;
    // Find line type token
    const types = ["CNT", "CTS", "CTC", "SL1L2", "FHO"];
    let typeIdx = -1;
    let lineType = null;
    for (const t of types) {
      const i = parts.indexOf(t);
      if (i > 0) {
        typeIdx = i;
        lineType = t;
        break;
      }
    }
    if (!lineType) continue;
    const rec = {
      version: parts[0],
      model: parts[1],
      desc: parts[2],
      fcst_lead: parts[3],
      line_type: lineType,
      fcst_var: parts[10] || parts[9],
      fcst_thresh: parts[typeIdx - 4] || "NA",
      obs_thresh: parts[typeIdx - 3] || "NA",
      source_file: path.basename(filePath),
      valid_dir: path.basename(path.dirname(filePath)),
    };
    const body = parts.slice(typeIdx + 1);
    if (lineType === "CNT" && body.length > 0) {
      rec.total = num(body[0]);
      // RMSE often appears in continuous block; scan plausible values
      rec.rmse = findFloatNear(body, 2, 20);
      rec.me = findSignedFloat(body);
    }
    if (lineType === "CTS" && body.length > 5) {
      rec.total = num(body[0]);
      // ETS/CSI appear later; keep raw for dashboard display
      rec.baser = num(body[1]);
      rec.fmean = num(body[6]);
      rec.acc = num(body[9]);
      rec.fbias = findFloatNear(body, 0.01, 20);
      rec.ets = findFloatNear(body, 0, 1);
    }
    if (lineType === "CTC" && body.length >= 5) {
      rec.total = num(body[0]);
      rec.fy_oy = num(body[1]);
      rec.fy_on = num(body[2]);
      rec.fn_oy = num(body[3]);
      rec.fn_on = num(body[4]);
    }
    records.push(rec);
  }
  return records;
}

function num(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

function findFloatNear(arr, min, max) {
  for (const v of arr) {
    const n = parseFloat(v);
    if (Number.isFinite(n) && n >= min && n <= max) return n;
  }
  return null;
}

function findSignedFloat(arr) {
  for (const v of arr) {
    if (!v.startsWith("-") && !v.startsWith("+")) continue;
    const n = parseFloat(v);
    if (Number.isFinite(n) && Math.abs(n) < 50) return n;
  }
  return null;
}

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "verifikasi-inanwp-api", data_dir: DATA_DIR });
});

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, service: "verifikasi-inanwp-api" });
});

app.get("/api/summary", (_req, res) => {
  const summary = readJsonSafe("dashboard/summary.json") || readJsonSafe("summary.json");
  const statFiles = findStatFiles();
  const records = statFiles.flatMap(parseStatFile);
  const cnt = records.filter((r) => r.line_type === "CNT");
  const cts = records.filter((r) => r.line_type === "CTS");
  res.json({
    generated_at: summary?.generated_at || new Date().toISOString(),
    model: summary?.model || "INANWP",
    observation: summary?.observation || "GSMAP NRT",
    status: summary?.status || (statFiles.length ? "READY" : "NO_DATA"),
    matched_pairs: summary?.matched_pairs || cnt[0]?.total || null,
    valid: summary?.valid || (statFiles[0] ? path.basename(path.dirname(statFiles[0])) : null),
    accum_hours: summary?.accum_hours || 3,
    note: summary?.note || null,
    n_stat_files: statFiles.length,
    n_records: records.length,
    metrics: {
      rmse: cnt[0]?.rmse ?? null,
      me: cnt[0]?.me ?? null,
      n_cts: cts.length,
    },
  });
});

app.get("/api/stats", (_req, res) => {
  const records = findStatFiles().flatMap(parseStatFile);
  res.json({ count: records.length, records });
});

app.get("/api/files", (_req, res) => {
  res.json({
    data_dir: DATA_DIR,
    stat_files: findStatFiles().map((f) => path.relative(DATA_DIR, f)),
    summary_exists: !!(readJsonSafe("dashboard/summary.json") || readJsonSafe("summary.json")),
  });
});

app.listen(PORT, HOST, () => {
  console.log(`API listening http://${HOST}:${PORT}`);
  console.log(`DATA_DIR=${DATA_DIR}`);
});
