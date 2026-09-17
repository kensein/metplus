"""Dashboard Verifikasi INanWP vs GSMAP - Main App."""

import streamlit as st

st.set_page_config(
    page_title="Verifikasi INanWP vs GSMAP",
    page_icon="🌧️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Dashboard Verifikasi Model INanWP")
st.caption("Verifikasi presipitasi menggunakan METplus GridStat | Observasi: GSMAP NRT")

st.markdown("""
### Selamat datang

Dashboard ini menampilkan hasil verifikasi model **INanWP** terhadap observasi satelit **GSMAP NRT**
menggunakan framework **METplus** (GridStat).

**Navigasi:**
- **Overview** — Ringkasan metrik verifikasi (RMSE, Bias, ACC, ETS)
- **Time Series** — Evolusi metrik per waktu valid
- **Threshold Analysis** — Analisis contingency table dan skill score per threshold

**Sumber data:** Output METplus dari server webpsi (`/mnt/wdd1/www/htdocs/wrf/metplus/dashboard/`)

**Periode data awal:**
- INanWP NC: 27 Juli 2026
- GSMAP NRT: 27–30 Juli 2026
""")

st.info(
    "Dashboard ini dirancang untuk deploy di server terpisah. "
    "Konfigurasi sumber data di `dashboard/.env` (lihat `config/dashboard.env.example`)."
)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Model", "INanWP")
with col2:
    st.metric("Observasi", "GSMAP NRT")
with col3:
    st.metric("Metode", "METplus GridStat")
