"""Data loader untuk dashboard - fetch dari server webpsi atau lokal."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import pandas as pd


def _load_env() -> dict[str, str]:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    config = dict(os.environ)
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
    return config


def get_data_source() -> tuple[str, str]:
    """Return (source_type, source_path_or_url)."""
    cfg = _load_env()
    if url := cfg.get("DATA_SOURCE_URL"):
        return "url", url
    if path := cfg.get("DATA_SOURCE_PATH"):
        return "local", path
    # Fallback ke sample data
    sample = Path(__file__).resolve().parents[2] / "sample_data" / "dashboard"
    return "local", str(sample)


def fetch_json(filename: str) -> dict[str, Any]:
    source_type, source = get_data_source()
    if source_type == "url":
        url = f"{source.rstrip('/')}/{filename}"
        with urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode())
    path = Path(source) / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_csv(filename: str) -> pd.DataFrame:
    source_type, source = get_data_source()
    if source_type == "url":
        url = f"{source.rstrip('/')}/{filename}"
        with urlopen(url, timeout=30) as resp:
            return pd.read_csv(StringIO(resp.read().decode()))
    path = Path(source) / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_summary() -> dict[str, Any]:
    return fetch_json("summary.json")


def load_stats() -> pd.DataFrame:
    return fetch_csv("verification_stats.csv")


def load_manifest() -> dict[str, Any]:
    return fetch_json("manifest.json")


def get_last_updated() -> str:
    manifest = load_manifest()
    if manifest.get("updated_at"):
        return manifest["updated_at"]
    summary = load_summary()
    return summary.get("generated_at", "Unknown")


def get_config() -> dict[str, str]:
    cfg = _load_env()
    return {
        "model": cfg.get("MODEL_NAME", "INanWP"),
        "observation": cfg.get("OBS_NAME", "GSMAP NRT"),
        "domain": cfg.get("DOMAIN_NAME", "Indonesia"),
        "refresh_interval": int(cfg.get("REFRESH_INTERVAL", "0")),
    }
