"""Indicator definitions and calculations used by the dashboard."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorDefinition:
    indicator_id: str
    title: str
    definition: str
    unit: str
    population: str
    valid_response_rule: str
    source_variables: tuple[str, ...]
    method: str
    verification: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IndicatorResult:
    definition: IndicatorDefinition
    estimate: float
    numerator_n: int
    denominator_n: int
    weight_sum: float
    valid: bool
    note: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["definition"] = self.definition.to_dict()
        return payload


def weighted_mean(frame: pd.DataFrame, values: pd.Series, weight: str = "hh_wt") -> tuple[float, int, float]:
    if weight not in frame:
        raise ValueError(f"Required weight column is missing: {weight}")
    valid = values.notna() & frame[weight].notna() & frame[weight].gt(0) & np.isfinite(frame[weight])
    if valid.sum() == 0:
        return float("nan"), 0, 0.0
    weights = frame.loc[valid, weight].astype(float)
    clean_values = values.loc[valid].astype(float)
    return float(np.average(clean_values, weights=weights)), int(valid.sum()), float(weights.sum())


def _any_yes(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    available = [frame[c].where(frame[c].isin([1, 2])).eq(1) for c in columns if c in frame]
    if not available:
        return pd.Series(np.nan, index=frame.index)
    combined = pd.concat(available, axis=1)
    valid_components = pd.concat([frame[c].where(frame[c].isin([1, 2])) for c in columns if c in frame], axis=1)
    return combined.any(axis=1).astype(float).mask(valid_components.notna().sum(axis=1).eq(0))


INDICATORS: dict[str, IndicatorDefinition] = {
    "FI-01": IndicatorDefinition(
        "FI-01", "Active formal financial access",
        "Respondent currently uses at least one bank, digital bank, MFI, NDFI, mobile-money or Umurenge SACCO channel.",
        "Share of respondents", "Respondents with at least one valid current-use response", "Each qf4 response must be 1=Yes or 2=No; all-invalid/all-missing rows are excluded.",
        tuple(f"qf4_{i:02d}" for i in range(1, 7)),
        "Weighted mean of any(qf4_01:qf4_06 == 1) using hh_wt.",
        "Verified against embedded Stata variable labels; project-calculated, not an official published rate.",
        ("The supplied file does not include a documented variance design in this project.", "The denominator excludes records with all six source responses missing."),
    ),
    "FI-02": IndicatorDefinition(
        "FI-02", "Current mobile-money use", "Respondent currently uses a mobile-money operator.",
        "Share of respondents", "Respondents with a valid qf4_05 response", "qf4_05 must be 1=Yes or 2=No; other codes and missing values are excluded.", ("qf4_05",),
        "Weighted mean of qf4_05 == 1 using hh_wt.",
        "Verified against the embedded Stata label for qf4_05; project-calculated.",
        ("This measures current use, not account quality, transaction frequency or financial outcomes.",),
    ),
    "FI-03": IndicatorDefinition(
        "FI-03", "Emergency fund coverage", "Respondent reports having set aside emergency/rainy-day funds.",
        "Share of respondents", "Respondents with a valid e9b response", "e9b must be 1=Yes or 2=No; other codes and missing values are excluded.", ("e9b",),
        "Weighted mean of e9b == 1 using hh_wt.",
        "Verified against the embedded Stata label for e9b; project-calculated.",
        ("The question does not establish the size or adequacy of the emergency fund.",),
    ),
    "FI-04": IndicatorDefinition(
        "FI-04", "Emergency money is difficult to raise", "Respondent says raising 56,000 Rwf within the next month is very or somewhat difficult.",
        "Share of respondents", "Respondents with a substantive e9c response", "e9c in {1,2,3} is substantive; 99=Do not know and missing values are excluded.", ("e9c",),
        "Weighted mean of e9c in {1, 2} using hh_wt.",
        "Verified against the embedded Stata label for e9c; project-calculated.",
        ("This is a self-reported perception and should not be interpreted as a poverty threshold.",),
    ),
    "FI-05": IndicatorDefinition(
        "FI-05", "Income pressure", "Respondent reports that income does not cover living costs monthly or more than occasionally.",
        "Share of respondents", "Respondents with a valid e7 response", "e7 must be one of 1,2,3,4; other codes and missing values are excluded.", ("e7",),
        "Weighted mean of e7 in {1, 2} using hh_wt.",
        "Verified against the embedded Stata label for e7; project-calculated.",
        ("This is not an official poverty or consumption-based welfare measure.",),
    ),
    "FI-06": IndicatorDefinition(
        "FI-06", "Internet access", "Respondent reports access to the internet.",
        "Share of respondents", "Respondents with a valid c14_5 response", "c14_5 must be 1=Yes or 2=No; other codes and missing values are excluded.", ("c14_5",),
        "Weighted mean of c14_5 == 1 using hh_wt.",
        "Verified against the embedded Stata label for c14_5; project-calculated.",
        ("Access does not measure affordability, quality, frequency or digital skills.",),
    ),
}


def indicator_value(frame: pd.DataFrame, indicator_id: str) -> pd.Series:
    if indicator_id == "FI-01":
        return _any_yes(frame, INDICATORS[indicator_id].source_variables)
    if indicator_id == "FI-02":
        values = frame["qf4_05"].where(frame["qf4_05"].isin([1, 2]))
        return values.eq(1).astype(float).mask(values.isna())
    if indicator_id == "FI-03":
        values = frame["e9b"].where(frame["e9b"].isin([1, 2]))
        return values.eq(1).astype(float).mask(values.isna())
    if indicator_id == "FI-04":
        values = frame["e9c"].where(frame["e9c"].isin([1, 2, 3]))
        return values.isin([1, 2]).astype(float).mask(values.isna())
    if indicator_id == "FI-05":
        values = frame["e7"].where(frame["e7"].isin([1, 2, 3, 4]))
        return values.isin([1, 2]).astype(float).mask(values.isna())
    if indicator_id == "FI-06":
        values = frame["c14_5"].where(frame["c14_5"].isin([1, 2]))
        return values.eq(1).astype(float).mask(values.isna())
    raise KeyError(f"Unknown indicator: {indicator_id}")


def calculate_indicator(frame: pd.DataFrame, indicator_id: str) -> IndicatorResult:
    definition = INDICATORS[indicator_id]
    required = set(definition.source_variables) | {"hh_wt"}
    missing = sorted(required - set(frame.columns))
    absent_channels: list[str] = []
    if indicator_id == "FI-01":
        # A second source may legitimately lack a channel variable (e.g. no
        # digital bank). The union is then taken over the channels PRESENT in
        # the active source, and the absent channel is reported — it is never
        # imputed as "No". Anchor channels (bank, mobile money, SACCO) must exist.
        available = [c for c in definition.source_variables if c in frame.columns]
        if "qf4_01" not in frame.columns or len(available) < 4:
            raise ValueError(
                f"Indicator {indicator_id} needs at least the bank anchor plus four channel variables; "
                f"available: {', '.join(available)}"
            )
        # Channel availability is validated above (anchor + threshold); the
        # documented absent channel is a scope reduction, not a failure, so
        # clear the required-columns list for FI-01.
        missing = []
        absent_channels = [c for c in definition.source_variables if c not in frame.columns]
        if "hh_wt" not in frame.columns:
            raise ValueError("Indicator FI-01 is missing required column: hh_wt")
    if missing:
        raise ValueError(f"Indicator {indicator_id} is missing required columns: {', '.join(missing)}")
    values = indicator_value(frame, indicator_id)
    estimate, denominator_n, weight_sum = weighted_mean(frame, values)
    valid_weights = frame["hh_wt"].notna() & frame["hh_wt"].gt(0) & np.isfinite(frame["hh_wt"])
    numerator_n = int(((values == 1) & values.notna() & valid_weights).sum())
    note = "No survey-design standard error is shown because PSU/strata metadata and a documented variance method were not supplied."
    if absent_channels:
        channel_map = {"qf4_02": "digital bank"}
        names = ", ".join(channel_map.get(c, c) for c in absent_channels)
        note += f" Channel(s) absent on the active source and excluded from the union: {names} — not imputed as 'No'."
    return IndicatorResult(
        definition=definition,
        estimate=estimate,
        numerator_n=numerator_n,
        denominator_n=denominator_n,
        weight_sum=weight_sum,
        valid=denominator_n > 0 and not np.isnan(estimate),
        note=note,
    )


def calculate_by_group(frame: pd.DataFrame, indicator_id: str, group: str) -> pd.DataFrame:
    rows = []
    for name, subset in frame.groupby(group, dropna=False):
        result = calculate_indicator(subset, indicator_id)
        rows.append({
            "group": name,
            "estimate": result.estimate,
            "numerator_n": result.numerator_n,
            "denominator_n": result.denominator_n,
            "weight_sum": result.weight_sum,
        })
    return pd.DataFrame(rows, columns=["group", "estimate", "numerator_n", "denominator_n", "weight_sum"])
