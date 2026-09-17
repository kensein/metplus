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

/* MET v12.x body columns after LINE_TYPE (CI cols may be NA) */
const CNT_IDX = {
  TOTAL: 0, FBAR: 1, FSTDEV: 6, OBAR: 11, OSTDEV: 16,
  PR_CORR: 21, ME: 31, ESTDEV: 36, MBIAS: 41, MAE: 44, MSE: 50,
};
const CTS_IDX = {
  TOTAL: 0, BASER: 1, FMEAN: 6, ACC: 11, FBIAS: 16,
  PODY: 19, PODN: 24, POFD: 29, FAR: 34, CSI: 39, GSS: 44, HK: 47, HSS: 52,
};
const CTC_IDX = { TOTAL: 0, FY_OY: 1, FY_ON: 2, FN_OY: 3, FN_ON: 4 };

function readJsonSafe(file) {
  const p = path.join(DATA_DIR, file);
  if (!fs.existsSync(p)) return null;
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; }
}

function num(v) {
  if (v === undefined || v === null || v === "" || v === "NA") return null;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

function pick(body, idx) {
  return num(body[idx]);
}

function findStatFiles() {
  const root = path.join(DATA_DIR, "gridstat");
  if (!fs.existsSync(root)) return [];
  const out = [];
  for (const dir of fs.readdirSync(root).sort()) {
    const full = path.join(root, dir);
    if (!fs.statSync(full).isDirectory()) continue;
    for (const f of fs.readdirSync(full).sort()) {
      if (f.endsWith(".stat")) out.push(path.join(full, f));
    }
  }
  return out;
}

function findTxtFiles() {
  const root = path.join(DATA_DIR, "gridstat");
  if (!fs.existsSync(root)) return [];
  const out = [];
  for (const dir of fs.readdirSync(root).sort()) {
    const full = path.join(root, dir);
    if (!fs.statSync(full).isDirectory()) continue;
    for (const f of fs.readdirSync(full).sort()) {
      if (f.endsWith(".txt")) out.push(path.join(full, f));
    }
  }
  return out;
}

function findPairsFiles() {
  const root = path.join(DATA_DIR, "gridstat");
  if (!fs.existsSync(root)) return [];
  const out = [];
  for (const dir of fs.readdirSync(root).sort()) {
    const full = path.join(root, dir);
    if (!fs.statSync(full).isDirectory()) continue;
    for (const f of fs.readdirSync(full).sort()) {
      if (f.endsWith("_pairs.nc") || f.endsWith("pairs.nc")) out.push(path.join(full, f));
    }
  }
  return out;
}

function parseStatFile(filePath) {
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/).filter(Boolean);
  const records = [];
  for (const line of lines) {
    const parts = line.split(/\s+/);
    if (parts.length < 24) continue;
    const types = ["CNT", "CTS", "CTC", "SL1L2", "FHO"];
    let typeIdx = -1;
    let lineType = null;
    for (const t of types) {
      const i = parts.indexOf(t);
      if (i > 0) { typeIdx = i; lineType = t; break; }
    }
    if (!lineType) continue;
    const body = parts.slice(typeIdx + 1);
    const rec = {
      version: parts[0],
      model: parts[1],
      desc: parts[2],
      fcst_lead: parts[3],
      fcst_valid_beg: parts[4],
      line_type: lineType,
      fcst_var: parts[9],
      fcst_units: parts[10],
      obs_var: parts[12],
      obtype: parts[15],
      vx_mask: parts[16],
      fcst_thresh: parts[typeIdx - 4] || "NA",
      obs_thresh: parts[typeIdx - 3] || "NA",
      source_file: path.basename(filePath),
      valid_dir: path.basename(path.dirname(filePath)),
      relative_path: path.relative(DATA_DIR, filePath),
    };

    if (lineType === "CNT") {
      rec.total = pick(body, CNT_IDX.TOTAL);
      rec.fbar = pick(body, CNT_IDX.FBAR);
      rec.obar = pick(body, CNT_IDX.OBAR);
      rec.me = pick(body, CNT_IDX.ME);
      rec.mae = pick(body, CNT_IDX.MAE);
      rec.mse = pick(body, CNT_IDX.MSE);
      rec.pr_corr = pick(body, CNT_IDX.PR_CORR);
      rec.mbias = pick(body, CNT_IDX.MBIAS);
      const mse = rec.mse;
      rec.rmse = mse != null && mse >= 0 ? Math.sqrt(mse) : pick(body, CNT_IDX.ESTDEV);
    }
    if (lineType === "CTS") {
      rec.total = pick(body, CTS_IDX.TOTAL);
      rec.baser = pick(body, CTS_IDX.BASER);
      rec.fmean = pick(body, CTS_IDX.FMEAN);
      rec.acc = pick(body, CTS_IDX.ACC);
      rec.fbias = pick(body, CTS_IDX.FBIAS);
      rec.pod = pick(body, CTS_IDX.PODY);
      rec.pofd = pick(body, CTS_IDX.POFD);
      rec.far = pick(body, CTS_IDX.FAR);
      rec.csi = pick(body, CTS_IDX.CSI);
      rec.ets = pick(body, CTS_IDX.GSS);
      rec.hk = pick(body, CTS_IDX.HK);
      rec.hss = pick(body, CTS_IDX.HSS);
    }
    if (lineType === "CTC") {
      rec.total = pick(body, CTC_IDX.TOTAL);
      rec.fy_oy = pick(body, CTC_IDX.FY_OY);
      rec.fy_on = pick(body, CTC_IDX.FY_ON);
      rec.fn_oy = pick(body, CTC_IDX.FN_OY);
      rec.fn_on = pick(body, CTC_IDX.FN_ON);
    }
    if (lineType === "SL1L2" && body.length >= 7) {
      rec.total = pick(body, 0);
      rec.fbar = pick(body, 1);
      rec.obar = pick(body, 2);
      rec.fobar = pick(body, 3);
      rec.ffbar = pick(body, 4);
      rec.oobar = pick(body, 5);
    }
    records.push(rec);
  }
  return records;
}

