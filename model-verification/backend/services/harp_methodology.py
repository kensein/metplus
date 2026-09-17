"""Verification methodology docs (HARP point + METplus techniques).

Copy is English, kept plain. Avoid semicolons and em dashes in user-facing text.
"""

HARP_REFERENCES = [
    {
        "title": "harpPoint",
        "url": "https://github.com/harphub/harpPoint",
        "description": "Point verification toolkit for NWP forecasts (Harmonised Assessment of Reanalysis Products).",
    },
    {
        "title": "harpIO docs",
        "url": "https://harphub.github.io/harpIO/",
        "description": "Read and transform forecasts and observations, including grid-to-station interpolation.",
    },
    {
        "title": "harpIO transformations",
        "url": "https://harphub.github.io/harpIO/articles/transformations.html",
        "description": "Point interpolation, regridding, and related transforms used when reading forecasts.",
    },
]

HARP_WORKFLOW = [
    {
        "step": 1,
        "name": "Read forecast",
        "detail": "Open model NetCDF and interpolate surface fields to Soft or Sinoptik station locations.",
    },
    {
        "step": 2,
        "name": "Read observations",
        "detail": "Load BMKG Soft or Sinoptik station reports at matching valid times.",
    },
    {
        "step": 3,
        "name": "Join",
        "detail": "Match forecast and observation on station id and valid time. Only complete pairs enter scoring.",
    },
    {
        "step": 4,
        "name": "Quality control",
        "detail": "Drop BMKG sentinel values, then remove outliers where absolute error exceeds 4 sigma.",
    },
    {
        "step": 5,
        "name": "Deterministic scores",
        "detail": "Compute bias, RMSE, MAE, error stdev, and correlation per parameter and lead time.",
    },
    {
        "step": 6,
        "name": "Common cases",
        "detail": "For fair model ranking, keep only cases present in every selected model.",
    },
]

HARP_SCORES = [
    {"id": "bias", "formula": "mean(fcst − obs)", "note": "Positive means the forecast runs high on average."},
    {"id": "rmse", "formula": "√mean((fcst − obs)²)", "note": "Primary ranking metric for continuous fields."},
    {"id": "mae", "formula": "mean(|fcst − obs|)", "note": "Mean absolute error, less sensitive to rare extremes than RMSE."},
    {"id": "stde", "formula": "std(fcst − obs, ddof=1)", "note": "Spread of the error after removing the mean bias."},
    {"id": "correlation", "formula": "Pearson(fcst, obs)", "note": "Linear association between forecast and observation."},
]

METPLUS_TECHNIQUES = [
    {
        "id": "metplus",
        "title": "GridStat (spatial)",
        "summary": (
            "Compares InaNWP precipitation fields with GSMaP on a common grid. "
            "Model rain is the 3-hour accumulation of RAINNC + RAINC + RAINSH. "
            "Leads run from H+3 through H+72."
        ),
        "workflow": [
            "Build a 3-hour forecast precip field from wrfout.",
            "Accumulate hourly GSMaP to 3 hours and regrid onto the model grid.",
            "Run grid_stat for continuous (CNT) and categorical (CTS) scores plus matched-pair maps.",
            "Export lead-time series for the dashboard.",
        ],
        "scores": [
            {"id": "rmse / mae / me", "formula": "as in CNT continuous stats", "note": "Grid-mean continuous errors on precip."},
            {"id": "CSI / ETS / POD / FAR", "formula": "from contingency table at thresholds (e.g. >0.1 mm, >1 mm)", "note": "Categorical hit or miss scores for rain events."},
        ],
    },
    {
        "id": "metplus_point",
        "title": "PointStat (BMKG Soft stations)",
        "summary": (
            "Samples InaNWP surface fields at BMKG station locations and scores them against Soft or Sinoptik. "
            "Observation source matches HARP. Parameters cover 2 m temperature, dewpoint, RH, QFF, QFE, "
            "wind speed, wind direction, and last-period rainfall when both Soft and wrfout provide them."
        ),
        "workflow": [
            "Extract a multi-field surface NetCDF at the valid time.",
            "Build Soft ASCII point observations with the same field names.",
            "Convert ASCII with ascii2nc, then run point_stat with MPR and CNT output.",
            "Export per-parameter lead-time series for the dashboard.",
        ],
        "scores": [
            {"id": "rmse / mae / me", "formula": "CNT over matched stations", "note": "Same continuous family as HARP, computed by MET."},
            {"id": "CSI / ETS", "formula": "CTS for rainfall thresholds", "note": "Applied to rainfall_last when categorical thresholds are set."},
        ],
    },
    {
        "id": "metplus_fss",
        "title": "FSS (neighborhood)",
        "summary": (
            "Fractions Skill Score checks how well rain fractions agree inside a neighborhood window. "
            "It forgives small location errors that would hurt strict grid-point scores."
        ),
        "workflow": [
            "Use the same 3-hour precip pair as GridStat.",
            "Run neighborhood verification (NBRCTS / NBRCNT) for several window widths.",
            "Surface FSS at a chosen threshold (often >1 mm) for each lead.",
        ],
        "scores": [
            {
                "id": "FSS",
                "formula": "1 − MSE_fractions / MSE_ref",
                "note": "Fractions inside each neighborhood. 1 is a perfect match of rain area fractions.",
            },
        ],
    },
    {
        "id": "metplus_mode",
        "title": "MODE (object-based)",
        "summary": (
            "MODE finds rain objects in forecast and GSMaP, then pairs them by location, size, and intensity. "
            "Useful when storms look right but sit a little off the observed spot."
        ),
        "workflow": [
            "Identify objects above a rain threshold in forecast and observation.",
            "Match object pairs and compute interest scores.",
            "Summarize matched interest and object counts per lead.",
        ],
        "scores": [
            {"id": "total / mean interest", "formula": "mean interest over matched F–O pairs", "note": "Higher interest means a stronger object match."},
            {"id": "object counts", "formula": "n_fcst, n_obs, n_matched", "note": "How many objects were found and successfully paired."},
        ],
    },
]


