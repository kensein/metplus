"""Overview page - ringkasan metrik verifikasi."""

import streamlit as st
import pandas as pd

from lib.data_loader import load_summary, load_stats, get_last_updated, get_config
from lib.plots import metric_cards, plot_ets_by_threshold, plot_contingency_table

st.set_page_config(page_title="Overview", layout="wide")
st.title("Overview Verifikasi")

cfg = get_config()
summary = load_summary()
stats_df = load_stats()

if not summary:
    st.warning(
        "Data belum tersedia. Pastikan output METplus sudah di-export ke dashboard "
        "(jalankan `scripts/export_dashboard_data.py` di server webpsi)."
    )
    st.stop()

cards = metric_cards(summary)
last_updated = get_last_updated()

st.caption(f"Terakhir diperbarui: {last_updated}")

# Metric cards
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("RMSE (mm)", f"{cards['rmse']:.2f}" if cards["rmse"] else "N/A")
with c2:
    st.metric("Bias / ME (mm)", f"{cards['bias']:.2f}" if cards["bias"] else "N/A")
with c3:
    st.metric("ACC", f"{cards['acc']:.3f}" if cards["acc"] else "N/A")
with c4:
    st.metric("Jam Valid", cards["valid_times"])
with c5:
    st.metric("Total Records", cards["n_records"])

st.divider()

# Daily summary table
daily = summary.get("metrics", {}).get("daily", {})
if daily:
    st.subheader("Ringkasan Harian")
    daily_df = pd.DataFrame.from_dict(daily, orient="index")
    daily_df.index.name = "Tanggal"
    daily_df = daily_df.reset_index()
    daily_df["Tanggal"] = pd.to_datetime(daily_df["Tanggal"], format="%Y%m%d").dt.strftime("%d %b %Y")
    st.dataframe(daily_df, use_container_width=True, hide_index=True)

st.divider()

# Charts
if not stats_df.empty:
    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(plot_ets_by_threshold(stats_df), use_container_width=True)
    with col_right:
        threshold = st.selectbox(
            "Threshold contingency table",
            options=sorted(stats_df[stats_df["line_type"] == "CTC"]["fcst_thresh"].unique()),
            index=2 if len(stats_df) > 0 else 0,
        )
        st.plotly_chart(
            plot_contingency_table(stats_df, threshold=threshold),
            use_container_width=True,
        )

# Info panel
with st.expander("Informasi Verifikasi"):
    st.markdown(f"""
    | Parameter | Nilai |
    |-----------|-------|
    | Model | {cfg['model']} |
    | Observasi | {cfg['observation']} |
    | Domain | {cfg['domain']} |
    | METplus Tool | GridStat |
    | Statistik | CNT, CTS, CTC, SL1L2, NBR* |
    | Threshold | 0.1, 1, 5, 10, 20, 50 mm |
    """)