function listMaps() {
  const mapsRoot = path.join(DATA_DIR, "maps");
  if (!fs.existsSync(mapsRoot)) return [];
  const out = [];
  for (const dir of fs.readdirSync(mapsRoot).sort()) {
    const full = path.join(mapsRoot, dir);
    if (!fs.statSync(full).isDirectory()) continue;
    const meta = readJsonSafe(path.join("maps", dir, "meta.json"));
    const pngs = fs.readdirSync(full).filter((f) => f.endsWith(".png")).sort();
    out.push({
      valid_dir: dir,
      meta,
      images: pngs.map((f) => ({
        name: f,
        label: f.replace(/\.png$/, "").toUpperCase(),
        url: `/verifikasi-inanwp/api/maps/${dir}/${f}`,
      })),
    });
  }
  return out;
}

function fileInfo(absPath) {
  const st = fs.statSync(absPath);
  return {
    name: path.basename(absPath),
    relative_path: path.relative(DATA_DIR, absPath),
    valid_dir: path.basename(path.dirname(absPath)),
    size_bytes: st.size,
    mtime: st.mtime.toISOString(),
    download_url: `/verifikasi-inanwp/api/download?path=${encodeURIComponent(path.relative(DATA_DIR, absPath))}`,
  };
}

function safeDataPath(rel) {
  const cleaned = path.normalize(rel || "").replace(/^(\.\.(\/|\\|$))+/, "");
  const abs = path.resolve(DATA_DIR, cleaned);
  if (!abs.startsWith(path.resolve(DATA_DIR))) return null;
  if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) return null;
  return abs;
}

function listValidDirs() {
  const root = path.join(DATA_DIR, "gridstat");
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root)
    .filter((d) => fs.statSync(path.join(root, d)).isDirectory())
    .sort()
    .reverse();
}

function filterByRun(items, run, getDir) {
  if (!run) return items;
  return items.filter((item) => getDir(item) === run);
}

