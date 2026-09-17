#!/usr/bin/env python3
"""Build dashboard series JSON from GridStat / PointStat / FSS / MODE outputs."""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

CNT_IDX = {
    "TOTAL": 0, "FBAR": 1, "OBAR": 11, "ME": 31, "MAE": 44, "MSE": 50, "PR_CORR": 21, "MBIAS": 41,
}
CTS_IDX = {
    "TOTAL": 0, "ACC": 11, "FBIAS": 16, "PODY": 19, "FAR": 34, "CSI": 39, "GSS": 44, "HSS": 52,
}
# NBRCTS: FSS is typically near the end; MET column layout varies — parse by header if present
NBRCTS_FSS_NAMES = ("FSS", "FRACTION_SKILL_SCORE")


def num(v):
    if v in (None, "", "NA"):
        return None
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except ValueError:
        return None


def parse_stat(path: Path):
    records = []
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 24:
            continue
        line_type = None
        type_idx = -1
        for t in ("CNT", "CTS", "CTC", "SL1L2", "NBRCTS", "NBRCNT", "NBRCTC"):
            if t in parts:
                type_idx = parts.index(t)
                line_type = t
                break
        if not line_type:
            continue
        body = parts[type_idx + 1 :]
        rec = {
            "line_type": line_type,
            "fcst_thresh": parts[type_idx - 4] if type_idx >= 4 else "NA",
            "raw_parts": parts,
            "body": body,
        }
        if line_type == "CNT":
            mse = num(body[CNT_IDX["MSE"]]) if len(body) > CNT_IDX["MSE"] else None
            rec.update({
                "total": num(body[CNT_IDX["TOTAL"]]) if body else None,
                "fbar": num(body[CNT_IDX["FBAR"]]) if len(body) > CNT_IDX["FBAR"] else None,
                "obar": num(body[CNT_IDX["OBAR"]]) if len(body) > CNT_IDX["OBAR"] else None,
                "me": num(body[CNT_IDX["ME"]]) if len(body) > CNT_IDX["ME"] else None,
                "mae": num(body[CNT_IDX["MAE"]]) if len(body) > CNT_IDX["MAE"] else None,
                "rmse": math.sqrt(mse) if mse is not None and mse >= 0 else None,
                "pr_corr": num(body[CNT_IDX["PR_CORR"]]) if len(body) > CNT_IDX["PR_CORR"] else None,
                "mbias": num(body[CNT_IDX["MBIAS"]]) if len(body) > CNT_IDX["MBIAS"] else None,
            })
        if line_type == "CTS":
            for k, i in CTS_IDX.items():
                rec[k.lower() if k != "PODY" else "pod"] = num(body[i]) if len(body) > i else None
            rec["ets"] = rec.get("gss")
        if line_type == "NBRCTS":
            # Heuristic: FSS often last numeric columns; also try named scan
            fss = None
            for i, p in enumerate(parts):
                if p.upper() in NBRCTS_FSS_NAMES and i + 1 < len(parts):
                    fss = num(parts[i + 1])
                    break
            if fss is None and body:
                # MET v11+ NBRCTS: FSS is index 23 in many builds (after TOTAL...)
                for idx in (23, 22, 24, len(body) - 1):
                    if 0 <= idx < len(body):
                        fss = num(body[idx])
                        if fss is not None and 0.0 <= fss <= 1.0:
                            break
            rec["fss"] = fss
            # neighborhood width often in INTERP_PNTS or similar column before line type
            rec["nbrhd_width"] = num(parts[type_idx - 1]) if type_idx >= 1 else None
        records.append(rec)
    return records


def find_score_file(run_dir: Path, prefer_substr: str | None = None) -> Path | None:
    txts = sorted(run_dir.glob("*.txt"))
    stats = sorted(run_dir.glob("*.stat"))
    if prefer_substr:
        for p in list(txts) + list(stats):
            if prefer_substr in p.name:
                return p
    for p in txts:
        if p.name.endswith(".stat.txt") or "INANWP_vs_GSMAP" in p.name:
            return p
    return stats[0] if stats else (txts[0] if txts else None)


