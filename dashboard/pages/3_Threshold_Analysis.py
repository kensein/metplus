"""Threshold analysis page."""

import streamlit as st
import pandas as pd
import plotly.express as px

from lib.data_loader import load_stats, get_last_updated

st.set_page_config(page_title="Threshold Analysis", layout="wide")
st.title("Analisis Threshold Presipitasi")

stats_df = load_stats()
st.caption(f"Terakhir diperbarui: {get_last_updated()}")

if stats_df.empty:
    st.warning("Data statistik belum tersedia.")
    st.stop()

cts = stats_df[stats_df["line_type"] == "CTS"].copy()
ctc = stats_df[stats_df["line_type"] == "CTC"].copy()

if cts.empty:
    st.warning("Tidak ada data CTS (categorical statistics).")
    st.stop()

# Threshold selection
thresholds = sorted(cts["fcst_thresh"].unique())
selected = st.multiselect("Pilih threshold (mm)", thresholds, default=thresholds[:3])

if not selected:
    st.info("Pilih minimal satu threshold.")
    st.stop()

filtered = cts[cts["fcst_thresh"].isin(selected)]

# Skill scores by threshold
metrics = ["ets", "bias", "csi", "far", "hss"]
metric = st.selectbox("Metrik kategorikal", metrics, index=0)

agg = filtered.groupby("fcst_thresh")[metric].mean().reset_index()
agg["threshold_mm"] = agg["fcst_thresh"].str.replace("gt", "").astype(float)

fig = px.bar(
    agg, x="threshold_mm", y=metric,
    title=f"{metric.upper()} per Threshold Presipitasi",
    labels={"threshold_mm": "Threshold (mm)", metric: metric.upper()},
    color="fcst_thresh",
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# Detailed table
st.subheader("Detail Statistik Kategorikal")
display_cols = ["valid", "fcst_thresh", "ets", "bias", "csi", "far", "hss", "acc"]
available = [c for c in display_cols if c in filtered.columns]
st.dataframe(
    filtered[available].sort_values(["fcst_thresh", "valid"]),
    use_container_width=True,
    hide_index=True,
)

# Contingency breakdown
if not ctc.empty:
    st.divider()
    st.subheader("Contingency Table (Agregat)")
    for thresh in selected:
        sub = ctc[ctc["fcst_thresh"] == thresh]
        if sub.empty:
            continue
        st.markdown(f"**Threshold: {thresh}**")
        totals = pd.DataFrame({
            "Kategori": ["Hit (FY_OY)", "False Alarm (FY_ON)", "Miss (FN_OY)", "Correct Neg (FN_ON)"],
            "Jumlah": [sub["fy_oy"].sum(), sub["fy_on"].sum(), sub["fn_oy"].sum(), sub["fn_on"].sum()],
        })
        st.dataframe(totals, use_container_width=True, hide_index=True)
