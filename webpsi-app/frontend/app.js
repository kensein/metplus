(function () {
  const API_BASE = "/verifikasi-inanwp/api";

  function $(id) { return document.getElementById(id); }

  function fmt(v) {
    if (v === null || v === undefined || v === "") return "—";
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
    return String(v);
  }

  async function getJson(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error(url + " → HTTP " + res.status);
    return res.json();
  }

  function row(label, value) {
    return "<tr><th style='width:38%'>" + label + "</th><td>" + value + "</td></tr>";
  }

  async function load() {
    const statusEl = $("status");
    const errEl = $("error");
    try {
      const [summary, stats] = await Promise.all([
        getJson(API_BASE + "/summary"),
        getJson(API_BASE + "/stats"),
      ]);

      $("m-status").textContent = summary.status || "READY";
      $("m-updated").textContent = "Update: " + (summary.generated_at || "—");
      $("m-valid").textContent = summary.valid || "—";
      $("m-accum").textContent = summary.accum_hours ? (summary.accum_hours + " jam accum") : "—";
      $("m-pairs").textContent = fmt(summary.matched_pairs);
      $("m-rmse").textContent = fmt(summary.metrics && summary.metrics.rmse);

      $("summary-table").innerHTML = [
        row("Model", summary.model),
        row("Observasi", summary.observation),
        row("Valid", summary.valid),
        row("Accum", summary.accum_hours ? summary.accum_hours + " jam" : "—"),
        row("Matched pairs", fmt(summary.matched_pairs)),
        row("STAT files", fmt(summary.n_stat_files)),
        row("Catatan", summary.note || "—"),
      ].join("");

      const prefer = (stats.records || []).filter((r) => r.line_type === "CTS" || r.line_type === "CTC");
      const rows = prefer.slice(0, 40).map((r) => {
        return "<tr>" +
          "<td>" + r.line_type + "</td>" +
          "<td>" + (r.fcst_thresh || "NA") + "</td>" +
          "<td>" + fmt(r.total) + "</td>" +
          "<td>" + fmt(r.acc) + "</td>" +
          "<td>" + (r.source_file || "") + "</td>" +
          "</tr>";
      });
      $("stats-table").innerHTML = rows.length
        ? rows.join("")
        : "<tr><td colspan='5' class='muted'>Belum ada baris CTS/CTC. Pastikan data METplus sudah di-sync.</td></tr>";

      statusEl.textContent = "Data API OK · " + API_BASE;
      errEl.hidden = true;
    } catch (e) {
      statusEl.textContent = "Gagal memuat API";
      errEl.hidden = false;
      errEl.textContent = String(e.message || e);
    }
  }

  load();
})();
