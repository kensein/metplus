(function () {
  const API_BASE = "/verifikasi-inanwp/api";

  function $(id) { return document.getElementById(id); }

  function fmt(v, digits) {
    if (v === null || v === undefined || v === "") return "—";
    if (typeof v === "number") {
      if (Number.isInteger(v)) return String(v);
      return v.toFixed(digits == null ? 3 : digits);
    }
    return String(v);
  }

  function fmtBytes(n) {
    if (!n && n !== 0) return "—";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(2) + " MB";
  }

  async function getJson(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error(url + " → HTTP " + res.status);
    return res.json();
  }

  function renderMaps(maps) {
    const el = $("maps-gallery");
    if (!maps || !maps.length || !maps[0].images || !maps[0].images.length) {
      el.innerHTML = "<p class='muted'>Belum ada peta. Generate dari <code>*_pairs.nc</code> dengan <code>scripts/render_pairs_maps.py</code>.</p>";
      return;
    }
    const set = maps[0];
    const meta = set.meta || {};
    $("maps-caption").textContent =
      "Valid " + (meta.valid || set.valid_dir) +
      " · grid " + (meta.shape ? meta.shape.join("×") : "—") +
      " · sumber " + (meta.source_nc || "pairs.nc");
    el.innerHTML = set.images.map(function (img) {
      return (
        "<figure class='map-card'>" +
          "<figcaption>" + img.label + "</figcaption>" +
          "<a href='" + img.url + "' target='_blank' rel='noopener'>" +
            "<img src='" + img.url + "' alt='" + img.label + "' loading='lazy' />" +
          "</a>" +
        "</figure>"
      );
    }).join("");
  }

  function renderFiles(files) {
    const rows = [];
    (files.stat_files || []).forEach(function (f) {
      rows.push(
        "<tr>" +
          "<td><span class='tag'>.stat</span></td>" +
          "<td><code>" + f.name + "</code></td>" +
          "<td>" + f.valid_dir + "</td>" +
          "<td>" + fmtBytes(f.size_bytes) + "</td>" +
          "<td><a href='" + f.download_url + "'>Download</a></td>" +
        "</tr>"
      );
    });
    (files.pairs_files || []).forEach(function (f) {
      rows.push(
        "<tr>" +
          "<td><span class='tag tag-nc'>_pairs.nc</span></td>" +
          "<td><code>" + f.name + "</code></td>" +
          "<td>" + f.valid_dir + "</td>" +
          "<td>" + fmtBytes(f.size_bytes) + "</td>" +
          "<td><a href='" + f.download_url + "'>Download</a></td>" +
        "</tr>"
      );
    });
    $("files-table").innerHTML = rows.length
      ? rows.join("")
      : "<tr><td colspan='5' class='muted'>Belum ada file .stat / _pairs.nc di data/metplus/gridstat.</td></tr>";
  }

  function renderCnt(records) {
    const cnt = (records || []).filter(function (r) { return r.line_type === "CNT"; });
    $("cnt-table").innerHTML = cnt.length
      ? cnt.map(function (r) {
          return "<tr>" +
            "<td>" + fmt(r.total, 0) + "</td>" +
            "<td>" + fmt(r.fbar) + "</td>" +
            "<td>" + fmt(r.obar) + "</td>" +
            "<td>" + fmt(r.me) + "</td>" +
            "<td>" + fmt(r.mae) + "</td>" +
            "<td>" + fmt(r.rmse) + "</td>" +
            "<td>" + fmt(r.pr_corr) + "</td>" +
            "<td>" + fmt(r.mbias) + "</td>" +
          "</tr>";
        }).join("")
      : "<tr><td colspan='8' class='muted'>Tidak ada baris CNT.</td></tr>";
  }

  function renderCts(records) {
    const cts = (records || []).filter(function (r) { return r.line_type === "CTS"; });
    $("cts-table").innerHTML = cts.length
      ? cts.map(function (r) {
          return "<tr>" +
            "<td>" + (r.fcst_thresh || "NA") + "</td>" +
            "<td>" + fmt(r.total, 0) + "</td>" +
            "<td>" + fmt(r.acc) + "</td>" +
            "<td>" + fmt(r.fbias) + "</td>" +
            "<td>" + fmt(r.pod) + "</td>" +
            "<td>" + fmt(r.far) + "</td>" +
            "<td>" + fmt(r.csi) + "</td>" +
            "<td>" + fmt(r.ets) + "</td>" +
            "<td>" + fmt(r.hss) + "</td>" +
          "</tr>";
        }).join("")
      : "<tr><td colspan='9' class='muted'>Tidak ada baris CTS.</td></tr>";
  }

  function renderCtc(records) {
    const ctc = (records || []).filter(function (r) { return r.line_type === "CTC"; });
    $("ctc-table").innerHTML = ctc.length
      ? ctc.map(function (r) {
          return "<tr>" +
            "<td>" + (r.fcst_thresh || "NA") + "</td>" +
            "<td>" + fmt(r.fy_oy, 0) + "</td>" +
            "<td>" + fmt(r.fy_on, 0) + "</td>" +
            "<td>" + fmt(r.fn_oy, 0) + "</td>" +
            "<td>" + fmt(r.fn_on, 0) + "</td>" +
          "</tr>";
        }).join("")
      : "<tr><td colspan='5' class='muted'>Tidak ada baris CTC.</td></tr>";
  }

  async function load() {
    const statusEl = $("status");
    const errEl = $("error");
    try {
      const [summary, stats, files, raw] = await Promise.all([
        getJson(API_BASE + "/summary"),
        getJson(API_BASE + "/stats"),
        getJson(API_BASE + "/files"),
        fetch(API_BASE + "/stat-raw", { credentials: "same-origin" }).then(function (r) {
          return r.ok ? r.text() : Promise.reject(new Error("stat-raw " + r.status));
        }),
      ]);

      $("m-status").textContent = summary.status || "READY";
      $("m-updated").textContent = "Update: " + (summary.generated_at || "—");
      $("m-valid").textContent = summary.valid || "—";
      $("m-accum").textContent = summary.accum_hours ? (summary.accum_hours + " jam accum") : "—";
      $("m-pairs").textContent = fmt(summary.matched_pairs, 0);
      $("m-rmse").textContent = fmt(summary.metrics && summary.metrics.rmse);

      renderMaps(files.maps);
      renderFiles(files);
      renderCnt(stats.records);
      renderCts(stats.records);
      renderCtc(stats.records);
      $("stat-raw").textContent = raw;

      statusEl.textContent =
        "Data OK · " +
        (summary.n_stat_files || 0) + " .stat · " +
        (summary.n_pairs_files || 0) + " pairs.nc · " +
        (summary.n_map_sets || 0) + " set peta";
      errEl.hidden = true;
    } catch (e) {
      statusEl.textContent = "Gagal memuat API";
      errEl.hidden = false;
      errEl.textContent = String(e.message || e);
    }
  }

  load();
})();
