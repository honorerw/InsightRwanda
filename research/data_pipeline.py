"""Reproducible loading and transformation of the supplied Stata source.

This module deliberately contains no Streamlit code. The same functions are used
by the dashboard and by the real-source tests, which keeps analysis independent
from presentation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ANALYSIS_COLUMNS = [
    "key", "a1", "a2", "a6", "hh_wt", "pop_wt", "hh_size", "hh_head", "b1", "b2",
    "c1c", "c4a", "c14_5", "f2", "f3", "f4c", "f4d", "f4e",
    "e2a", "e2c", "e2d", "e2e", "e6", "e7", "e7a", "e9a", "e9b", "e9c",
    "e10a1", "e10a2", "e10a3", "e10a4",
    *[f"qf1_{i:02d}" for i in range(1, 12)],
    *[f"qf3_{i:02d}" for i in range(1, 12)],
    *[f"qf4_{i:02d}" for i in range(1, 12)],
    "g4a", "g4b", "g6", "g11a", "g11b", "h4b", "h5", "h7", "h9a", "h10a",
    "i4a", "i4c", "i7", "i9a", "i9b", "j1a", "j1b", "k15_10", "k15_12",
    "n1b", "n3", "n4", "n10", "n11", "n12", "n13_3", "n13_4", "n13_5", "n13_6",
]

PROVINCES = {1: "Kigali", 2: "South", 3: "West", 4: "North", 5: "East"}
DISTRICTS = {
    11: "Nyarugenge", 12: "Gasabo", 13: "Kicukiro", 21: "Nyanza", 22: "Gisagara",
    23: "Nyaruguru", 24: "Huye", 25: "Nyamagabe", 26: "Ruhango", 27: "Muhanga",
    28: "Kamonyi", 31: "Karongi", 32: "Rutsiro", 33: "Rubavu", 34: "Nyabihu",
    35: "Ngororero", 36: "Rusizi", 37: "Nyamasheke", 41: "Rulindo", 42: "Gakenke",
    43: "Musanze", 44: "Burera", 45: "Gicumbi", 51: "Rwamagana", 52: "Nyagatare",
    53: "Gatsibo", 54: "Kayonza", 55: "Kirehe", 56: "Ngoma", 57: "Bugesera",
}
URBAN_RURAL = {1: "Urban", 2: "Rural"}
SEX = {1: "Male", 2: "Female"}


class SourceLoadError(RuntimeError):
    """Raised when a source cannot be read as the expected analytical Stata file."""


def yes(series: pd.Series, code: int = 1) -> pd.Series:
    """Return a nullable 0/1 indicator for a labelled yes code."""

    return series.eq(code).astype(float).mask(series.isna())


def any_yes(df: pd.DataFrame, columns: Iterable[str], code: int = 1) -> pd.Series:
    """Return 1 when any valid yes/no component is yes.

    For the survey's binary current-use questions, only codes 1 and 2 are
    substantive. Unexpected codes and missing values are excluded; a row with
    no substantive component is therefore missing rather than a false answer.
    """

    source_columns = [c for c in columns if c in df]
    if not source_columns:
        return pd.Series(np.nan, index=df.index)
    valid_components = pd.concat([df[c].where(df[c].isin([1, 2])) for c in source_columns], axis=1)
    output = valid_components.eq(code).any(axis=1).astype(float)
    return output.mask(valid_components.notna().sum(axis=1).eq(0))


def load_analysis_data(path: str | Path) -> pd.DataFrame:
    """Read only the documented analytical slice from the original Stata file.

    The original file is never modified. A missing requested column raises an
    error from pandas rather than silently producing an empty result.
    """

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Source dataset does not exist: {source}")
    try:
        df = pd.read_stata(
            source,
            columns=ANALYSIS_COLUMNS,
            convert_categoricals=False,
            preserve_dtypes=False,
        )
    except (OSError, ValueError, EOFError, ImportError) as exc:
        raise SourceLoadError(
            f"Could not read {source} as a compatible Stata source with the required analytical fields. "
            f"Original error: {exc}"
        ) from exc
    for column in df.select_dtypes(include="object").columns:
        df[column] = df[column].mask(df[column].eq(""), np.nan)
    df["province"] = df["a1"].map(PROVINCES).fillna("Unknown")
    df["district"] = df["a2"].map(DISTRICTS).fillna("Unknown")
    df["setting"] = df["a6"].map(URBAN_RURAL).fillna("Unknown")
    df["sex"] = df["b2"].map(SEX).fillna("Unknown")
    df["head_sex"] = df["hh_head"].map({1: "Male", 2: "Female"}).fillna("Unknown")
    return df


def enrich_analysis_data(frame: pd.DataFrame) -> pd.DataFrame:
    """Create analysis variables using the supplied survey labels and codes."""

    out = frame.copy()
    out["active_access"] = any_yes(out, [f"qf4_{i:02d}" for i in [1, 2, 3, 4, 5, 6]])
    out["mobile_money"] = yes(out["qf4_05"])
    out["bank_use"] = any_yes(out, ["qf4_01", "qf4_02"])
    out["sacco_use"] = yes(out["qf4_06"])
    out["formal_own_name"] = any_yes(out, [f"qf3_{i:02d}" for i in [1, 2, 3, 4, 5, 6]])
    out["emergency_fund"] = yes(out["e9b"])
    out["emergency_difficult"] = out["e9c"].isin([1, 2]).astype(float).mask(out["e9c"].isna())
    out["income_pressure"] = out["e7"].isin([1, 2]).astype(float).mask(out["e7"].isna())
    out["financial_stress"] = out["e6"].isin([1, 2, 3]).astype(float).mask(out["e6"].isna())
    out["owns_money"] = yes(out["e2a"])
    out["saves_regularly"] = out["e2c"].isin([1, 2]).astype(float).mask(out["e2c"].isna())
    out["internet_access"] = yes(out["c14_5"])
    out["phone_ownership"] = yes(out["f3"])
    out["microinsurance"] = yes(out["i4a"])
    out["social_safety_net"] = yes(out["i9a"])
    out["has_pension"] = yes(out["g11a"])
    out["resilience_score"] = out[["emergency_fund", "owns_money", "saves_regularly", "social_safety_net"]].mean(axis=1, skipna=True)
    out["resilience_band"] = pd.cut(
        out["resilience_score"],
        bins=[-0.01, .39, .69, 1.01],
        labels=["Priority", "Watch", "Resilient"],
    ).astype(object).where(out["resilience_score"].notna(), "Unknown")
    return out


def filter_analysis_data(
    frame: pd.DataFrame,
    province: str | None = None,
    district: str | None = None,
    setting: str | None = None,
    respondent_sex: str | None = None,
) -> pd.DataFrame:
    """Apply the dashboard's geographic and demographic filters consistently."""

    requested = {
        "province": province,
        "district": district,
        "setting": setting,
        "sex": respondent_sex,
    }
    missing = [column for column, value in requested.items() if value is not None and column not in frame]
    if missing:
        raise ValueError(f"Cannot apply filters; missing derived columns: {', '.join(missing)}")
    output = frame
    for column, value in requested.items():
        if value is not None:
            output = output[output[column].eq(value)]
    return output.copy()


def aggregate_weighted_measure(
    frame: pd.DataFrame,
    measure: str,
    dimensions: Iterable[str] = ("province", "district", "setting", "sex"),
) -> pd.DataFrame:
    """Build a disclosure-ready aggregate table without retaining row records."""

    dimensions = tuple(dimensions)
    required = set(dimensions) | {measure, "hh_wt"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Cannot aggregate; missing columns: {', '.join(missing)}")
    rows = []
    for keys, subset in frame.groupby(list(dimensions), dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        values = subset[measure]
        valid = values.notna() & subset["hh_wt"].notna() & subset["hh_wt"].gt(0) & np.isfinite(subset["hh_wt"])
        row = dict(zip(dimensions, keys))
        row.update({
            "records": int(len(subset)),
            "valid_records": int(valid.sum()),
            "positive_records": int((values.eq(1) & valid).sum()),
            "weight_sum": float(subset.loc[valid, "hh_wt"].sum()),
            "estimate": float(np.average(values.loc[valid], weights=subset.loc[valid, "hh_wt"])) if valid.any() else float("nan"),
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=[*dimensions, "records", "valid_records", "positive_records", "weight_sum", "estimate"])