function buildRunSummaries() {
  const dirs = listValidDirs();
  const allRecords = findStatFiles().flatMap(parseStatFile);
  const pairs = findPairsFiles();
  const maps = listMaps();
  return dirs.map((dir) => {
    const records = allRecords.filter((r) => r.valid_dir === dir);
    const cnt = records.find((r) => r.line_type === "CNT");
    const hasStat = records.length > 0;
    const hasPairs = pairs.some((f) => path.basename(path.dirname(f)) === dir);
    const hasMaps = maps.some((m) => m.valid_dir === dir);
    const meta = readJsonSafe(path.join("maps", dir, "meta.json"));
    return {
      run: dir,
      valid: meta?.valid || dir,
      status: hasStat ? "READY" : "NO_STAT",
      matched_pairs: cnt?.total ?? null,
      rmse: cnt?.rmse ?? null,
      me: cnt?.me ?? null,
      has_stat: hasStat,
      has_pairs: hasPairs,
      has_maps: hasMaps,
      n_records: records.length,
    };
  });
}

function resolveRun(queryRun) {
  const dirs = listValidDirs();
  if (!dirs.length) return null;
  if (queryRun && dirs.includes(queryRun)) return queryRun;
  return dirs[0];
}

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "verifikasi-inanwp-api", data_dir: DATA_DIR });
});

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, service: "verifikasi-inanwp-api" });
});

app.get("/api/runs", (_req, res) => {
  const runs = buildRunSummaries();
  const series = readJsonSafe("dashboard/series.json");
  res.json({
    count: runs.length,
    latest: runs[0]?.run || null,
    auto_update: true,
    note: "Otomasi aktif di DPU: sehari sekali, verifikasi 3 jam hingga H+72 (RAINNC+RAINC+RAINSH), push ke webpsi.",
    precip_source: series?.precip_source || "RAINNC+RAINC+RAINSH",
    series_points: series?.n_points || 0,
    series_init: series?.init || null,
    runs,
  });
});

app.get("/api/series", (_req, res) => {
  const series = readJsonSafe("dashboard/series.json");
  if (!series) {
    return res.json({
      n_points: 0,
      points: [],
      precip_source: "RAINNC+RAINC+RAINSH",
      note: "Belum ada seri H+3..H+72. Menunggu pipeline harian DPU.",
    });
  }
  res.json(series);
});

app.get("/api/summary", (req, res) => {
  const run = resolveRun(String(req.query.run || ""));
  const summary = readJsonSafe("dashboard/summary.json") || readJsonSafe("summary.json");
  const runMeta = run ? readJsonSafe(path.join("gridstat", run, "run_meta.json")) : null;
  const statFiles = filterByRun(findStatFiles(), run, (f) => path.basename(path.dirname(f)));
  const pairsFiles = filterByRun(findPairsFiles(), run, (f) => path.basename(path.dirname(f)));
  const txtFiles = filterByRun(findTxtFiles(), run, (f) => path.basename(path.dirname(f)));
  const records = statFiles.flatMap(parseStatFile);
  const cnt = records.filter((r) => r.line_type === "CNT");
  const cts = records.filter((r) => r.line_type === "CTS");
  const maps = listMaps().filter((m) => !run || m.valid_dir === run);
  const mapMeta = maps[0]?.meta;
  const meta = runMeta || summary || {};
  res.json({
    run,
    generated_at: meta.generated_at || new Date().toISOString(),
    model: meta.model || "INANWP",
    observation: meta.observation || "GSMAP NRT",
    status: meta.status || (statFiles.length ? "READY" : "NO_DATA"),
    matched_pairs: meta.matched_pairs || cnt[0]?.total || null,
    valid: meta.valid || mapMeta?.valid || run,
    accum_hours: meta.accum_hours || 3,
    precip_source: meta.precip_source || "RAINNC+RAINC+RAINSH",
    lead_hours: meta.lead_hours ?? null,
    init: meta.init || null,
    note: meta.note || null,
    n_stat_files: statFiles.length,
    n_txt_files: txtFiles.length,
    n_pairs_files: pairsFiles.length,
    n_map_sets: maps.length,
    n_records: records.length,
    n_runs: listValidDirs().length,
    metrics: {
      rmse: cnt[0]?.rmse ?? null,
      me: cnt[0]?.me ?? null,
      mae: cnt[0]?.mae ?? null,
      fbar: cnt[0]?.fbar ?? null,
      obar: cnt[0]?.obar ?? null,
      pr_corr: cnt[0]?.pr_corr ?? null,
      n_cts: cts.length,
    },
    files: {
      stat: statFiles.map((f) => path.relative(DATA_DIR, f)),
      txt: txtFiles.map((f) => path.relative(DATA_DIR, f)),
      pairs: pairsFiles.map((f) => path.relative(DATA_DIR, f)),
    },
  });
});

