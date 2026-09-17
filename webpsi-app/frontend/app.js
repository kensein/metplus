(function () {
  const API_BASE = "/verifikasi-inanwp/api";

  const MAP_ORDER = ["fcst.png", "obs.png", "diff.png"];
  const MAP_META = {
    "fcst.png": {
      label: "Prakiraan (FCST)",
      blurb: "Keluaran model InaNWP: akumulasi curah hujan 3 jam hingga waktu valid.",
    },
    "obs.png": {
      label: "Observasi (OBS)",
      blurb: "Estimasi hujan satelit GSMAP pada interval 3 jam yang sama.",
    },
    "diff.png": {
      label: "Selisih (DIFF)",
      blurb: "Prakiraan dikurangi observasi. Merah: model lebih basah; biru: model lebih kering.",
    },
  };

  let currentRun = null;

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

  function describeValid(validRaw, accumHours) {
    const raw = String(validRaw || "");
    const m = raw.match(/^(\d{4})(\d{2})(\d{2})[_ ]?(\d{2})Z?$/i);
    const hours = accumHours || 3;
    if (!m) {
      return { label: raw || "—", windowText: hours + " jam akumulasi" };
    }
    const y = m[1], mo = m[2], d = m[3], hh = parseInt(m[4], 10);
    const end = new Date(Date.UTC(+y, +mo - 1, +d, hh, 0, 0));
    const start = new Date(end.getTime() - hours * 3600 * 1000);
    function stamp(dt) {
      const dd = String(dt.getUTCDate()).padStart(2, "0");
      const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
      const yy = dt.getUTCFullYear();
      const h = String(dt.getUTCHours()).padStart(2, "0");
      return dd + "/" + mm + "/" + yy + " " + h + ".00 UTC";
    }
    return {
      label: stamp(end),
      windowText: "Akumulasi " + hours + " jam: " + stamp(start) + " sampai " + stamp(end),
    };
  }

  function runLabel(run) {
    const info = describeValid(run.valid || run.run, 3);
    return info.label + " (" + run.run + ")";
  }

  async function getJson(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error(url + " → HTTP " + res.status);
    return res.json();
  }

  function q(run) {
    return run ? ("?run=" + encodeURIComponent(run)) : "";
  }

  function sortImages(images) {
    return (images || []).slice().sort(function (a, b) {
      const ia = MAP_ORDER.indexOf(a.name);
      const ib = MAP_ORDER.indexOf(b.name);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  }

  function fillRunSelect(runsPayload) {
    const sel = $("run-select");
    const runs = runsPayload.runs || [];
    sel.innerHTML = runs.map(function (r) {
      return "<option value='" + r.run + "'" +
        (r.run === currentRun ? " selected" : "") +
        ">" + runLabel(r) + "</option>";
    }).join("");
    $("run-count").textContent = runs.length
      ? (runs.length + " run tersimpan" + (runsPayload.auto_update ? " · otomasi push DPU aktif" : " · otomasi belum aktif"))
      : "Belum ada run";
  }

  function renderRunsTable(runsPayload) {
    const runs = runsPayload.runs || [];
    $("runs-table").innerHTML = runs.length
      ? runs.map(function (r) {
          const info = describeValid(r.valid || r.run, 3);
          const active = r.run === currentRun ? " class='runs-table-active'" : "";
          return "<tr" + active + ">" +
            "<td><button type='button' class='linkish' data-run='" + r.run + "'>" + info.label + "</button><div class='muted'>" + r.run + "</div></td>" +
            "<td>" + (r.status || "—") + "</td>" +
            "<td>" + fmt(r.matched_pairs, 0) + "</td>" +
            "<td>" + fmt(r.rmse) + "</td>" +
            "<td>" + fmt(r.me) + "</td>" +
            "<td>" +
              (r.has_stat ? "skor " : "") +
              (r.has_pairs ? "pairs " : "") +
              (r.has_maps ? "peta" : "") +
            "</td>" +
          "</tr>";
        }).join("")
      : "<tr><td colspan='6' class='muted'>Belum ada histori. Jalankan METplus di DPU lalu sync ke webpsi.</td></tr>";

    $("runs-table").querySelectorAll("button[data-run]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        selectRun(btn.getAttribute("data-run"));
      });
    });
  }

  function renderMaps(maps, summary) {
    const el = $("maps-gallery");
    const explain = $("maps-explain");
    if (!maps || !maps.length || !maps[0].images || !maps[0].images.length) {
      el.innerHTML = "<p class='muted'>Belum ada peta untuk run ini.</p>";
      explain.innerHTML = "";
      return;
    }
    const set = maps[0];
    const meta = set.meta || {};
    const validInfo = describeValid(meta.valid || summary.valid || set.valid_dir, summary.accum_hours || 3);
    $("maps-caption").textContent =
      validInfo.windowText +
      " · grid " + (meta.shape ? meta.shape.join("×") : "—") +
      " · sumber " + (meta.source_nc || "pairs.nc");

    explain.innerHTML =
      "<ul>" +
        "<li><strong>Prakiraan (FCST)</strong>: keluaran model InaNWP untuk akumulasi hujan 3 jam hingga waktu valid di atas.</li>" +
        "<li><strong>Observasi (OBS)</strong>: estimasi hujan satelit GSMAP pada periode yang sama.</li>" +
        "<li><strong>Selisih (DIFF)</strong>: FCST dikurangi OBS (mm). Nilai positif berarti prakiraan lebih basah; negatif berarti lebih kering.</li>" +
      "</ul>";

    el.innerHTML = sortImages(set.images).map(function (img) {
      const info = MAP_META[img.name] || { label: img.label, blurb: "" };
      return (
        "<figure class='map-card'>" +
          "<figcaption>" +
            "<strong>" + info.label + "</strong>" +
            (info.blurb ? "<span>" + info.blurb + "</span>" : "") +
          "</figcaption>" +
          "<a href='" + img.url + "' target='_blank' rel='noopener'>" +
            "<img src='" + img.url + "' alt='" + info.label + "' loading='lazy' />" +
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
          "<td><span class='tag'>statistik</span></td>" +
          "<td><code>" + f.name + "</code></td>" +
          "<td>" + f.valid_dir + "</td>" +
          "<td>" + fmtBytes(f.size_bytes) + "</td>" +
          "<td><a href='" + f.download_url + "'>Unduh</a></td>" +
        "</tr>"
      );
    });
    (files.pairs_files || []).forEach(function (f) {
      rows.push(
        "<tr>" +
          "<td><span class='tag tag-nc'>pasangan grid</span></td>" +
          "<td><code>" + f.name + "</code></td>" +
          "<td>" + f.valid_dir + "</td>" +
          "<td>" + fmtBytes(f.size_bytes) + "</td>" +
          "<td><a href='" + f.download_url + "'>Unduh</a></td>" +
        "</tr>"
      );
    });
    $("files-table").innerHTML = rows.length
      ? rows.join("")
      : "<tr><td colspan='5' class='muted'>Tidak ada file untuk run ini.</td></tr>";
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

  async function loadRun(run) {
    const statusEl = $("status");
    const errEl = $("error");
    try {
      const [summary, stats, files, runsPayload, raw] = await Promise.all([
        getJson(API_BASE + "/summary" + q(run)),
        getJson(API_BASE + "/stats" + q(run)),
        getJson(API_BASE + "/files" + q(run)),
        getJson(API_BASE + "/runs"),
        fetch(API_BASE + "/stat-raw" + q(run), { credentials: "same-origin" }).then(function (r) {
          return r.ok ? r.text() : Promise.reject(new Error("stat-raw " + r.status));
        }),
      ]);

      currentRun = summary.run || run || runsPayload.latest;
      fillRunSelect(runsPayload);
      renderRunsTable(runsPayload);

      const validInfo = describeValid(summary.valid, summary.accum_hours || 3);
      $("m-status").textContent = summary.status || "READY";
      $("m-updated").textContent = "Diperbarui: " + (summary.generated_at || "—");
      $("m-valid").textContent = validInfo.label;
      $("m-accum").textContent = validInfo.windowText;
      $("m-pairs").textContent = fmt(summary.matched_pairs, 0);
      $("m-rmse").textContent = fmt(summary.metrics && summary.metrics.rmse);

      renderMaps(files.maps, summary);
      renderFiles(files);
      renderCnt(stats.records);
      renderCts(stats.records);
      renderCtc(stats.records);
      $("stat-raw").textContent = raw;

      statusEl.textContent =
        "Run " + (currentRun || "—") +
        " · " + (summary.n_stat_files || 0) + " file skor · " +
        (summary.n_pairs_files || 0) + " file pasangan grid · " +
        (runsPayload.count || 0) + " run histori";
      errEl.hidden = true;
    } catch (e) {
      statusEl.textContent = "Gagal memuat API";
      errEl.hidden = false;
      errEl.textContent = String(e.message || e);
    }
  }

  function selectRun(run) {
    currentRun = run;
    const sel = $("run-select");
    if (sel) sel.value = run;
    loadRun(run);
  }

  $("run-select").addEventListener("change", function () {
    selectRun($("run-select").value);
  });

  loadRun(null);
})();
