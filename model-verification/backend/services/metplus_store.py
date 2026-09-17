"""Read METplus GridStat / series artifacts into Monas-compatible score shapes.

Layout expected (METPLUS_DATA_DIR, default data/metplus):

    dashboard/series.json          # points[] lead_hours, rmse, me, mae, csi_0.1, ...
    dashboard/series_<init>.json
    dashboard/summary.json
    gridstat/<YYYYMMDDHH>/...      # .stat / .txt / pairs
    maps/<YYYYMMDDHH>/{fcst,obs,diff}.png

Multi-model extension (optional):

    models/<ModelName>/dashboard/series.json
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


def metplus_root() -> Path:
    return Path(os.getenv("METPLUS_DATA_DIR", "data/metplus")).expanduser()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_model_dirs() -> dict[str, Path]:
    """Map model name -> dashboard dir containing series.json."""
    root = metplus_root()
    found: dict[str, Path] = {}
    models_root = root / "models"
    if models_root.is_dir():
        for child in sorted(models_root.iterdir()):
            dash = child / "dashboard"
            if (dash / "series.json").is_file() or (dash / "summary.json").is_file():
                found[child.name] = dash
    # Default / legacy: flat dashboard = InaNWP
    flat = root / "dashboard"
    if (flat / "series.json").is_file() or (flat / "summary.json").is_file():
        found.setdefault("InaNWP", flat)
    return found


def load_series(model: str = "InaNWP", init: str | None = None) -> dict[str, Any] | None:
    dirs = list_model_dirs()
    dash = dirs.get(model)
    if not dash:
        return None
    if init:
        data = _read_json(dash / f"series_{init}.json")
        if data:
            return data
    return _read_json(dash / "series.json")


def available_models() -> dict[str, str]:
    present = set(list_model_dirs())
    return {m: ("real" if m in present else "none") for m in MODELS}


def scores_frame(
    models: list[str] | None = None,
    parameter: str | None = None,
    init_time: str | None = None,
    lead_time: int | None = None,
) -> pd.DataFrame:
    """Normalize series.json points → rows like HARP scores_frame."""
    if parameter and parameter not in (METPLUS_PARAM, "precip", "rainfall_6h_rrr"):
        # Only precip family supported for METplus path in v1
        return pd.DataFrame()
    want = models or list(MODELS)
    init_tag = None
    if init_time:
        init_tag = str(init_time).replace("-", "").replace("T", "").replace(":", "").replace("Z", "")[:10]
        if len(init_tag) > 10:
            init_tag = init_tag[:10]

    rows: list[dict[str, Any]] = []
    for model in want:
        series = load_series(model, init_tag)
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
            rows.append({
                "model": model,
                "parameter": METPLUS_PARAM,
                "init_time": init,
                "lead_time": lt,
                "bias": me,
                "rmse": rmse,
                "mae": mae,
                "stde": None,
                "correlation": p.get("pr_corr"),
                "csi": p.get("csi_0.1") or p.get("csi_0_1"),
                "ets": p.get("ets_0.1") or p.get("ets_0_1"),
                "pod": p.get("pod_0.1") or p.get("pod_0_1"),
                "far": p.get("far_0.1") or p.get("far_0_1"),
                "n_cases": int(p.get("matched_pairs") or series.get("n_points") or 0),
                "n_stations": 0,
                "computed_at": series.get("generated_at"),
                "valid": p.get("valid"),
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["lead_time", "model"]).reset_index(drop=True)


def ranking_payload(models: list[str], init_time: str | None, score: str = "rmse") -> dict[str, Any]:
    df = scores_frame(models=models, init_time=init_time)
    if df.empty:
        return {}
    metric = score if score in df.columns else "rmse"
    # mean over leads (lower better for rmse/mae/bias abs; higher better for csi/ets/corr)
    higher_better = metric in ("correlation", "csi", "ets", "pod")
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
    return {"score_metric": metric, "init_time": init_time, "method": "metplus", "ranking": ranking}


def spatial_maps(model: str = "InaNWP", valid: str | None = None) -> dict[str, Any]:
    """List PNG maps for a valid time (METplus pairs maps)."""
    root = metplus_root()
    # Prefer model-scoped maps, else flat
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


def cycles(model: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for m, dash in list_model_dirs().items():
        if model and m != model:
            continue
        series = _read_json(dash / "series.json") or {}
        init = series.get("init")
        rows.append({
            "model": m,
            "init_time": init,
            "n_points": series.get("n_points"),
            "precip_source": series.get("precip_source"),
            "generated_at": series.get("generated_at"),
            "method": "metplus",
        })
        # also list series_*.json
        for p in sorted(dash.glob("series_*.json")):
            tag = p.stem.replace("series_", "")
            if tag == init:
                continue
            data = _read_json(p) or {}
            rows.append({
                "model": m,
                "init_time": data.get("init") or tag,
                "n_points": data.get("n_points"),
                "method": "metplus",
            })
    return rows