def match_run(root: Path, sub: str, lead: int, init: str | None):
    base = root / sub
    if not base.is_dir():
        return None
    for run_dir in sorted(base.glob("*")):
        if not run_dir.is_dir():
            continue
        meta_p = run_dir / "run_meta.json"
        if not meta_p.exists():
            continue
        meta = json.loads(meta_p.read_text())
        if int(meta.get("lead_hours", -1)) != lead:
            continue
        if init and meta.get("init") != init:
            continue
        return run_dir, meta
    return None


def point_from_cnt_cts(lead, meta, recs, extra=None):
    cnt = next((r for r in recs if r["line_type"] == "CNT"), {})
    cts01 = next((r for r in recs if r["line_type"] == "CTS" and r.get("fcst_thresh") == ">0.1"), {})
    cts10 = next((r for r in recs if r["line_type"] == "CTS" and r.get("fcst_thresh") == ">1.0"), {})
    row = {
        "lead_hours": lead,
        "valid": meta.get("valid") or meta.get("valid_yyyymmddhh"),
        "init": meta.get("init"),
        "rmse": cnt.get("rmse"),
        "me": cnt.get("me"),
        "mae": cnt.get("mae"),
        "fbar": cnt.get("fbar"),
        "obar": cnt.get("obar"),
        "mbias": cnt.get("mbias"),
        "pr_corr": cnt.get("pr_corr"),
        "acc_0.1": cts01.get("acc"),
        "pod_0.1": cts01.get("pod"),
        "far_0.1": cts01.get("far"),
        "csi_0.1": cts01.get("csi"),
        "ets_0.1": cts01.get("ets"),
        "fbias_0.1": cts01.get("fbias"),
        "csi_1.0": cts10.get("csi"),
        "ets_1.0": cts10.get("ets"),
        "matched_pairs": int(cnt.get("total") or 0) if cnt.get("total") is not None else meta.get("matched_pairs"),
    }
    if extra:
        row.update(extra)
    return row


def export_method(root: Path, method: str, sub: str, init, max_lead, step, prefer=None):
    points = []
    for lead in range(step, max_lead + 1, step):
        matched = match_run(root, sub, lead, init)
        if not matched:
            continue
        run_dir, meta = matched
        score_file = find_score_file(run_dir, prefer_substr=prefer)
        if not score_file:
            # MODE may not have classic .stat — summarize objects
            if method == "metplus_mode":
                objs = list(run_dir.glob("*.obj")) + list(run_dir.glob("*_obj.txt"))
                interest = None
                n_fcst = n_obs = n_match = None
                for p in run_dir.glob("*"):
                    if p.suffix in (".txt", ".stat", ".out") or "mode" in p.name.lower():
                        text = p.read_text(errors="replace")
                        m = re.search(r"TOTAL INTEREST\s*[:=]\s*([0-9.]+)", text, re.I)
                        if m:
                            interest = num(m.group(1))
                        m = re.search(r"Fcst\s+objects\s*[:=]\s*(\d+)", text, re.I)
                        if m:
                            n_fcst = int(m.group(1))
                        m = re.search(r"Obs\s+objects\s*[:=]\s*(\d+)", text, re.I)
                        if m:
                            n_obs = int(m.group(1))
                        m = re.search(r"Matched\s*[:=]\s*(\d+)", text, re.I)
                        if m:
                            n_match = int(m.group(1))
                points.append({
                    "lead_hours": lead,
                    "valid": meta.get("valid_yyyymmddhh"),
                    "init": meta.get("init"),
                    "rmse": None,
                    "me": None,
                    "mae": None,
                    "csi_0.1": None,
                    "ets_0.1": None,
                    "total_interest": interest,
                    "n_fcst_objects": n_fcst,
                    "n_obs_objects": n_obs,
                    "n_matched": n_match,
                    "n_obj_files": len(objs),
                    "mode_rc": meta.get("mode_rc"),
                })
            continue
        recs = parse_stat(score_file)
        if method == "metplus_fss":
            nbr = [r for r in recs if r["line_type"] == "NBRCTS"]
            # pick width~5 or median FSS at thresh >1.0
            chosen = None
            for r in nbr:
                if r.get("fcst_thresh") in (">1.0", ">=1.0", ">1", "1"):
                    chosen = r
                    if r.get("nbrhd_width") in (5, 5.0):
                        break
            if not chosen and nbr:
                chosen = nbr[len(nbr) // 2]
            fss = chosen.get("fss") if chosen else None
            points.append({
                "lead_hours": lead,
                "valid": meta.get("valid_yyyymmddhh"),
                "init": meta.get("init"),
                "rmse": None,
                "me": None,
                "mae": None,
                "fss": fss,
                "fss_1.0": fss,
                "csi_0.1": None,
                "ets_0.1": None,
                "nbrhd_width": chosen.get("nbrhd_width") if chosen else 5,
                "score": fss,
            })
        else:
            points.append(point_from_cnt_cts(lead, meta, recs))

    points.sort(key=lambda p: p["lead_hours"])
    series = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "init": init or (points[0]["init"] if points else None),
        "method": method,
        "precip_source": "RAINNC+RAINC+RAINSH",
        "accum_hours": step,
        "max_lead_hours": max_lead,
        "n_points": len(points),
        "points": points,
    }
    return series


