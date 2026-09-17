#!/usr/bin/env python3
"""Build dashboard/series.json from gridstat .stat/.txt for leads H+3..H+72."""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

CNT_IDX = {
    "TOTAL": 0, "FBAR": 1, "OBAR": 11, "ME": 31, "MAE": 44, "MSE": 50, "PR_CORR": 21, "MBIAS": 41,
}
CTS_IDX = {
    "TOTAL": 0, "ACC": 11, "FBIAS": 16, "PODY": 19, "FAR": 34, "CSI": 39, "GSS": 44, "HSS": 52,
}


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
        for t in ("CNT", "CTS", "CTC", "SL1L2"):
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
        records.append(rec)
    return records


def find_score_file(run_dir: Path) -> Path | None:
    txts = sorted(run_dir.glob("*.txt"))
    # prefer MET dump copy ending .stat.txt or scores from .stat
    for p in txts:
        if p.name.endswith(".stat.txt") or "INANWP_vs_GSMAP" in p.name:
            return p
    stats = sorted(run_dir.glob("*.stat"))
    return stats[0] if stats else (txts[0] if txts else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metplus-dir", default=str(Path.home() / "data/metplus"))
    ap.add_argument("--init", help="Forecast init YYYYMMDDHH")
    ap.add_argument("--max-lead", type=int, default=72)
    ap.add_argument("--step", type=int, default=3)
    args = ap.parse_args()

    root = Path(args.metplus_dir)
    gridstat = root / "gridstat"
    dash = root / "dashboard"
    dash.mkdir(parents=True, exist_ok=True)

    points = []
    for lead in range(args.step, args.max_lead + 1, args.step):
        # match by meta lead file or by scanning summary_*.json
        matched = None
        for run_dir in sorted(gridstat.glob("*")):
            if not run_dir.is_dir():
                continue
            meta_p = run_dir / "run_meta.json"
            if meta_p.exists():
                meta = json.loads(meta_p.read_text())
                if int(meta.get("lead_hours", -1)) == lead:
                    if args.init and meta.get("init") != args.init:
                        continue
                    matched = (run_dir, meta)
                    break
        if not matched:
            continue
        run_dir, meta = matched
        score_file = find_score_file(run_dir)
        if not score_file:
            continue
        recs = parse_stat(score_file)
        cnt = next((r for r in recs if r["line_type"] == "CNT"), {})
        cts01 = next((r for r in recs if r["line_type"] == "CTS" and r.get("fcst_thresh") == ">0.1"), {})
        cts10 = next((r for r in recs if r["line_type"] == "CTS" and r.get("fcst_thresh") == ">1.0"), {})
        points.append({
            "lead_hours": lead,
            "valid": meta.get("valid") or run_dir.name,
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
            "txt_file": score_file.name,
            "run_dir": run_dir.name,
        })

    points.sort(key=lambda p: p["lead_hours"])
    init = args.init or (points[0]["init"] if points else None)
    series = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "init": init,
        "precip_source": "RAINNC+RAINC+RAINSH",
        "accum_hours": args.step,
        "max_lead_hours": args.max_lead,
        "n_points": len(points),
        "points": points,
    }
    out = dash / "series.json"
    out.write_text(json.dumps(series, indent=2))
    if init:
        (dash / f"series_{init}.json").write_text(json.dumps(series, indent=2))
    # also flat txt for series
    lines = ["lead_hours,valid,rmse,me,mae,csi_0.1,ets_0.1,pod_0.1,far_0.1,fbias_0.1"]
    for p in points:
        lines.append(
            f"{p['lead_hours']},{p['valid']},{p['rmse']},{p['me']},{p['mae']},"
            f"{p['csi_0.1']},{p['ets_0.1']},{p['pod_0.1']},{p['far_0.1']},{p['fbias_0.1']}"
        )
    (dash / "series.txt").write_text("\n".join(lines) + "\n")
    print(json.dumps({"wrote": str(out), "n_points": len(points), "init": init}, indent=2))


if __name__ == "__main__":
    main()
