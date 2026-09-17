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
    "label": "3-hour precipitation (RAINNC+RAINC+RAINSH)",
    "unit": "mm",
    "category": "continuous",
}

# PointStat Soft multi-param — HARP Soft ids that wrfout surface can verify
POINTSTAT_PARAMS = [
    "temp_drybulb_c_tttttt",
    "temp_dewpoint_c_tdtdtd",
    "relative_humidity_pc",
    "pressure_qff_mb_derived",
    "pressure_qfe_mb_derived",
    "wind_speed_ff",
    "wind_dir_deg_dd",
    "rainfall_last_mm",
]

POINTSTAT_PARAM_ALIASES = {
    "precip_3h": "rainfall_last_mm",
    "precip": "rainfall_last_mm",
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
    method = normalize_method(method)
    # PointStat: keep HARP Soft param ids; GridStat/FSS/MODE: precip_3h only
    if method == "metplus_point":
        param = POINTSTAT_PARAM_ALIASES.get(parameter or "", parameter) or None
        if param and param not in POINTSTAT_PARAMS and param != METPLUS_PARAM:
            # unknown → empty (jangan coerce ke hujan)
            return pd.DataFrame()
        if param == METPLUS_PARAM:
            param = "rainfall_last_mm"
    else:
        param = METPLUS_PARAM
        if parameter and parameter not in (METPLUS_PARAM, "precip", "rainfall_6h_rrr", "rainfall_last_mm", None, ""):
            parameter = METPLUS_PARAM

    want = models or list(MODELS)
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
            row_param = p.get("parameter") or METPLUS_PARAM
            if row_param == "precip":
                row_param = "rainfall_last_mm"
            if method == "metplus_point":
                if param and row_param != param:
                    continue
                out_param = row_param
            else:
                out_param = METPLUS_PARAM
            rmse = p.get("rmse")
            me = p.get("me")
            mae = p.get("mae")
            fss = p.get("fss") or p.get("fss_1.0")
            if method == "metplus_fss" and rmse is None and fss is not None:
                pass
            rows.append({
                "model": model,
                "parameter": out_param,
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


def ranking_payload(models: list[str], init_time: str | None, score: str = "rmse", method: str = "metplus", parameter: str | None = None) -> dict[str, Any]:
    method = normalize_method(method)
    df = scores_frame(models=models, init_time=init_time, method=method, parameter=parameter)
    if df.empty:
        return {}
    # Prefer method-specific default metric
    if method == "metplus_fss" and score == "rmse":
        score = "fss" if "fss" in df.columns and df["fss"].notna().any() else "csi"
    if method == "metplus_mode" and score in ("rmse", "ets"):
        if "total_interest" in df.columns and df["total_interest"].notna().any():
            score = "total_interest"
        elif "mae" in df.columns and df["mae"].notna().any():
            score = "mae"
        else:
            score = "ets"
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
            "parameter": parameter or (g["parameter"].iloc[0] if "parameter" in g.columns else None),
        })
    ranking.sort(key=lambda r: (r["mean_score"] is None, -(r["mean_score"] or 0) if higher_better else (r["mean_score"] or 0)))
    for i, r in enumerate(ranking, 1):
        r["rank"] = i
    return {"score_metric": metric, "init_time": init_time, "method": method, "parameter": parameter, "ranking": ranking}


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


def _parse_valid_iso(yyyymmdd_hhmmss: str) -> str | None:
    s = str(yyyymmdd_hhmmss or "").strip()
    if len(s) >= 15 and "_" in s:
        d, t = s.split("_", 1)
        if len(d) == 8 and len(t) >= 6:
            return f"{d[0:4]}-{d[4:6]}-{d[6:8]}T{t[0:2]}:{t[2:4]}:{t[4:6]}Z"
    if len(s) == 10 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:00:00Z"
    return None


def station_point_series(station_id: str, model: str = "InaNWP", parameter: str | None = None) -> dict[str, Any]:
    """Baca MPR PointStat untuk satu stasiun → obs + satu init series (fcst per lead)."""
    root = metplus_root()
    pt_roots = [root / "models" / model / "pointstat", root / "pointstat"]
    sid = str(station_id).strip()
    want = POINTSTAT_PARAM_ALIASES.get(parameter or "", parameter) if parameter else None
    if want == METPLUS_PARAM:
        want = "rainfall_last_mm"
    by_init: dict[str, list[dict[str, Any]]] = {}
    obs_by_valid: dict[str, float] = {}

    for pt_root in pt_roots:
        if not pt_root.is_dir():
            continue
        found_any = False
        for run_dir in sorted(pt_root.glob("*")):
            if not run_dir.is_dir():
                continue
            meta = _read_json(run_dir / "run_meta.json") or {}
            init = str(meta.get("init") or "")
            lead = meta.get("lead_hours")
            valid_tag = meta.get("valid_yyyymmddhh") or run_dir.name
            stat_files = sorted(run_dir.glob("*.stat"))
            if not stat_files:
                continue
            hit = False
            for line in stat_files[0].read_text(errors="replace").splitlines():
                parts = line.split()
                if "MPR" not in parts:
                    continue
                i = parts.index("MPR")
                if len(parts) < i + 10:
                    continue
                if str(parts[i + 3]) != sid:
                    continue
                fcst_var = parts[9] if len(parts) > 9 else ""
                if fcst_var == "precip":
                    fcst_var = "rainfall_last_mm"
                if want:
                    # legacy single-field STAT used name precip
                    if want == "rainfall_last_mm" and fcst_var in ("precip", "rainfall_last_mm", ""):
                        pass
                    elif fcst_var != want:
                        continue
                try:
                    fcst = float(parts[i + 8]) if parts[i + 8] not in ("NA",) else None
                    obs = float(parts[i + 9]) if parts[i + 9] not in ("NA",) else None
                except ValueError:
                    continue
                valid_raw = parts[4] if len(parts) > 4 else f"{valid_tag[:8]}_{valid_tag[8:]}0000"
                valid_iso = _parse_valid_iso(valid_raw) or _parse_valid_iso(f"{valid_tag}0000")
                if not valid_iso:
                    continue
                hit = True
                if obs is not None:
                    obs_by_valid[valid_iso] = obs
                if init:
                    by_init.setdefault(init, []).append({
                        "valid_time": valid_iso,
                        "lead_time": int(lead) if lead is not None else None,
                        "fcst": fcst,
                        "obs": obs,
                        "parameter": fcst_var or want,
                        "err": (fcst - obs) if fcst is not None and obs is not None else None,
                    })
            if hit:
                found_any = True
        if found_any:
            break

    inits = []
    for init, pts in sorted(by_init.items()):
        pts_sorted = sorted(pts, key=lambda r: (r.get("lead_time") is None, r.get("lead_time") or 0, r["valid_time"]))
        inits.append({
            "init_time": init,
            "model": model,
            "points": [{"valid_time": p["valid_time"], "lead_time": p["lead_time"], "fcst": p["fcst"]} for p in pts_sorted],
            "table": pts_sorted,
        })
    obs = [{"valid_time": k, "obs": v} for k, v in sorted(obs_by_valid.items())]
    return {
        "station_id": sid,
        "model": model,
        "parameter": want or "rainfall_last_mm",
        "method": "metplus_point",
        "obs": obs,
        "inits": inits,
        "n_inits": len(inits),
        "n_obs": len(obs),
    }