def write_series(dash: Path, series: dict, stem: str):
    dash.mkdir(parents=True, exist_ok=True)
    out = dash / f"{stem}.json"
    out.write_text(json.dumps(series, indent=2))
    init = series.get("init")
    if init:
        (dash / f"{stem}_{init}.json").write_text(json.dumps(series, indent=2))
    # txt
    pts = series.get("points") or []
    if series.get("method") == "metplus_fss":
        lines = ["lead_hours,valid,fss,nbrhd_width"]
        for p in pts:
            lines.append(f"{p['lead_hours']},{p.get('valid')},{p.get('fss')},{p.get('nbrhd_width')}")
    elif series.get("method") == "metplus_mode":
        lines = ["lead_hours,valid,total_interest,n_fcst_objects,n_obs_objects,n_matched"]
        for p in pts:
            lines.append(
                f"{p['lead_hours']},{p.get('valid')},{p.get('total_interest')},"
                f"{p.get('n_fcst_objects')},{p.get('n_obs_objects')},{p.get('n_matched')}"
            )
    else:
        lines = ["lead_hours,valid,rmse,me,mae,csi_0.1,ets_0.1,pod_0.1,far_0.1,fbias_0.1"]
        for p in pts:
            lines.append(
                f"{p['lead_hours']},{p.get('valid')},{p.get('rmse')},{p.get('me')},{p.get('mae')},"
                f"{p.get('csi_0.1')},{p.get('ets_0.1')},{p.get('pod_0.1')},{p.get('far_0.1')},{p.get('fbias_0.1')}"
            )
    (dash / f"{stem}.txt").write_text("\n".join(lines) + "\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metplus-dir", default=str(Path.home() / "data/metplus"))
    ap.add_argument("--init", help="Forecast init YYYYMMDDHH")
    ap.add_argument("--max-lead", type=int, default=72)
    ap.add_argument("--step", type=int, default=3)
    args = ap.parse_args()

    root = Path(args.metplus_dir)
    dash = root / "dashboard"
    summary = {}

    grid = export_method(root, "metplus", "gridstat", args.init, args.max_lead, args.step)
    # legacy names for dashboard GridStat
    write_series(dash, grid, "series")
    summary["gridstat"] = {"n_points": grid["n_points"], "init": grid["init"]}

    point = export_method(root, "metplus_point", "pointstat", args.init, args.max_lead, args.step, prefer="POINT")
    write_series(dash, point, "series_point")
    summary["pointstat"] = {"n_points": point["n_points"], "init": point["init"]}

    fss = export_method(root, "metplus_fss", "fss", args.init, args.max_lead, args.step, prefer="FSS")
    write_series(dash, fss, "series_fss")
    summary["fss"] = {"n_points": fss["n_points"], "init": fss["init"]}

    mode = export_method(root, "metplus_mode", "mode", args.init, args.max_lead, args.step)
    write_series(dash, mode, "series_mode")
    summary["mode"] = {"n_points": mode["n_points"], "init": mode["init"]}

    (dash / "summary_methods.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "init": args.init,
        "methods": summary,
    }, indent=2))
    print(json.dumps({"dashboard": str(dash), "methods": summary}, indent=2))


if __name__ == "__main__":
    main()
