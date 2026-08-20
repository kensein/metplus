"""Time series page - evolusi metrik per waktu valid."""

import streamlit as st

from lib.data_loader import load_stats, get_last_updated
from lib.plots import plot_rmse_timeseries, plot_bias_timeseries, plot_acc_timeseries

st.set_page_config(page_title="Time Series", layout="wide")
st.title("Time Series Metrik Verifikasi")

stats_df = load_stats()
st.caption(f"Terakhir diperbarui: {get_last_updated()}")

if stats_df.empty:
    st.warning("Data statistik belum tersedia.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["RMSE", "Bias (ME)", "ACC"])

with tab1:
    st.plotly_chart(plot_rmse_timeseries(stats_df), use_container_width=True)
    st.markdown("""
    **RMSE (Root Mean Square Error)** — mengukur magnitude error rata-rata.
    Nilai lebih kecil = verifikasi lebih baik.
    """)

with tab2:
    st.plotly_chart(plot_bias_timeseries(stats_df), use_container_width=True)
    st.markdown("""
    **ME (Mean Error / Bias)** — selisih rata-rata model vs observasi.
    Nilai positif = model over-estimate, negatif = under-estimate.
    """)

with tab3:
    st.plotly_chart(plot_acc_timeseries(stats_df), use_container_width=True)
    st.markdown("""
    **ACC (Anomaly Correlation Coefficient)** — korelasi pola spasial anomali.
    Nilai mendekati 1 = pola spasial sangat sesuai.
    """)
