"""Evidence-linked insights and safe aggregate visualizations.

Phase 17 consumes only the aggregate result contract produced by Phase 14 (or
an approved geographic aggregate).  It never loads observations and it does
not grant analytical or publication eligibility.  A synthetic result can be
used by software tests when explicitly requested, but is never returned as a
verified research insight and is rejected by the production visualization
path.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
from typing import Any, Iterable

import plotly.graph_objects as go


RAW_KEYS = {
    "records",
    "rows",
    "raw_records",
    "household_id",
    "person_id",
    "respondent_id",
}
SUPPORTED_USES = {"internal_analysis", "public_display"}


def _blocker(identifier: str, message: str, next_action: str) -> dict[str, str]:
    return {"identifier": identifier, "message": message, "next_action": next_action}


def _contains_raw_keys(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(RAW_KEYS.intersection(value)) or any(_contains_raw_keys(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_raw_keys(item) for item in value)
    return False


def _stable_id(result: dict[str, Any]) -> str:
    explicit = result.get("result_id") or result.get("source_result_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    provenance = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
    identity = {
        "dataset_id": result.get("dataset_id"),
        "dataset_release": result.get("dataset_release"),
        "indicator_id": result.get("indicator_id"),
        "definition_version": result.get("definition_version"),
        "input_file_sha256": provenance.get("input_file_sha256"),
        "calculated_at_utc": provenance.get("calculated_at_utc"),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return f"result-{digest}"


def _definition_evidence(definition: dict[str, Any]) -> list[str]:
    references: list[str] = []
    for record in definition.get("mapping_records", []):
        if isinstance(record, dict):
            for key in ("evidence_reference", "codebook_reference"):
                value = record.get(key)
                if isinstance(value, str) and value.strip():
                    references.append(value.strip())
    review = definition.get("definition_review")
    if isinstance(review, dict):
        for field in review.get("fields", []):
            if isinstance(field, dict) and isinstance(field.get("evidence_reference"), str) and field["evidence_reference"].strip():
                references.append(field["evidence_reference"].strip())
    return list(dict.fromkeys(references))


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _base_blocked(
    *,
    definition: dict[str, Any] | None,
    blockers: Iterable[dict[str, str]],
    data_classification: str = "unavailable",
) -> dict[str, Any]:
    rows = list(blockers)
    return {
        "status": "blocked",
        "insight_status": "blocked",
        "indicator_id": definition.get("indicator_id") if isinstance(definition, dict) else None,
        "definition_version": definition.get("definition_version") if isinstance(definition, dict) else None,
        "source_result_id": None,
        "data_classification": data_classification,
        "blocker_ids": [item["identifier"] for item in rows],
        "blockers": rows,
        "next_actions": list(dict.fromkeys(item["next_action"] for item in rows)),
        "result_artifact_written": False,
        "raw_records_included": False,
    }


def _required_result_checks(result: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if result.get("calculation_status") != "calculated" or result.get("status") != "calculated":
        blockers.append(_blocker("result_not_calculated", "The source result is not a successful calculated aggregate.", "Use only a successful Phase 14 or approved Phase 16 aggregate result."))
    readiness = result.get("readiness") if isinstance(result.get("readiness"), dict) else {}
    if readiness.get("analysis_eligible") is not True:
        blockers.append(_blocker("central_analytical_eligibility", "The source result is not centrally eligible for analysis.", "Resolve the central readiness blockers; Phase 17 cannot override them."))
    if _contains_raw_keys(result) or result.get("raw_records_included") is True:
        blockers.append(_blocker("raw_records_in_result", "The source result contains a raw-record field.", "Remove row-level records and retain aggregate metadata only."))
    for key in ("dataset_id", "dataset_release", "indicator_id", "definition_version", "estimate"):
        if result.get(key) in (None, ""):
            blockers.append(_blocker("result_provenance", f"The source result is missing '{key}'.", "Provide the complete aggregate result contract and provenance."))
    if result.get("estimate") is not None:
        try:
            if not isfinite(float(result["estimate"])):
                raise ValueError
        except (TypeError, ValueError):
            blockers.append(_blocker("invalid_estimate", "The source result estimate is not a finite number.", "Re-run the validated calculation and retain no invalid aggregate."))
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    for key in ("input_validation", "result_integrity"):
        report = validation.get(key)
        if not isinstance(report, dict) or report.get("status") != "pass":
            blockers.append(_blocker("calculation_validation", f"The source result does not contain a passing {key} report.", "Run and pass the Phase 15 validation checks before constructing an insight."))
    quality = result.get("quality_validation") if isinstance(result.get("quality_validation"), dict) else {}
    if quality.get("status") != "pass":
        blockers.append(_blocker("quality_validation", "The source result does not contain a passing aggregate quality report.", "Resolve calculation-quality failures before constructing an insight."))
    provenance = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
    for key in ("mapping_evidence_references", "calculation_specification_evidence_references", "input_file_sha256", "calculated_at_utc"):
        value = provenance.get(key)
        if value in (None, "", []):
            blockers.append(_blocker("result_provenance", f"Result provenance field '{key}' is missing.", "Record the evidence-linked calculation provenance."))
    return blockers


def build_verified_insight(
    result: dict[str, Any] | None,
    definition: dict[str, Any] | None,
    *,
    intended_use: str = "internal_analysis",
    population_scope: str | None = None,
    geographic_scope: str | None = None,
    reference_period: str | None = None,
    max_age_days: int | None = None,
    allow_synthetic_test_data: bool = False,
) -> dict[str, Any]:
    """Validate one aggregate result and construct a traceable insight record."""

    if intended_use not in SUPPORTED_USES:
        return _base_blocked(definition=definition, blockers=[_blocker("invalid_intended_use", "The intended insight use is not supported.", "Choose internal_analysis or public_display.")])
    if not isinstance(result, dict):
        return _base_blocked(definition=definition, blockers=[_blocker("source_result_missing", "No aggregate analytical result is available.", "Complete an eligible calculation and provide its aggregate result artifact.")])
    if not isinstance(definition, dict):
        return _base_blocked(definition=None, blockers=[_blocker("indicator_definition_missing", "The verified indicator definition is unavailable.", "Provide the exact-release approved indicator definition.")])

    blockers = _required_result_checks(result)
    classification = str(result.get("data_classification", "unknown"))
    synthetic = classification == "synthetic_test_data" or result.get("is_synthetic") is True
    if synthetic and not allow_synthetic_test_data:
        blockers.append(_blocker("synthetic_result_not_for_real_research", "Synthetic test results cannot be used for real research insights or public displays.", "Supply an eligible authorized aggregate result from the approved source."))
    elif not synthetic and classification != "authorized_aggregate":
        blockers.append(_blocker("restricted_result_not_for_research", "Only explicitly authorized aggregate results may become research insights.", "Replace the result with an authorized aggregate and record its classification in the result provenance."))
    if result.get("indicator_id") != definition.get("indicator_id") or result.get("definition_version") != definition.get("definition_version"):
        blockers.append(_blocker("definition_result_mismatch", "The result and indicator definition do not identify the same versioned indicator.", "Use a result calculated from the exact approved definition version."))
    definition_fields = {
        "definition_version": definition.get("definition_version"),
        "indicator_id": definition.get("indicator_id"),
        "definition_text": definition.get("official_definition") or definition.get("description"),
        "numerator_definition": definition.get("numerator_definition"),
        "denominator_definition": definition.get("denominator_definition"),
        "unit": definition.get("unit"),
    }
    if any(value in (None, "") for value in definition_fields.values()):
        blockers.append(_blocker("definition_incomplete", "The indicator definition is missing version, formula, unit, or definition text.", "Complete and approve the exact-release indicator definition."))
    result_unit = result.get("unit")
    if result_unit not in (None, definition.get("unit")):
        blockers.append(_blocker("unit_mismatch", "The result unit does not match the verified indicator definition.", "Use the unit specified by the approved indicator definition."))
    if definition.get("unit") == "percentage":
        display_estimate = result.get("reported_percentage", result.get("percentage"))
    else:
        display_estimate = result.get("reported_estimate", result.get("estimate"))
    try:
        display_estimate = float(display_estimate)
        if not isfinite(display_estimate):
            raise ValueError
    except (TypeError, ValueError):
        display_estimate = None
        blockers.append(_blocker("result_unit_value_missing", "The result does not contain a finite value expressed in the verified indicator unit.", "Record an aggregate output value whose unit matches the approved definition."))
    if definition.get("definition_approval_status") != "approved" or definition.get("methodology_approval_status") != "approved":
        blockers.append(_blocker("definition_not_approved", "The indicator definition or methodology is not approved.", "Obtain independent approval for the indicator definition and method."))
    if not _definition_evidence(definition):
        blockers.append(_blocker("definition_provenance_missing", "No codebook-backed definition or mapping evidence is linked.", "Link verified definition and mapping evidence for the exact release."))
    expected = {
        "population_scope": population_scope,
        "geographic_scope": geographic_scope,
        "reference_period": reference_period,
    }
    for field, requested in expected.items():
        if requested is not None and result.get(field) != requested:
            blockers.append(_blocker(f"{field}_mismatch", f"The result does not match the requested {field.replace('_', ' ')}.", "Use a result with an explicitly compatible scope and reference period."))
    specification = definition.get("calculation_specification") if isinstance(definition.get("calculation_specification"), dict) else {}
    uncertainty_requested = specification.get("confidence_interval_requested") is True
    if uncertainty_requested and (result.get("standard_error") is None or not isinstance(result.get("confidence_interval"), dict)):
        blockers.append(_blocker("uncertainty_metadata_missing", "The approved method requests uncertainty information that is absent from the result.", "Implement the approved variance method and retain its uncertainty metadata."))
    if result.get("confidence_interval") is not None and result.get("confidence_interval_unit") != definition.get("unit"):
        blockers.append(_blocker("uncertainty_unit_unverified", "The confidence interval unit is not established as matching the indicator unit.", "Record and validate the interval unit from the approved statistical method."))
    if max_age_days is not None:
        calculated_at = _parse_timestamp((result.get("provenance") or {}).get("calculated_at_utc"))
        if calculated_at is None:
            blockers.append(_blocker("calculation_timestamp_invalid", "The result timestamp cannot be validated for freshness.", "Record a timezone-aware calculation timestamp."))
        elif (datetime.now(timezone.utc) - calculated_at).total_seconds() > max_age_days * 86400:
            blockers.append(_blocker("source_result_stale", "The source result is older than the requested freshness window.", "Recalculate or obtain an approved freshness review."))
    readiness = result.get("readiness") if isinstance(result.get("readiness"), dict) else {}
    if intended_use == "public_display":
        if readiness.get("publication_eligible") is not True:
            blockers.append(_blocker("publication_eligibility", "The result is analytically eligible, but not approved for public display.", "Complete separate disclosure, licensing, and publication review."))
        if result.get("publication_status") not in {"approved", "eligible"}:
            blockers.append(_blocker("publication_status", "The result does not carry an approved publication status.", "Record output-level publication approval before displaying it publicly."))
        if result.get("disclosure_status") not in {"approved", "reviewed"}:
            blockers.append(_blocker("disclosure_status", "Disclosure review is not approved for this output.", "Complete disclosure-risk review before public display."))
    if blockers:
        return _base_blocked(definition=definition, blockers=list(dict((item["identifier"], item) for item in blockers).values()), data_classification="synthetic_test_only" if synthetic else classification)

    source_result_id = _stable_id(result)
    insight_identity = f"{source_result_id}|{definition['indicator_id']}|{intended_use}"
    insight_id = "insight-" + hashlib.sha256(insight_identity.encode("utf-8")).hexdigest()[:20]
    limitations = list(result.get("limitations") or [])
    if not limitations:
        limitations.append("Interpretation is limited to the approved descriptive aggregate and its documented scope.")
    return {
        "status": "synthetic_test_only" if synthetic else "verified",
        "insight_status": "synthetic_test_only" if synthetic else "verified",
        "insight_id": insight_id,
        "source_result_id": source_result_id,
        "indicator_id": definition["indicator_id"],
        "definition_version": definition["definition_version"],
        "definition": definition_fields,
        "research_question": definition.get("policy_question"),
        "dataset_id": result["dataset_id"],
        "dataset_release": result["dataset_release"],
        "population_scope": result.get("population_scope"),
        "geographic_scope": result.get("geographic_scope"),
        "reference_period": result.get("reference_period"),
        "comparison_category": result.get("comparison_category"),
        "comparison_category_status": result.get("comparison_category_status"),
        "comparison_category_type": result.get("comparison_category_type"),
        "geographic_validation_status": result.get("geographic_validation_status"),
        "geographic_join_status": result.get("geographic_join_status"),
        "area_validation_status": result.get("area_validation_status"),
        "geographic_resource_id": result.get("geographic_resource_id"),
        "geographic_resource_version": result.get("geographic_resource_version"),
        "geographic_disclosure_status": result.get("geographic_disclosure_status"),
        "temporal_comparability_status": result.get("temporal_comparability_status"),
        "temporal_comparability_evidence_references": list(result.get("temporal_comparability_evidence_references") or []),
        "unit": definition["unit"],
        "comparison_group": definition.get("comparison_group"),
        "comparison_group_status": definition.get("comparison_group_status"),
        "comparison_group_evidence_references": list(definition.get("comparison_group_evidence_references") or []),
        "estimate": float(result["estimate"]),
        "display_estimate": display_estimate,
        "reported_estimate": result.get("reported_estimate", result["estimate"]),
        "eligible_observation_count": result.get("eligible_observation_count"),
        "uncertainty": {
            "standard_error": result.get("standard_error"),
            "confidence_interval": result.get("confidence_interval"),
            "unit": result.get("confidence_interval_unit"),
            "status": (result.get("reproducibility") or {}).get("uncertainty_status", "not_recorded"),
        },
        "limitations": limitations,
        "provenance": {
            "source_result_id": source_result_id,
            "dataset_id": result["dataset_id"],
            "dataset_release": result["dataset_release"],
            "definition_evidence_references": _definition_evidence(definition),
            "mapping_evidence_references": list((result.get("provenance") or {}).get("mapping_evidence_references") or []),
            "calculation_specification_evidence_references": list((result.get("provenance") or {}).get("calculation_specification_evidence_references") or []),
            "input_file_sha256": (result.get("provenance") or {}).get("input_file_sha256"),
            "calculated_at_utc": (result.get("provenance") or {}).get("calculated_at_utc"),
            "code_version": (result.get("reproducibility") or {}).get("code_version"),
            "calculation_specification_version": (result.get("reproducibility") or {}).get("calculation_specification_version"),
            "survey_design_method": (result.get("reproducibility") or {}).get("survey_design_method"),
            "variance_method": (result.get("reproducibility") or {}).get("variance_method"),
        },
        "validation_status": "pass",
        "analytical_eligibility": True,
        "publication_eligibility": readiness.get("publication_eligible") is True,
        "disclosure_status": result.get("disclosure_status"),
        "publication_status": result.get("publication_status"),
        "intended_use": intended_use,
        "data_classification": "synthetic_test_data" if synthetic else "authorized_aggregate",
        "result_artifact_written": False,
        "raw_records_included": False,
    }


def build_indicator_summary_figure(
    insight: dict[str, Any] | None,
    *,
    intended_use: str = "public_display",
) -> go.Figure | None:
    """Return a chart only for a verified insight approved for this use."""

    if not _chartable_insight(insight, intended_use=intended_use):
        return None
    assert isinstance(insight, dict)
    try:
        estimate = float(insight["display_estimate"])
    except (KeyError, TypeError, ValueError):
        return None
    if not isfinite(estimate):
        return None
    definition = insight.get("definition") or {}
    title = f"{definition.get('definition_text', insight.get('indicator_id', 'Verified indicator'))}"
    unit = str(insight.get("unit") or "value")
    period = insight.get("reference_period") or "Reference period not recorded"
    scope = insight.get("geographic_scope") or insight.get("population_scope") or "Scope not recorded"
    bar = go.Bar(
        x=[str(period)],
        y=[estimate],
        name=str(insight.get("indicator_id")),
        marker={"color": "#1769aa"},
        text=[f"{estimate:g} {unit}"],
        textposition="auto",
        customdata=[unit],
        hovertemplate="<b>%{x}</b><br>Estimate: %{y:g} %{customdata}<extra></extra>",
    )
    uncertainty = insight.get("uncertainty") if isinstance(insight.get("uncertainty"), dict) else {}
    interval = uncertainty.get("confidence_interval") if uncertainty.get("unit") == insight.get("unit") else None
    if isinstance(interval, dict) and interval.get("lower") is not None and interval.get("upper") is not None:
        try:
            lower = float(interval["lower"])
            upper = float(interval["upper"])
            if not (isfinite(lower) and isfinite(upper) and lower <= estimate <= upper):
                return None
            bar.error_y = {"type": "data", "array": [upper - estimate], "arrayminus": [estimate - lower], "visible": True}
        except (TypeError, ValueError):
            return None
    figure = go.Figure(bar)
    figure.update_layout(
        title=f"{title} · {scope}",
        yaxis_title=unit,
        xaxis_title="Reference period",
        showlegend=False,
        template="plotly_white",
        height=390,
        margin={"l": 56, "r": 24, "t": 72, "b": 56},
        font={"family": "Inter, sans-serif", "color": "#102a43"},
    )
    figure.update_yaxes(automargin=True, gridcolor="#e6edf3", zeroline=False)
    figure.update_xaxes(automargin=True)
    return figure


def build_verified_time_series_figure(
    insights: Iterable[dict[str, Any]] | None,
    *,
    intended_use: str = "public_display",
) -> go.Figure | None:
    """Build a trend only with explicit, evidence-backed period comparability.

    Input order is preserved as the approved period order; this function does
    not infer chronology, harmonization, or equivalence from period labels.
    Uncertainty is shown only when every point has a valid interval.
    """

    items = list(insights or [])
    if len(items) < 2 or any(not _chartable_insight(item, intended_use=intended_use) for item in items):
        return None
    first = items[0]
    identity_fields = ("indicator_id", "definition_version", "unit", "population_scope", "geographic_scope")
    if any(item.get(field) != first.get(field) for item in items for field in identity_fields):
        return None
    periods = [item.get("reference_period") for item in items]
    if any(not isinstance(period, str) or not period.strip() for period in periods) or len(set(periods)) != len(periods):
        return None
    if any(
        item.get("temporal_comparability_status") != "verified"
        or not isinstance(item.get("temporal_comparability_evidence_references"), list)
        or not all(isinstance(ref, str) and ref.strip() for ref in item["temporal_comparability_evidence_references"])
        or not item["temporal_comparability_evidence_references"]
        for item in items
    ):
        return None
    values: list[float] = []
    intervals: list[tuple[float, float] | None] = []
    for item in items:
        try:
            value = float(item["display_estimate"])
        except (KeyError, TypeError, ValueError):
            return None
        if not isfinite(value):
            return None
        values.append(value)
        uncertainty = item.get("uncertainty") if isinstance(item.get("uncertainty"), dict) else {}
        interval = uncertainty.get("confidence_interval") if uncertainty.get("unit") == item.get("unit") else None
        if uncertainty.get("confidence_interval") is not None and interval is None:
            return None
        if interval is None:
            intervals.append(None)
            continue
        try:
            lower, upper = float(interval["lower"]), float(interval["upper"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (isfinite(lower) and isfinite(upper) and lower <= value <= upper):
            return None
        intervals.append((lower, upper))
    if any(interval is None for interval in intervals) and not all(interval is None for interval in intervals):
        return None
    error_y: dict[str, Any] = {"visible": False}
    if all(interval is not None for interval in intervals):
        error_y = {
            "type": "data",
            "array": [interval[1] - value for interval, value in zip(intervals, values)],
            "visible": True,
        }
    definition = first.get("definition") if isinstance(first.get("definition"), dict) else {}
    unit = str(first.get("unit") or "value")
    figure = go.Figure(
        go.Scatter(
            x=periods,
            y=values,
            mode="lines+markers",
            name=str(first.get("indicator_id")),
            line={"color": "#1769aa", "width": 3},
            marker={"size": 9, "color": "#0d6572"},
            error_y=error_y,
            customdata=[unit] * len(periods),
            hovertemplate="<b>%{x}</b><br>Estimate: %{y:g} %{customdata}<extra></extra>",
        )
    )
    figure.update_layout(
        title=(
            f"{definition.get('definition_text', first.get('indicator_id'))} · "
            f"{first.get('geographic_scope') or first.get('population_scope') or 'scope not recorded'}"
        ),
        xaxis_title="Reference period (approved order)",
        yaxis_title=unit,
        template="plotly_white",
        height=410,
        margin={"l": 56, "r": 24, "t": 72, "b": 56},
        font={"family": "Inter, sans-serif", "color": "#102a43"},
        showlegend=False,
    )
    figure.update_yaxes(automargin=True, gridcolor="#e6edf3", zeroline=False)
    figure.update_xaxes(automargin=True)
    return figure


def build_verified_comparison_figure(
    insights: Iterable[dict[str, Any]] | None,
    *,
    intended_use: str = "public_display",
) -> go.Figure | None:
    """Build an unsorted comparison chart from compatible verified insights."""

    items = list(insights or [])
    if not items or any(not _chartable_insight(item, intended_use=intended_use) for item in items):
        return None
    first = items[0]
    keys = ("indicator_id", "definition_version", "unit", "reference_period")
    if any(item.get(key) != first.get(key) for item in items for key in keys):
        return None
    geographic_scopes = {item.get("geographic_scope") for item in items}
    if len(geographic_scopes) > 1:
        if any(
            item.get("geographic_validation_status") != "verified"
            or item.get("geographic_join_status") != "validated"
            or item.get("area_validation_status") != "pass"
            or not item.get("geographic_resource_id")
            or not item.get("geographic_resource_version")
            or item.get("geographic_disclosure_status") not in {"reviewed", "approved"}
            for item in items
        ):
            return None
        if len({item.get("geographic_resource_id") for item in items}) != 1 or len({item.get("geographic_resource_version") for item in items}) != 1:
            return None
    values: list[float] = []
    labels: list[str] = []
    intervals: list[tuple[float, float] | None] = []
    for item in items:
        try:
            value = float(item["display_estimate"])
        except (KeyError, TypeError, ValueError):
            return None
        if not isfinite(value):
            return None
        values.append(value)
        labels.append(str(item.get("geographic_scope") or item.get("population_scope") or "Scope not recorded"))
        uncertainty = item.get("uncertainty") if isinstance(item.get("uncertainty"), dict) else {}
        interval = uncertainty.get("confidence_interval") if uncertainty.get("unit") == item.get("unit") else None
        if uncertainty.get("confidence_interval") is not None and interval is None:
            return None
        if interval is None:
            intervals.append(None)
        else:
            try:
                lower, upper = float(interval["lower"]), float(interval["upper"])
            except (KeyError, TypeError, ValueError):
                return None
            if not (isfinite(lower) and isfinite(upper) and lower <= value <= upper):
                return None
            intervals.append((lower, upper))
    if any(interval is None for interval in intervals) and not all(interval is None for interval in intervals):
        return None
    error_y = {"visible": False}
    if all(interval is not None for interval in intervals):
        error_y = {
            "type": "data",
            "array": [interval[1] - value for interval, value in zip(intervals, values)],
            "arrayminus": [value - interval[0] for interval, value in zip(intervals, values)],
            "visible": True,
        }
    figure = go.Figure(go.Bar(
        x=labels,
        y=values,
        name=str(first.get("indicator_id")),
        marker={"color": "#1769aa"},
        text=[f"{value:g}" for value in values],
        textposition="auto",
        error_y=error_y,
        hovertemplate="<b>%{x}</b><br>Estimate: %{y:g}<extra></extra>",
    ))
    figure.update_layout(
        title=f"{(first.get('definition') or {}).get('definition_text', first.get('indicator_id'))} · comparison",
        yaxis_title=str(first.get("unit") or "value"),
        xaxis_title="Scope",
        showlegend=False,
        template="plotly_white",
        height=400,
        margin={"l": 58, "r": 24, "t": 72, "b": 64},
        font={"family": "Inter, sans-serif", "color": "#102a43"},
    )
    figure.update_yaxes(automargin=True, gridcolor="#e6edf3", zeroline=False)
    figure.update_xaxes(automargin=True)
    return figure


def build_verified_grouped_comparison_figure(
    insights: Iterable[dict[str, Any]] | None,
    *,
    intended_use: str = "public_display",
) -> go.Figure | None:
    """Compare indicators across categories only under approved group evidence.

    Each indicator must cover the same documented categories, period,
    population, geography, unit, and evidence-backed comparison group.
    """

    items = list(insights or [])
    if len(items) < 2 or any(not _chartable_insight(item, intended_use=intended_use) for item in items):
        return None
    first = items[0]
    group = first.get("comparison_group")
    if (
        not isinstance(group, str)
        or not group.strip()
        or first.get("comparison_group_status") != "verified"
        or not isinstance(first.get("comparison_group_evidence_references"), list)
        or not all(isinstance(ref, str) and ref.strip() for ref in first["comparison_group_evidence_references"])
        or not first["comparison_group_evidence_references"]
    ):
        return None
    common_fields = ("comparison_group", "comparison_group_status", "unit", "reference_period", "population_scope", "geographic_scope")
    if any(item.get(field) != first.get(field) for item in items for field in common_fields):
        return None
    categories: set[str] = set()
    indicators: dict[str, dict[str, float]] = {}
    intervals: dict[str, dict[str, tuple[float, float] | None]] = {}
    for item in items:
        indicator_id = item.get("indicator_id")
        category = item.get("comparison_category")
        if (
            item.get("comparison_group_status") != "verified"
            or not isinstance(item.get("comparison_group_evidence_references"), list)
            or not all(isinstance(ref, str) and ref.strip() for ref in item["comparison_group_evidence_references"])
            or not item["comparison_group_evidence_references"]
            or item.get("comparison_category_status") != "verified"
            or not isinstance(category, str)
            or not category.strip()
            or not isinstance(indicator_id, str)
        ):
            return None
        series = indicators.setdefault(indicator_id, {})
        if category in series:
            return None
        try:
            value = float(item["display_estimate"])
        except (KeyError, TypeError, ValueError):
            return None
        if not isfinite(value):
            return None
        if item.get("comparison_category_type") == "geography" and (
            item.get("geographic_validation_status") != "verified"
            or item.get("geographic_join_status") != "validated"
            or item.get("area_validation_status") != "pass"
            or not item.get("geographic_resource_id")
            or not item.get("geographic_resource_version")
            or item.get("geographic_disclosure_status") not in {"reviewed", "approved"}
        ):
            return None
        series[category] = value
        categories.add(category)
        uncertainty = item.get("uncertainty") if isinstance(item.get("uncertainty"), dict) else {}
        interval = uncertainty.get("confidence_interval") if uncertainty.get("unit") == first.get("unit") else None
        if uncertainty.get("confidence_interval") is not None and interval is None:
            return None
        if interval is None:
            intervals.setdefault(indicator_id, {})[category] = None
        else:
            try:
                lower, upper = float(interval["lower"]), float(interval["upper"])
            except (KeyError, TypeError, ValueError):
                return None
            if not (isfinite(lower) and isfinite(upper) and lower <= value <= upper):
                return None
            intervals.setdefault(indicator_id, {})[category] = (lower, upper)
    if len(indicators) < 2 or any(set(values) != categories for values in indicators.values()):
        return None
    has_intervals = [intervals[indicator][category] is not None for indicator in indicators for category in categories]
    if any(has_intervals) and not all(has_intervals):
        return None
    ordered_categories = list(dict.fromkeys(item["comparison_category"] for item in items))
    figure = go.Figure()
    for indicator_id, values in indicators.items():
        figure.add_bar(
            x=ordered_categories,
            y=[values[category] for category in ordered_categories],
            name=indicator_id,
            error_y=(
                {
                    "type": "data",
                    "array": [intervals[indicator_id][category][1] - values[category] for category in ordered_categories],
                    "arrayminus": [values[category] - intervals[indicator_id][category][0] for category in ordered_categories],
                    "visible": True,
                }
                if all(has_intervals)
                else {"visible": False}
            ),
            hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y:g}<extra></extra>",
        )
    figure.update_layout(
        barmode="group",
        title=f"Verified indicator comparison · {group}",
        xaxis_title="Verified comparison category",
        yaxis_title=str(first.get("unit") or "value"),
        template="plotly_white",
        height=420,
        margin={"l": 58, "r": 24, "t": 72, "b": 64},
        font={"family": "Inter, sans-serif", "color": "#102a43"},
        legend={"title": {"text": "Indicator"}},
    )
    figure.update_yaxes(automargin=True, gridcolor="#e6edf3", zeroline=False)
    figure.update_xaxes(automargin=True)
    return figure


def _chartable_insight(insight: dict[str, Any] | None, *, intended_use: str) -> bool:
    """Require the structured insight contract before a figure can be made."""

    if not isinstance(insight, dict) or intended_use not in SUPPORTED_USES:
        return False
    if insight.get("status") != "verified" or insight.get("insight_status") != "verified":
        return False
    if insight.get("validation_status") != "pass" or insight.get("analytical_eligibility") is not True:
        return False
    if insight.get("raw_records_included") is True or insight.get("data_classification") != "authorized_aggregate":
        return False
    if not isinstance(insight.get("source_result_id"), str) or not insight["source_result_id"].strip():
        return False
    if insight.get("intended_use") != intended_use:
        return False
    if intended_use == "public_display" and insight.get("publication_eligibility") is not True:
        return False
    definition = insight.get("definition")
    return (
        isinstance(definition, dict)
        and bool(definition.get("definition_text"))
        and bool(insight.get("indicator_id"))
        and bool(insight.get("definition_version"))
        and bool(insight.get("unit"))
        and bool(insight.get("provenance"))
    )


def interpret_verified_insight(insight: dict[str, Any] | None) -> dict[str, Any]:
    """Create a deterministic, non-causal interpretation for one insight."""

    if not isinstance(insight, dict) or insight.get("status") != "verified":
        blockers = insight.get("blockers") if isinstance(insight, dict) and isinstance(insight.get("blockers"), list) else []
        blocker_ids = [item.get("identifier") for item in blockers if isinstance(item, dict) and item.get("identifier")]
        next_actions = [item.get("next_action") for item in blockers if isinstance(item, dict) and item.get("next_action")]
        missing = ", ".join(str(item) for item in blocker_ids) if blocker_ids else "the verified aggregate result and its evidence-linked definition"
        action = " ".join(dict.fromkeys(str(item) for item in next_actions)) if next_actions else "Verify the exact-release source, mapping, method, quality checks, and publication review."
        return {
            "status": "blocked",
            "text": f"No verified interpretation is available. Missing or blocked evidence: {missing}. Next evidence needed: {action}",
            "source_result_id": insight.get("source_result_id") if isinstance(insight, dict) else None,
            "limitations": [],
            "blocker_ids": blocker_ids,
            "next_actions": list(dict.fromkeys(str(item) for item in next_actions)),
        }
    definition = insight.get("definition") or {}
    unit = insight.get("unit") or "value"
    scope = insight.get("geographic_scope") or insight.get("population_scope") or "the documented population scope"
    period = insight.get("reference_period") or "the documented reference period"
    estimate = insight.get("display_estimate")
    source = insight.get("provenance") if isinstance(insight.get("provenance"), dict) else {}
    uncertainty = insight.get("uncertainty") if isinstance(insight.get("uncertainty"), dict) else {}
    interval = uncertainty.get("confidence_interval")
    validated_interval = None
    if uncertainty.get("unit") == unit and isinstance(interval, dict):
        try:
            lower, upper, point = float(interval["lower"]), float(interval["upper"]), float(estimate)
            if all(isfinite(number) for number in (lower, upper, point)) and lower <= point <= upper:
                validated_interval = {"lower": lower, "upper": upper, "unit": unit}
        except (KeyError, TypeError, ValueError):
            pass
    text = (
        f"This descriptive result measures {definition.get('definition_text', insight.get('indicator_id'))} "
        f"for {scope} during {period}: {estimate} {unit}. It supports interpretation only within the approved definition, "
        "source release, and survey method. It does not establish a causal policy or programme effect, nor does it by itself "
        "demonstrate poverty reduction or policy effectiveness."
    )
    return {
        "status": "verified",
        "source_result_id": insight.get("source_result_id"),
        "text": text,
        "research_question": insight.get("research_question") or "Not recorded in the verified definition.",
        "indicator_definition": definition.get("definition_text"),
        "dataset_id": source.get("dataset_id") or insight.get("dataset_id"),
        "dataset_release": source.get("dataset_release") or insight.get("dataset_release"),
        "population_scope": insight.get("population_scope") or "Not recorded.",
        "reference_period": insight.get("reference_period") or "Not recorded.",
        "value": estimate,
        "unit": unit,
        "uncertainty": validated_interval,
        "limitations": list(insight.get("limitations") or []),
        "unsupported_claims": ["causal effects", "policy effectiveness", "poverty reduction impact"],
    }


def verified_filter_options(
    insights: Iterable[dict[str, Any]] | None,
    field: str,
    *,
    intended_use: str = "public_display",
) -> tuple[str, ...]:
    """Return filter choices present only in fully eligible insight records."""

    allowed_fields = {"indicator_id", "reference_period", "population_scope", "geographic_scope", "comparison_category"}
    if field not in allowed_fields or intended_use not in SUPPORTED_USES:
        return ()
    values: list[str] = []
    for insight in insights or ():
        if not _chartable_insight(insight, intended_use=intended_use):
            continue
        value = insight.get(field)
        if field == "comparison_category" and insight.get("comparison_category_status") != "verified":
            continue
        if field == "reference_period" and (
            insight.get("temporal_comparability_status") != "verified"
            or not isinstance(insight.get("temporal_comparability_evidence_references"), list)
            or not insight["temporal_comparability_evidence_references"]
            or not all(isinstance(ref, str) and ref.strip() for ref in insight["temporal_comparability_evidence_references"])
        ):
            continue
        if isinstance(value, str) and value.strip() and value not in values:
            values.append(value)
    return tuple(values)


def filter_verified_insights(
    insights: Iterable[dict[str, Any]] | None,
    *,
    filters: dict[str, str] | None = None,
    intended_use: str = "public_display",
) -> list[dict[str, Any]] | None:
    """Filter already-eligible records; invalid choices fail closed.

    This helper only narrows a result set. It cannot upgrade a record's
    analytical, disclosure, or publication status.
    """

    items = list(insights or ())
    criteria = filters or {}
    if not isinstance(criteria, dict) or any(
        not isinstance(field, str)
        or not isinstance(value, str)
        or value not in verified_filter_options(items, field, intended_use=intended_use)
        for field, value in criteria.items()
    ):
        return None
    eligible = [item for item in items if _chartable_insight(item, intended_use=intended_use)]
    return [item for item in eligible if all(item.get(field) == value for field, value in criteria.items())]


def build_phase17_status(
    phase14_status: dict[str, Any],
    definition: dict[str, Any] | None,
    *,
    intended_use: str = "public_display",
) -> dict[str, Any]:
    """Adapt current Phase 14 metadata into a safe Phase 17 dashboard status."""

    result = phase14_status.get("result") if isinstance(phase14_status, dict) else None
    insight = build_verified_insight(result, definition, intended_use=intended_use)
    if insight.get("status") == "blocked" and isinstance(phase14_status, dict):
        existing = list(insight.get("blockers") or [])
        known = {item.get("identifier") for item in existing}
        for item in phase14_status.get("blockers", []):
            if not isinstance(item, dict) or item.get("identifier") in known:
                continue
            existing.append(_blocker(str(item.get("identifier")), str(item.get("message")), str(item.get("next_action"))))
        insight["blockers"] = existing
        insight["blocker_ids"] = [item["identifier"] for item in existing]
        insight["next_actions"] = list(dict.fromkeys(item["next_action"] for item in existing))
    return insight


# Descriptive aliases for callers that use the phase objective terminology.
construct_verified_insight = build_verified_insight
create_verified_insight = build_verified_insight
build_summary_figure = build_indicator_summary_figure
interpret_insight = interpret_verified_insight