def get_harp_methodology() -> dict:
    return {
        "title": "HARP point verification",
        "subtitle": "Station verification following the harpPoint and harpIO workflow",
        "references": HARP_REFERENCES,
        "workflow": HARP_WORKFLOW,
        "scores": HARP_SCORES,
        "qc": (
            "BMKG sentinel values such as 8888 or 9999 are treated as missing, not as zero. "
            "Setting them to zero would invent dry rain reports. "
            "After that, pairs with absolute error above 4 sigma are dropped. "
            "Wind direction uses circular error. "
            "Leads cover analysis (D+0) through D+7 (168 hours). "
            "If either forecast or observation is missing for a station and valid time, that pair is skipped."
        ),
        "python_equivalence": (
            "Upstream HARP is written in R (harpPoint, harpIO). "
            "This app mirrors that flow in Python: crop surface NetCDF, interpolate to stations, "
            "join with Soft observations, then compute the same deterministic scores."
        ),
        "data_sources": {
            "InaNWP": (
                "Real NetCDF (*-d01-asim.nc). Temperature uses t2m only. "
                "Max, min, wet-bulb, and visibility are not in the crop file, so they stay unavailable."
            ),
            "InaCAWO": "Forecast NetCDF not wired yet.",
            "GFS": "Forecast NetCDF not wired yet.",
            "IFS": "Forecast NetCDF not wired yet.",
        },
    }


def get_metplus_methodology() -> dict:
    return {
        "title": "METplus verification",
        "subtitle": "GridStat, PointStat, FSS, and MODE run on DPU against GSMaP or BMKG Soft",
        "compute_note": (
            "Scores are computed on the DPU host. This web app only reads exported artifacts "
            "(series JSON, STAT files, and optional maps)."
        ),
        "techniques": METPLUS_TECHNIQUES,
        "shared_precip": (
            "For GSMaP-based techniques, forecast precipitation is RAINNC + RAINC + RAINSH "
            "accumulated over 3 hours ending at the valid time."
        ),
    }


def get_methodology(method: str | None = None) -> dict:
    """Full methods handbook, optionally focused on one technique."""
    harp = get_harp_methodology()
    metplus = get_metplus_methodology()
    m = (method or "").strip().lower()
    payload = {
        "title": "Verification methods",
        "intro": (
            "This app supports two engines. HARP scores forecasts at BMKG stations. "
            "METplus adds spatial and object techniques against GSMaP, plus PointStat against Soft stations."
        ),
        "harp": harp,
        "metplus": metplus,
    }
    if m in ("harp",):
        payload["focus"] = "harp"
    elif m in ("metplus", "metplus_point", "metplus_fss", "metplus_mode"):
        payload["focus"] = m
    else:
        payload["focus"] = "all"
    return payload


# Back-compat alias used by older imports
def get_methodology_legacy() -> dict:
    return get_harp_methodology()