app.get("/api/stats", (req, res) => {
  const run = resolveRun(String(req.query.run || ""));
  const statFiles = filterByRun(findStatFiles(), run, (f) => path.basename(path.dirname(f)));
  const records = statFiles.flatMap(parseStatFile);
  res.json({ run, count: records.length, records });
});

app.get("/api/files", (req, res) => {
  const run = resolveRun(String(req.query.run || ""));
  res.json({
    run,
    data_dir: DATA_DIR,
    stat_files: filterByRun(findStatFiles().map(fileInfo), run, (f) => f.valid_dir),
    txt_files: filterByRun(findTxtFiles().map(fileInfo), run, (f) => f.valid_dir),
    pairs_files: filterByRun(findPairsFiles().map(fileInfo), run, (f) => f.valid_dir),
    maps: listMaps().filter((m) => !run || m.valid_dir === run),
    summary_exists: !!(readJsonSafe("dashboard/summary.json") || readJsonSafe("summary.json")),
    series_exists: !!readJsonSafe("dashboard/series.json"),
  });
});

app.get("/api/maps", (req, res) => {
  const run = resolveRun(String(req.query.run || ""));
  res.json({
    run,
    maps: listMaps().filter((m) => !run || m.valid_dir === run),
  });
});

app.get("/api/maps/:valid/:file", (req, res) => {
  const abs = safeDataPath(path.join("maps", req.params.valid, req.params.file));
  if (!abs || !abs.endsWith(".png")) return res.status(404).json({ error: "not found" });
  res.setHeader("Cache-Control", "public, max-age=300");
  res.sendFile(abs);
});

app.get("/api/download", (req, res) => {
  const abs = safeDataPath(String(req.query.path || ""));
  if (!abs) return res.status(404).json({ error: "not found" });
  const allowed = [".stat", ".txt", ".nc", ".json", ".log", ".png"];
  if (!allowed.some((ext) => abs.endsWith(ext))) {
    return res.status(403).json({ error: "file type not allowed" });
  }
  res.download(abs, path.basename(abs));
});

app.get("/api/stat-raw", (req, res) => {
  const run = resolveRun(String(req.query.run || ""));
  const txtFiles = filterByRun(findTxtFiles(), run, (f) => path.basename(path.dirname(f)));
  const statFiles = filterByRun(findStatFiles(), run, (f) => path.basename(path.dirname(f)));
  const preferTxt = txtFiles.find((f) => f.endsWith(".stat.txt")) || txtFiles.find((f) => path.basename(f).startsWith("scores_"));
  let target = preferTxt || statFiles[0];
  if (!target) return res.status(404).type("text").send("no .txt/.stat files");
  if (req.query.path) {
    const abs = safeDataPath(String(req.query.path));
    if (!abs || !(abs.endsWith(".stat") || abs.endsWith(".txt"))) {
      return res.status(404).type("text").send("not found");
    }
    target = abs;
  }
  res.type("text/plain").send(fs.readFileSync(target, "utf8"));
});

app.listen(PORT, HOST, () => {
  console.log(`API listening http://${HOST}:${PORT}`);
  console.log(`DATA_DIR=${DATA_DIR}`);
});
