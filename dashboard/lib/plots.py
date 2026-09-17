"""Plotting utilities untuk dashboard verifikasi."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


COLORS = {
    "primary": "#1f77b4",
    "secondary": "#ff7f0e",
    "success": "#2ca02c",
    "danger": "#d62728",
}


def plot_rmse_timeseries(df: pd.DataFrame) -> go.Figure:
    """Plot RMSE over valid time."""
    cnt = df[df["line_type"] == "CNT"].copy()
    if cnt.empty:
        return go.Figure().add_annotation(text="Tidak ada data CNT", showarrow=False)

    cnt["valid_dt"] = pd.to_datetime(cnt["valid"], format="%Y%m%d_%H%M%S", errors="coerce")
    daily = cnt.groupby(cnt["valid_dt"].dt.date)["rmse"].mean().reset_index()
    daily.columns = ["date", "rmse"]

    fig = px.line(
        daily, x="date", y="rmse",
        title="RMSE Harian (mm)",
        markers=True,
        color_discrete_sequence=[COLORS["primary"]],
    )
    fig.update_layout(
        xaxis_title="Tanggal Valid",
        yaxis_title="RMSE (mm)",
        hovermode="x unified",
    )
    return fig


def plot_bias_timeseries(df: pd.DataFrame) -> go.Figure:
    """Plot Mean Error (bias) over valid time."""
    cnt = df[df["line_type"] == "CNT"].copy()
    if cnt.empty:
        return go.Figure().add_annotation(text="Tidak ada data CNT", showarrow=False)

    cnt["valid_dt"] = pd.to_datetime(cnt["valid"], format="%Y%m%d_%H%M%S", errors="coerce")
    daily = cnt.groupby(cnt["valid_dt"].dt.date)["me"].mean().reset_index()
    daily.columns = ["date", "me"]

    fig = px.bar(
        daily, x="date", y="me",
        title="Mean Error (Bias) Harian (mm)",
        color_discrete_sequence=[COLORS["secondary"]],
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(xaxis_title="Tanggal Valid", yaxis_title="ME (mm)")
    return fig


def plot_ets_by_threshold(df: pd.DataFrame) -> go.Figure:
    """Plot ETS by precipitation threshold."""
    cts = df[df["line_type"] == "CTS"].copy()
    if cts.empty:
        return go.Figure().add_annotation(text="Tidak ada data CTS", showarrow=False)

    agg = cts.groupby("fcst_thresh")["ets"].mean().reset_index()
    agg["threshold_mm"] = agg["fcst_thresh"].str.replace("gt", "").astype(float)

    fig = px.bar(
        agg, x="threshold_mm", y="ets",
        title="Equitable Threat Score (ETS) per Threshold",
        labels={"threshold_mm": "Threshold (mm)", "ets": "ETS"},
        color_discrete_sequence=[COLORS["success"]],
    )
    fig.update_layout(yaxis_range=[0, 1])
    return fig


def plot_contingency_table(df: pd.DataFrame, threshold: str = "gt5") -> go.Figure:
    """Plot contingency table as heatmap."""
    ctc = df[(df["line_type"] == "CTC") & (df["fcst_thresh"] == threshold)].copy()
    if ctc.empty:
        return go.Figure().add_annotation(
            text=f"Tidak ada data CTC untuk threshold {threshold}", showarrow=False
        )

    totals = {
        "Hit (FY_OY)": ctc["fy_oy"].sum(),
        "False Alarm (FY_ON)": ctc["fy_on"].sum(),
        "Miss (FN_OY)": ctc["fn_oy"].sum(),
        "Correct Neg (FN_ON)": ctc["fn_on"].sum(),
    }

    fig = go.Figure(data=go.Heatmap(
        z=[
            [totals["Hit (FY_OY)"], totals["False Alarm (FY_ON)"]],
            [totals["Miss (FN_OY)"], totals["Correct Neg (FN_ON)"]],
        ],
        x=["Obs Yes", "Obs No"],
        y=["Fcst Yes", "Fcst No"],
        text=[[f"{totals['Hit (FY_OY)']:.0f}", f"{totals['False Alarm (FY_ON)']:.0f}"],
              [f"{totals['Miss (FN_OY)']:.0f}", f"{totals['Correct Neg (FN_ON)']:.0f}"]],
        texttemplate="%{text}",
        textfont={"size": 16},
        colorscale="Blues",
        showscale=False,
    ))
    fig.update_layout(title=f"Contingency Table (threshold {threshold})")
    return fig


def plot_acc_timeseries(df: pd.DataFrame) -> go.Figure:
    """Plot Anomaly Correlation Coefficient over time."""
    cnt = df[df["line_type"] == "CNT"].copy()
    if cnt.empty or "acc" not in cnt.columns:
        return go.Figure().add_annotation(text="Tidak ada data ACC", showarrow=False)

    cnt["valid_dt"] = pd.to_datetime(cnt["valid"], format="%Y%m%d_%H%M%S", errors="coerce")
    daily = cnt.groupby(cnt["valid_dt"].dt.date)["acc"].mean().reset_index()
    daily.columns = ["date", "acc"]

    fig = px.line(
        daily, x="date", y="acc",
        title="Anomaly Correlation Coefficient (ACC) Harian",
        markers=True,
        color_discrete_sequence=[COLORS["success"]],
    )
    fig.update_layout(yaxis_range=[-1, 1], xaxis_title="Tanggal Valid", yaxis_title="ACC")
    return fig


def metric_cards(summary: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics for display cards."""
    overall = summary.get("metrics", {}).get("overall", {})
    return {
        "rmse": overall.get("rmse_mean"),
        "bias": overall.get("me_mean"),
        "acc": overall.get("acc_mean"),
        "n_records": overall.get("n_records", 0),
        "valid_times": len(summary.get("valid_times", [])),
    }
