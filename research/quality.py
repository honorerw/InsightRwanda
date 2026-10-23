"""Data-quality checks for the supplied analytical slice."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .data_pipeline import ANALYSIS_COLUMNS, DISTRICTS, PROVINCES


@dataclass(frozen=True)
class QualityCheck:
    check_id: str
    category: str
    status: str
    finding: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _check(check_id: str, category: str, status: str, finding: str, **evidence: Any) -> QualityCheck:
    return QualityCheck(check_id, category, status, finding, evidence)


def run_quality_checks(
    frame: pd.DataFrame,
    source_variable_count: int | None = None,
    *,
    expected_columns: list[str] | None = None,
    row_unit: str = "household",
    slice_label: str | None = None,
) -> list[QualityCheck]:
    """Run structural and analytical-slice checks.

    These checks describe data structure and coding integrity. They do not certify
    representativeness, fieldwork quality, or official statistical publication.
    Second sources pass ``expected_columns`` (the documented subset) and
    ``row_unit="individual"`` so the key check states the unit instead of
    failing innocently on repeated household keys.
    """

    checks: list[QualityCheck] = []
    if expected_columns is None:
        expected_columns = [c for c in ANALYSIS_COLUMNS if c not in {"province", "district", "setting", "sex", "head_sex"}]
    required = list(expected_columns)
    missing = sorted(set(required) - set(frame.columns))
    checks.append(_check(
        "schema_required_columns", "Schema", "PASS" if not missing else "FAIL",
        "All requested analytical variables are present." if not missing else "Requested analytical variables are missing.",
        missing_columns=missing,
        requested_count=len(required),
    ))

    checks.append(_check(
        "row_count", "Schema", "PASS" if len(frame) > 0 else "FAIL",
        f"{len(frame):,} records are available in the loaded slice.", rows=int(len(frame)),
    ))

    duplicate_keys = int(frame["key"].duplicated().sum()) if "key" in frame else -1
    if row_unit == "household":
        key_status = "PASS" if duplicate_keys == 0 else "FAIL"
        key_finding = (
            "Household identifiers are unique in the supplied slice." if duplicate_keys == 0
            else "Household identifier is missing or repeated; row-level integrity cannot be confirmed."
        )
    else:
        key_status = "INFO"
        key_finding = (
            f"Row unit is {row_unit}: household keys repeat across selected members "
            f"({int(frame['key'].nunique()):,} unique households from {len(frame):,} rows)."
        )
    checks.append(_check(
        "unique_household_key", "Integrity", key_status, key_finding,
        duplicate_rows=duplicate_keys,
    ))

    if "hh_wt" in frame:
        invalid_weight_mask = frame["hh_wt"].isna() | frame["hh_wt"].le(0) | ~np.isfinite(frame["hh_wt"])
        invalid_weights = int(invalid_weight_mask.sum())
        weight_min = float(frame["hh_wt"].min())
        weight_max = float(frame["hh_wt"].max())
    else:
        invalid_weights = -1
        weight_min = float("nan")
        weight_max = float("nan")
    checks.append(_check(
        "household_weight", "Survey fields", "PASS" if invalid_weights == 0 else "FAIL",
        "All household weights are present, finite and positive." if invalid_weights == 0 else "Household weights are missing, non-finite, or non-positive.",
        invalid_weights=invalid_weights,
        weight_min=weight_min,
        weight_max=weight_max,
    ))

    invalid_provinces = int((~frame["a1"].isin(PROVINCES)).sum()) if "a1" in frame else -1
    invalid_districts = int((~frame["a2"].isin(DISTRICTS)).sum()) if "a2" in frame else -1
    geography_status = "PASS" if invalid_provinces == 0 and invalid_districts == 0 else "FAIL" if invalid_provinces < 0 or invalid_districts < 0 else "WARN"
    checks.append(_check(
        "geographic_codes", "Coding", geography_status,
        "Province and district codes map to the supplied code dictionaries." if invalid_provinces == 0 and invalid_districts == 0 else "Some geographic codes do not map to the supplied dictionaries.",
        invalid_province_codes=invalid_provinces,
        invalid_district_codes=invalid_districts,
    ))

    if "a1" in frame and "a2" in frame:
        district_province_mismatch = int(((frame["a2"] // 10) != frame["a1"]).sum())
    else:
        district_province_mismatch = -1
    consistency_status = "PASS" if district_province_mismatch == 0 else "FAIL" if district_province_mismatch < 0 else "WARN"
    checks.append(_check(
        "district_province_consistency", "Consistency", consistency_status,
        "District code prefixes are consistent with province codes." if district_province_mismatch == 0 else "District/province fields are missing or some code combinations are inconsistent.",
        mismatched_rows=district_province_mismatch,
    ))

    core = ["qf4_05", "e9b", "e9c", "e7", "c14_5", "b2", "a1", "a2"]
    missingness = {
        col: round(float(frame[col].isna().mean()), 4) for col in core if col in frame
    }
    checks.append(_check(
        "core_missingness", "Completeness", "INFO",
        "Missingness was measured for core dashboard variables; it is not imputed.",
        missingness=missingness,
    ))

    expected_codes = {
        "qf4_05": {1, 2}, "e9b": {1, 2}, "c14_5": {1, 2}, "f3": {1, 2},
        "e9c": {1, 2, 3, 99}, "e7": {1, 2, 3, 4}, "b2": {1, 2},
    }
    unexpected_codes = {}
    for col, allowed in expected_codes.items():
        if col in frame:
            values = sorted(frame[col].dropna().unique().tolist())
            unexpected = [v for v in values if v not in allowed]
            if unexpected:
                unexpected_codes[col] = {"observed": values, "allowed": sorted(allowed), "unexpected": unexpected}
    checks.append(_check(
        "core_value_codes", "Coding", "PASS" if not unexpected_codes else "WARN",
        "No unexpected codes were found in the checked indicator variables." if not unexpected_codes else "Unexpected codes were found in checked indicator variables.",
        unexpected_codes=unexpected_codes,
    ))

    if source_variable_count is not None:
        analytical_desc = slice_label or f"a documented {len(ANALYSIS_COLUMNS):,}-variable analytical slice"
        checks.append(_check(
            "source_inventory", "Traceability", "PASS",
            f"The source metadata reports {source_variable_count:,} variables; the app uses {analytical_desc}.",
            source_variables=source_variable_count,
            analytical_variables=len(expected_columns),
        ))
    return checks


def quality_summary(checks: list[QualityCheck]) -> dict[str, int]:
    return {status: sum(c.status == status for c in checks) for status in ["PASS", "WARN", "FAIL", "INFO"]}
