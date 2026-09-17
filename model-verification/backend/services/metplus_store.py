"""Read METplus GridStat / PointStat / FSS / MODE artifacts into Monas-compatible score shapes.

Layout expected (METPLUS_DATA_DIR, default data/metplus):

    dashboard/series.json            # GridStat (metplus)
    dashboard/series_point.json      # PointStat (metplus_point)
    dashboard/series_fss.json        # FSS neighborhood (metplus_fss)
    dashboard/series_mode.json       # MODE objects (metplus_mode)
    dashboard/series_<init>.json
    gridstat|pointstat|fss|mode/<YYYYMMDDHH>/...
    maps/<YYYYMMDDHH>/{fcst,obs,diff}.png
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from backend.config import MODELS

METPLUS_PARAM = "precip_3h"
METPLUS_PARAM_META = {
    "label": "Curah hujan 3 jam (RAINNC+RAINC+RAINSH)",
    "unit": "mm",
    "category": "continuous",
}

METHOD_SERIES = {
    "metplus": "series.json",
    "metplus_point": "series_point.json",
    "metplus_fss": "series_fss.json",
    "metplus_mode": "series_mode.json",
}

METHOD_SERIES_PREFIX = {
    "metplus": "series",
    "metplus_point": "series_point",
    "metplus_fss": "series_fss",
    "metplus_mode": "series_mode",
}


def metplus_root() -> Path:
    return Path(os.getenv("METPLUS_DATA_DIR", "data/metplus")).expanduser()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def normalize_method(method: str | None) -> str:
    m = (method or "metplus").strip().lower()
    if m in METHOD_SERIES:
        return m
    if m in ("metplus_grid", "grid", "gridstat", "spatial"):
        return "metplus"
    if m in ("point", "pointstat", "metplus-point"):
        return "metplus_point"
    if m in ("fss", "neighborhood"):
        return "metplus_fss"
    if m in ("mode", "object"):
        return "metplus_mode"
    return "metplus"


def list_model_dirs() -> dict[str, Path]:
    """Map model name -> dashboard dir containing series*.json."""
    root = metplus_root()
    found: dict[str, Path] = {}
    models_root = root / "models"
    if models_root.is_dir():
        for child in sorted(models_root.iterdir()):
            dash = child / "dashboard"
            if any((dash / name).is_file() for name in METHOD_SERIES.values()):
                found[child.name] = dash
            elif (dash / "summary.json").is_file():
                found[child.name] = dash
    flat = root / "dashboard"
    if any((flat / name).is_file() for name in METHOD_SERIES.values()) or (flat / "summary.json").is_file():
        found.setdefault("InaNWP", flat)
    return found


def load_series(model: str = "InaNWP", init: str | None = None, method: str = "metplus") -> dict[str, Any] | None:
    dirs = list_model_dirs()
    dash = dirs.get(model)
    if not dash:
        return None
    method = normalize_method(method)
    prefix = METHOD_SERIES_PREFIX[method]
    if init:
        data = _read_json(dash / f"{prefix}_{init}.json")
        if data:
            return data
    return _read_json(dash / f"{prefix}.json")


def available_models(method: str = "metplus") -> dict[str, str]:
    method = normalize_method(method)
    present: set[str] = set()
    for m, dash in list_model_dirs().items():
        prefix = METHOD_SERIES_PREFIX[method]
        if (dash / f"{prefix}.json").is_file() or list(dash.glob(f"{prefix}_*.json")):
            present.add(m)
    return {m: ("real" if m in present else "none") for m in MODELS}


def scores_frame(
    models: list[str] | None = None,
    parameter: str | None = None,
    init_time: str | None = None,
    lead_time: int | None = None,
    method: str = "metplus",
) -> pd.DataFrame:
    """Normalize series*.json points → rows like HARP scores_frame."""
    if parameter and parameter not in (METPLUS_PARAM, "precip", "rainfall_6h_rrr", "rainfall_last_mm"):
        return pd.DataFrame()
    want = models or list(MODELS)
    method = normalize_method(method)
    init_tag = None
    if init_time:
        init_tag = str(init_time).replace("-", "").replace("T", "").replace(":", "").replace("Z", "")[:10]
        if len(init_tag) > 10:
            init_tag = init_tag[:10]

    rows: list[dict[str, Any]] = []
    for model in want:
        series = load_series(model, init_tag, method=method)
        if not series:
            continue
        init = series.get("init") or init_tag
        for p in series.get("points") or []:
            lt = int(p.get("lead_hours") or p.get("lead_time") or 0)
            if lead_time is not None and lt != int(lead_time):
                continue
            rmse = p.get("rmse")
            me = p.get("me")
            mae = p.get("mae")
            fss = p.get("fss") or p.get("fss_1.0")
            # For FSS method, surface FSS as primary "score" and also as correlation-like field
            if method == "metplus_fss" and rmse is None and fss is not None:
                # keep rmse empty; UI can select csi/ets/fss via metric mapping
                pass
            rows.append({
                "model": model,
                "parameter": METPLUS_PARAM,
                "init_time": init,
                "lead_time": lt,
                "bias": me,
                "rmse": rmse if rmse is not None else fss,
                "mae": mae if mae is not None else p.get("total_interest"),
                "stde": None,
                "correlation": p.get("pr_corr") if p.get("pr_corr") is not None else fss,
                "csi": p.get("csi_0.1") or p.get("csi_0_1") or fss,
                "ets": p.get("ets_0.1") or p.get("ets_0_1") or p.get("total_interest"),
                "pod": p.get("pod_0.1") or p.get("pod_0_1"),
                "far": p.get("far_0.1") or p.get("far_0_1"),
                "fss": fss,
                "total_interest": p.get("total_interest"),
                "n_cases": int(p.get("matched_pairs") or p.get("n_matched") or series.get("n_points") or 0),
                "n_stations": int(p.get("n_stations") or (167 if method == "metplus_point" else 0)),
                "computed_at": series.get("generated_at"),
                "valid": p.get("valid"),
                "method": method,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["lead_time", "model"]).reset_index(drop=True)


def ranking_payload(models: list[str], init_time: str | None, score: str = "rmse", method: str = "metplus") -> dict[str, Any]:
    method = normalize_method(method)
    df = scores_frame(models=models, init_time=init_time, method=method)
    if df.empty:
        return {}
    # Prefer method-specific default metric
    if method == "metplus_fss" and score == "rmse":
        score = "fss" if "fss" in df.columns and df["fss"].notna().any() else "csi"
    if method == "metplus_mode" and score == "rmse":
        score = "ets" if "ets" in df.columns and df["ets"].notna().any() else "mae"
    metric = score if score in df.columns else "rmse"
    if metric not in df.columns:
        return {}
    higher_better = metric in ("correlation", "csi", "ets", "pod", "fss", "total_interest")
    ranking = []
    for model, g in df.groupby("model"):
        vals = pd.to_numeric(g[metric], errors="coerce").dropna()
        if vals.empty:
            continue
        mean_v = float(vals.mean())
        ranking.append({
            "model": model,
            "mean_rmse": float(pd.to_numeric(g["rmse"], errors="coerce").mean()) if "rmse" in g else None,
            "mean_score": mean_v,
            "score": mean_v,
            "n_leads": int(len(g)),
            "metric": metric,
        })
    ranking.sort(key=lambda r: (r["mean_score"] is None, -(r["mean_score"] or 0) if higher_better else (r["mean_score"] or 0)))
    for i, r in enumerate(ranking, 1):
        r["rank"] = i
    return {"score_metric": metric, "init_time": init_time, "method": method, "ranking": ranking}


def spatial_maps(model: str = "InaNWP", valid: str | None = None) -> dict[str, Any]:
    root = metplus_root()
    map_roots = []
    model_maps = root / "models" / model / "maps"
    if model_maps.is_dir():
        map_roots.append(model_maps)
    flat = root / "maps"
    if flat.is_dir():
        map_roots.append(flat)

    out = []
    for mr in map_roots:
        for d in sorted(mr.iterdir()):
            if not d.is_dir():
                continue
            if valid and d.name != valid and not d.name.startswith(str(valid)[:8]):
                continue
            files = {}
            for name in ("fcst.png", "obs.png", "diff.png", "meta.json"):
                p = d / name
                if p.is_file():
                    files[name] = f"maps/{d.name}/{name}"
            if files:
                out.append({"valid": d.name, "files": files, "model": model})
    return {"model": model, "maps": out, "method": "metplus"}


def cycles(model: str | None = None, method: str = "metplus") -> list[dict[str, Any]]:
    method = normalize_method(method)
    prefix = METHOD_SERIES_PREFIX[method]
    rows = []
    for m, dash in list_model_dirs().items():
        if model and m != model:
            continue
        series = _read_json(dash / f"{prefix}.json") or {}
        init = series.get("init")
        if series:
            rows.append({
                "model": m,
                "init_time": init,
                "n_points": series.get("n_points"),
                "precip_source": series.get("precip_source"),
                "generated_at": series.get("generated_at"),
                "method": method,
            })
        for p in sorted(dash.glob(f"{prefix}_*.json")):
            tag = p.stem.replace(f"{prefix}_", "")
            if tag == init:
                continue
            data = _read_json(p) or {}
            rows.append({
                "model": m,
                "init_time": data.get("init") or tag,
                "n_points": data.get("n_points"),
                "method": method,
            })
    return rows
