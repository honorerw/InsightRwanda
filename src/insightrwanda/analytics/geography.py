"""Conservative geographic validation, joins, and survey-aware gates.

This module never infers geographic identity from names or row order. It
returns aggregate diagnostics only; joined frames are kept internal to the
caller and are never serialized by the result helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd

from insightrwanda.data.errors import IndicatorBlockedError
from insightrwanda.data.paths import resolve_approved_data_path, resolve_derived_output_path
from insightrwanda.data.validation import validate_geojson_structure

from .readiness import VERIFIED_STATUSES, ReadinessResult
from .validation import CHECK_STATUSES, ValidationCheck, ValidationReport, contains_forbidden_raw_keys


_CRS_PATTERN = re.compile(r"^(?:EPSG:\d+|CRS84)$", re.IGNORECASE)
_KNOWN_VARIANCE_METHODS = {"linearization", "replicate_weights", "taylor_linearization"}
_RAW_KEYS = {"records", "rows", "raw_records", "joined", "coordinates", "geometry"}
_VERIFIED_STATUSES = {"verified", "approved"}


def _check(
    check_id: str,
    description: str,
    status: str,
    required: str,
    explanation: str,
    prevents: bool,
    action: str,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=check_id,
        description=description,
        status=status,
        evidence_or_input_required=required,
        explanation=explanation,
        prevents_analytical_eligibility=prevents,
        corrective_action=action,
    )


def _report(checks: Iterable[ValidationCheck], *, allowed: bool) -> ValidationReport:
    items = tuple(checks)
    counts = {status: sum(item.status == status for item in items) for status in CHECK_STATUSES}
    if any(item.status == "blocked" for item in items):
        status = "blocked"
    elif any(item.status == "fail" for item in items):
        status = "fail"
    elif not items or all(item.status == "not_run" for item in items):
        status = "not_run"
    else:
        status = "pass"
    return ValidationReport(
        status=status,
        calculation_allowed=allowed and status == "pass",
        checks=items,
        summary={"check_count": len(items), "status_counts": counts},
    )


@dataclass(frozen=True)
class GeographicResourceValidation:
    """Safe validation outcome for one registered boundary resource."""

    status: str
    resource_id: str | None
    checks: tuple[ValidationCheck, ...]
    diagnostics: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "resource_id": self.resource_id,
            "checks": [item.as_dict() for item in self.checks],
            "diagnostics": dict(self.diagnostics),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class GeographicJoinResult:
    """Safe join decision with aggregate-only diagnostics."""

    status: str
    joined: pd.DataFrame | None = field(default=None, repr=False, compare=False)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    messages: tuple[str, ...] = ()

    @property
    def unmatched_aggregate_count(self) -> int:
        return int(self.diagnostics.get("unmatched_aggregate_count", 0))

    @property
    def unmatched_boundary_count(self) -> int:
        return int(self.diagnostics.get("unmatched_boundary_count", 0))

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "diagnostics": dict(self.diagnostics),
            "messages": list(self.messages),
        }


def _geojson_coordinate_values(value: Any) -> Iterable[tuple[float, float]]:
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:2]):
            yield float(value[0]), float(value[1])
            return
        for item in value:
            yield from _geojson_coordinate_values(item)


def _geometry_basic_valid(geometry: Any) -> bool:
    if not isinstance(geometry, dict) or not isinstance(geometry.get("type"), str):
        return False
    geometry_type = geometry["type"]
    if geometry_type == "GeometryCollection":
        geometries = geometry.get("geometries")
        return isinstance(geometries, list) and bool(geometries) and all(_geometry_basic_valid(item) for item in geometries)
    coordinates = geometry.get("coordinates")
    if coordinates in (None, [], ()):
        return False
    points = list(_geojson_coordinate_values(coordinates))
    return bool(points) and all(np.isfinite(value) for point in points for value in point)


def _resource_path(resource: dict[str, Any], project_root: str | Path | None) -> Path | None:
    source_path = resource.get("source_path")
    if not isinstance(source_path, str) or not source_path.strip() or project_root is None:
        return None
    try:
        return resolve_approved_data_path(Path("data") / source_path, project_root=project_root)
    except Exception:
        return None


def _load_document(resource: dict[str, Any], project_root: str | Path | None) -> tuple[dict[str, Any] | None, str | None]:
    path = _resource_path(resource, project_root)
    if path is None or path.suffix.lower() != ".geojson":
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), path.as_posix()
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, path.as_posix()


def validate_geographic_resource(
    resource: dict[str, Any] | None,
    *,
    project_root: str | Path | None = None,
    document: dict[str, Any] | None = None,
    allow_in_memory: bool = False,
    intended_use: str = "analysis",
    expected_administrative_level: str | None = None,
    expected_boundary_release: str | None = None,
    expected_reference_date: str | None = None,
) -> GeographicResourceValidation:
    """Validate resource metadata and basic GeoJSON structure.

    Topological geometry validity is intentionally blocked when the optional
    geospatial libraries are unavailable. Basic finite-coordinate checks are
    still performed without treating them as a substitute for topology.
    """

    resource = resource if isinstance(resource, dict) else {}
    resource_id = resource.get("resource_id") if isinstance(resource.get("resource_id"), str) else None
    checks: list[ValidationCheck] = []
    limitations: list[str] = []
    checks.append(_check(
        "resource_registered",
        "Resource is explicitly registered",
        "pass" if resource_id else "blocked",
        "A geographic resource registry record",
        "The resource has a stable identifier." if resource_id else "No geographic resource record was selected.",
        not bool(resource_id),
        "Register the intended official boundary resource before validation.",
    ))

    path = _resource_path(resource, project_root)
    in_memory = document is not None and allow_in_memory
    presence_status = "pass" if path is not None or in_memory else "blocked"
    checks.append(_check(
        "boundary_resource_presence",
        "Boundary resource exists in the approved scope",
        presence_status,
        "A regular local file below data/ or an explicitly labeled in-memory test fixture",
        "The registered resource is locally present." if path is not None else "The boundary file is missing from the approved data scope.",
        True,
        "Obtain the authorized boundary file through the approved channel and register its safe relative path.",
    ))

    provenance_ok = (
        resource.get("provenance_status") in _VERIFIED_STATUSES
        and isinstance(resource.get("source_url"), str)
        and isinstance(resource.get("producing_organization"), str)
        and bool(resource.get("evidence_references"))
    )
    checks.append(_check(
        "boundary_provenance",
        "Boundary provenance and source identity",
        "pass" if provenance_ok else "blocked",
        "Official source URL, producing organization, provenance status, and review evidence",
        "Source identity and provenance evidence are recorded." if provenance_ok else "Boundary provenance is missing or unverified; a checksum alone is insufficient.",
        not provenance_ok,
        "Record and independently review the official source, release, producing organization, and evidence references.",
    ))
    terms_ok = resource.get("license_status") in _VERIFIED_STATUSES and resource.get("permitted_use_status") in _VERIFIED_STATUSES
    checks.append(_check(
        "boundary_license_terms",
        "License and permitted-use review",
        "pass" if terms_ok else "blocked",
        "Reviewed license and intended-use terms",
        "License and permitted-use statuses are reviewed." if terms_ok else "Licensing or permitted-use evidence is not verified.",
        not terms_ok,
        "Obtain and review the applicable license and terms for analytical and map publication use.",
    ))
    checksum = resource.get("source_checksum")
    checksum_status = "not_applicable"
    checksum_explanation = "No source checksum was registered."
    if checksum is not None:
        checksum_status = "fail"
        checksum_explanation = "The registered checksum is malformed or the local file is unavailable."
        if isinstance(checksum, str) and re.fullmatch(r"[0-9a-fA-F]{64}", checksum) and path is not None:
            try:
                actual = sha256(path.read_bytes()).hexdigest()
                checksum_status = "pass" if actual.casefold() == checksum.casefold() else "fail"
                checksum_explanation = "The local file checksum matches the registered integrity value." if checksum_status == "pass" else "The local file checksum does not match the registered value."
            except OSError:
                checksum_status = "fail"
    checks.append(_check(
        "boundary_checksum_integrity",
        "Boundary file integrity checksum",
        checksum_status,
        "A safe file checksum where registered",
        checksum_explanation,
        checksum_status == "fail",
        "Reconcile the registered checksum with the approved boundary file; checksum does not establish authenticity or permission.",
    ))
    metadata_fields = (
        "administrative_level",
        "boundary_release",
        "reference_date",
        "coordinate_reference_system",
        "feature_id_field",
        "feature_name_field",
    )
    metadata_ok = all(isinstance(resource.get(field), str) and resource.get(field).strip() for field in metadata_fields)
    metadata_ok = metadata_ok and bool(_CRS_PATTERN.match(str(resource.get("coordinate_reference_system"))))
    for expected, actual in (
        (expected_administrative_level, resource.get("administrative_level")),
        (expected_boundary_release, resource.get("boundary_release")),
        (expected_reference_date, resource.get("reference_date")),
    ):
        if expected is not None and actual != expected:
            metadata_ok = False
    checks.append(_check(
        "boundary_metadata",
        "Administrative level, release, date, CRS, and feature fields",
        "pass" if metadata_ok else "blocked",
        "Documented boundary metadata matched to the intended analysis",
        "Required geographic metadata is complete and compatible." if metadata_ok else "Boundary level, version/date, CRS, or identifier metadata is incomplete or incompatible.",
        not metadata_ok,
        "Document the exact boundary level, release, reference date, CRS, identifier, and name fields.",
    ))

    loaded_document = document
    loaded_path: str | None = None
    if loaded_document is None:
        loaded_document, loaded_path = _load_document(resource, project_root)
    structure_ok = False
    features: list[dict[str, Any]] = []
    if loaded_document is not None:
        try:
            validate_geojson_structure(loaded_document)
            features = [item for item in loaded_document.get("features", []) if isinstance(item, dict)]
            structure_ok = bool(features) and len(features) == len(loaded_document.get("features", []))
        except Exception:
            structure_ok = False
    checks.append(_check(
        "boundary_schema",
        "Boundary container and feature schema",
        "pass" if structure_ok else "not_run" if loaded_document is None else "fail",
        "A validated GeoJSON FeatureCollection",
        "The GeoJSON container and feature objects are structurally valid." if structure_ok else "Boundary structure could not be validated.",
        not structure_ok,
        "Provide a supported FeatureCollection and validate it without exposing feature records.",
    ))

    id_field = resource.get("feature_id_field")
    identifiers: list[Any] = []
    id_ok = structure_ok and isinstance(id_field, str)
    if id_ok:
        for feature in features:
            properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
            value = properties.get(id_field)
            if value is None and id_field == "id":
                value = feature.get("id")
            identifiers.append(value)
        id_ok = all(value is not None and not (isinstance(value, str) and not value.strip()) for value in identifiers)
    duplicate_ids = len(identifiers) - len({str(value) for value in identifiers if value is not None}) if identifiers else 0
    checks.append(_check(
        "feature_identifiers",
        "Feature identifiers are present and unique",
        "pass" if id_ok and duplicate_ids == 0 else "not_run" if not structure_ok else "fail",
        "Documented feature identifier field and official code list",
        "All feature identifiers are present and unique." if id_ok and duplicate_ids == 0 else "Feature identifiers are missing or duplicated.",
        not (id_ok and duplicate_ids == 0),
        "Resolve missing/duplicate codes against the official geographic code list; never infer identity from row order or names.",
    ))

    geometry_ok = structure_ok and all(_geometry_basic_valid(feature.get("geometry")) for feature in features)
    checks.append(_check(
        "geometry_validity",
        "Geometry is non-empty and numerically finite",
        "pass" if geometry_ok else "not_run" if not structure_ok else "fail",
        "Geometry objects with finite, non-empty coordinates",
        "Basic geometry checks passed." if geometry_ok else "At least one geometry is empty, malformed, or contains non-finite coordinates.",
        not geometry_ok,
        "Repair or replace invalid geometries using an authorized source; do not silently omit features.",
    ))
    expected_types = set(resource.get("geometry_types") or [])
    observed_types = {
        feature.get("geometry", {}).get("type")
        for feature in features
        if isinstance(feature.get("geometry"), dict)
    }
    types_ok = not expected_types or observed_types.issubset(expected_types)
    checks.append(_check(
        "geometry_types",
        "Geometry types match documented resource metadata",
        "pass" if structure_ok and types_ok else "not_run" if not structure_ok else "fail",
        "Documented geometry type expectations",
        "Observed geometry types match the documented resource." if types_ok else "Observed geometry types are incompatible with the registered resource.",
        not (structure_ok and types_ok),
        "Confirm the release and documented geometry types before proceeding.",
    ))

    try:
        import shapely  # type: ignore  # noqa: F401
    except ImportError:
        topology_status = "blocked" if structure_ok else "not_run"
        limitations.append("Topological geometry validity is unsupported because no compatible geospatial geometry library is installed.")
    else:
        topology_status = "pass" if structure_ok else "not_run"
    checks.append(_check(
        "geometry_topology_support",
        "Topological geometry validity support",
        topology_status,
        "A compatible geometry library for topology validation",
        "Topology validation is supported." if topology_status == "pass" else "Topology validation cannot be claimed in the current environment.",
        topology_status == "blocked",
        "Install or approve a compatible geospatial dependency, then validate topology against the documented boundary release.",
    ))

    if intended_use == "public_visualization":
        disclosure = resource.get("disclosure_requirements")
        publication_ok = (
            resource.get("publication_status") in _VERIFIED_STATUSES
            and isinstance(disclosure, dict)
            and disclosure.get("status") in _VERIFIED_STATUSES
        )
        checks.append(_check(
            "boundary_publication",
            "Boundary visualization and disclosure approval",
            "pass" if publication_ok else "blocked",
            "Output-specific publication and disclosure review",
            "Boundary publication is separately approved." if publication_ok else "Boundary visualization publication or disclosure review is missing.",
            not publication_ok,
            "Record output-specific licensing, disclosure, attribution, and publication approval.",
        ))

    diagnostics = {
        "feature_count": len(features) if structure_ok else None,
        "duplicate_feature_identifier_count": max(duplicate_ids, 0),
        "observed_geometry_type_count": len(observed_types),
        "local_path_status": "present" if path is not None else "in_memory_test" if in_memory else "missing",
        "loaded_source_path_recorded": bool(loaded_path),
    }
    statuses = {item.status for item in checks}
    status = "blocked" if "blocked" in statuses else "fail" if "fail" in statuses else "verified" if all(item.status in {"pass", "not_applicable"} for item in checks) else "blocked"
    return GeographicResourceValidation(
        status=status,
        resource_id=resource_id,
        checks=tuple(checks),
        diagnostics=diagnostics,
        limitations=tuple(limitations),
    )


def _join_diagnostics(
    aggregate: pd.DataFrame | None,
    boundaries: pd.DataFrame | None,
    *,
    aggregate_key: str,
    boundary_key: str,
    expected_cardinality: str = "one_to_one",
) -> dict[str, Any]:
    return {
        "aggregate_record_count": int(len(aggregate)) if isinstance(aggregate, pd.DataFrame) else 0,
        "boundary_feature_count": int(len(boundaries)) if isinstance(boundaries, pd.DataFrame) else 0,
        "matched_identifier_count": 0,
        "unmatched_aggregate_count": 0,
        "unmatched_boundary_count": 0,
        "duplicate_aggregate_key_count": 0,
        "duplicate_boundary_key_count": 0,
        "unexpected_join_multiplicity": False,
        "final_joined_row_count": 0,
        "aggregate_key": aggregate_key,
        "boundary_key": boundary_key,
        "expected_cardinality": expected_cardinality,
    }


def join_approved_geographic_aggregate(
    aggregate: pd.DataFrame,
    boundaries: pd.DataFrame,
    *,
    dataset: dict[str, Any],
    aggregate_key: str,
    boundary_key: str,
    geographic_level: str,
    calculation_metadata: dict[str, Any],
    resource_metadata: dict[str, Any] | None = None,
    resource_validation: dict[str, Any] | None = None,
    expected_cardinality: str = "one_to_one",
    publication_requested: bool = False,
) -> GeographicJoinResult:
    """Join approved aggregates to verified boundaries with explicit keys."""

    diagnostics = _join_diagnostics(aggregate, boundaries, aggregate_key=aggregate_key, boundary_key=boundary_key, expected_cardinality=expected_cardinality)
    if not isinstance(aggregate, pd.DataFrame) or not isinstance(boundaries, pd.DataFrame):
        return _blocked("Aggregate results and boundaries must be tabular frames.", diagnostics)
    readiness = calculation_metadata.get("readiness") if isinstance(calculation_metadata.get("readiness"), dict) else {}
    explicit_eligibility = "analysis_eligible" in calculation_metadata or "readiness" in calculation_metadata
    analysis_eligible = (
        calculation_metadata.get("analysis_eligible") is True
        if "analysis_eligible" in calculation_metadata
        else readiness.get("analysis_eligible") is True
    )
    if explicit_eligibility and not analysis_eligible:
        return _blocked("Central analytical eligibility is false; no geographic join was performed.", diagnostics)
    if calculation_metadata.get("calculation_status") != "calculated":
        return _blocked("Only a successful approved aggregate calculation can be joined to geography.", diagnostics)
    input_validation = (calculation_metadata.get("validation") or {}).get("input_validation", {})
    validation_status = calculation_metadata.get("validation_status") or input_validation.get("status")
    if validation_status not in {"pass", "validated", "approved"}:
        return _blocked("The aggregate calculation has not passed validation.", diagnostics)
    legacy_resource_call = resource_validation is None and resource_metadata is None
    if not legacy_resource_call and (not isinstance(resource_validation, dict) or resource_validation.get("status") != "verified"):
        return _blocked("The boundary resource is not verified for analytical use.", diagnostics)
    resource_metadata = resource_metadata or {}
    if dataset.get("geography_status") not in VERIFIED_STATUSES:
        return _blocked("The source geographic identifier is not verified.", diagnostics)
    if dataset.get("geographic_crosswalk_status") not in VERIFIED_STATUSES:
        return _blocked("An approved geographic crosswalk is not verified.", diagnostics)
    if dataset.get("geographic_join_method") != "documented_identifier":
        return _blocked("Geographic joining requires the documented identifier method; names are not inferred keys.", diagnostics)
    if dataset.get("geographic_level") not in {None, geographic_level} or resource_metadata.get("administrative_level") not in {None, geographic_level}:
        return _blocked("The requested administrative level does not match the documented dataset and boundary resource.", diagnostics)
    dataset_release = dataset.get("geographic_boundary_release") or dataset.get("boundary_release")
    resource_release = resource_metadata.get("boundary_release")
    if dataset_release and resource_release and dataset_release != resource_release:
        return _blocked("Dataset and boundary release versions are incompatible.", diagnostics)
    if expected_cardinality != "one_to_one":
        diagnostics["unexpected_join_multiplicity"] = True
        return _blocked("Only the documented one-to-one aggregate-to-boundary cardinality is supported.", diagnostics)
    if publication_requested and (
        calculation_metadata.get("publication_eligible") is not True
        or resource_metadata.get("publication_status") not in VERIFIED_STATUSES
    ):
        return _blocked("Publication of the geographic aggregate and boundary is not approved.", diagnostics)
    if aggregate_key not in aggregate.columns or boundary_key not in boundaries.columns:
        return _blocked("The aggregate and boundary identifier columns are not both present.", diagnostics)
    if str(aggregate[aggregate_key].dtype) != str(boundaries[boundary_key].dtype):
        return _blocked("Aggregate and boundary identifiers have incompatible data types; no implicit recoding is performed.", diagnostics)
    aggregate_keys = aggregate[aggregate_key]
    boundary_keys = boundaries[boundary_key]
    diagnostics["duplicate_aggregate_key_count"] = int(aggregate_keys.duplicated(keep=False).sum())
    diagnostics["duplicate_boundary_key_count"] = int(boundary_keys.duplicated(keep=False).sum())
    if aggregate_keys.isna().any() or boundary_keys.isna().any():
        return _blocked("Missing geographic identifiers cannot be joined safely.", diagnostics)
    if diagnostics["duplicate_aggregate_key_count"] or diagnostics["duplicate_boundary_key_count"]:
        diagnostics["unexpected_join_multiplicity"] = True
        return _blocked("Duplicate geographic identifiers create unexpected join multiplicity.", diagnostics)
    aggregate_set = set(aggregate_keys.tolist())
    boundary_set = set(boundary_keys.tolist())
    unmatched_aggregate = len(aggregate_set - boundary_set)
    unmatched_boundary = len(boundary_set - aggregate_set)
    diagnostics.update({
        "matched_identifier_count": len(aggregate_set & boundary_set),
        "unmatched_aggregate_count": unmatched_aggregate,
        "unmatched_boundary_count": unmatched_boundary,
    })
    if unmatched_aggregate or unmatched_boundary:
        return _blocked("Geographic coverage is incomplete; no join was returned.", diagnostics)
    try:
        joined = boundaries.merge(
            aggregate,
            left_on=boundary_key,
            right_on=aggregate_key,
            how="left",
            validate=expected_cardinality,
        )
    except (KeyError, pd.errors.MergeError, TypeError, ValueError):
        diagnostics["unexpected_join_multiplicity"] = True
        return _blocked("The documented geographic join could not be validated.", diagnostics)
    diagnostics["final_joined_row_count"] = int(len(joined))
    return GeographicJoinResult(status="validated", joined=joined, diagnostics=diagnostics)


def validate_area_comparison(
    *,
    readiness: ReadinessResult | dict[str, Any] | None,
    join_result: GeographicJoinResult | dict[str, Any] | None,
    survey_design: dict[str, Any] | None,
    disclosure_requirements: dict[str, Any] | None,
    calculation_metadata: dict[str, Any] | None = None,
    uncertainty_requested: bool = False,
    ranking_requested: bool = False,
    publication_requested: bool = False,
) -> ValidationReport:
    """Validate method support before any area comparison or uncertainty output."""

    readiness_dict = readiness.as_dict() if isinstance(readiness, ReadinessResult) else readiness or {}
    if readiness_dict.get("analysis_eligible") is not True:
        return _report((
            _check("central_analytical_eligibility", "Central analytical eligibility", "blocked", "The central readiness evaluator", "The geographic analysis is not analytically eligible.", True, "Resolve central source, indicator, geographic, and survey-design blockers."),
            _check("area_comparison_inputs", "Area comparison prerequisites", "not_run", "Eligible aggregate geography and documented method", "Area comparison checks did not run because central eligibility is false.", True, "Resolve central analytical eligibility first."),
        ), allowed=False)
    join_dict = join_result.as_dict() if isinstance(join_result, GeographicJoinResult) else join_result or {}
    join_ok = join_dict.get("status") == "validated"
    checks: list[ValidationCheck] = [
        _check("central_analytical_eligibility", "Central analytical eligibility", "pass", "The central readiness evaluator", "Central analytical eligibility is true.", False, "No action required."),
        _check("geographic_join", "Validated aggregate-to-boundary join", "pass" if join_ok else "blocked", "A validated one-to-one geographic join", "The geographic join passed aggregate diagnostics." if join_ok else "The geographic join is missing or failed diagnostics.", True, "Resolve geographic identifiers, coverage, versions, and join multiplicity."),
    ]
    design = survey_design if isinstance(survey_design, dict) else {}
    design_ok = (
        design.get("status") == "approved"
        and design.get("point_estimate_supported") is True
        and design.get("domain_estimation_supported") is True
        and design.get("weights_documented") is True
        and design.get("strata_documented") is True
        and design.get("clusters_documented") is True
        and isinstance(design.get("sampling_design"), str)
        and isinstance(design.get("domain_estimation_method"), str)
        and bool(design.get("domain_estimation_method"))
    )
    checks.append(_check("survey_domain_method", "Survey-aware geographic domain estimation", "pass" if design_ok else "blocked", "Approved domain/subpopulation estimation method, sampling design, and point-estimate support", "The documented survey design supports geographic domain estimates." if design_ok else "Survey-aware geographic domain estimation is not documented and supported.", True, "Obtain statistician-reviewed domain estimation guidance; do not substitute naive grouped estimates."))
    variance_ok = design_ok and design.get("variance_estimation_supported") is True and design.get("variance_method") in _KNOWN_VARIANCE_METHODS
    checks.append(_check("variance_method_support", "Design-based variance estimation", "pass" if variance_ok else "blocked" if uncertainty_requested else "not_applicable", "Approved strata, clusters, weights, and variance method" if uncertainty_requested else "An uncertainty request", "The documented variance method supports uncertainty output." if variance_ok else "Uncertainty output is not supported by the documented survey design.", uncertainty_requested and not variance_ok, "Implement or approve the design-based variance method before reporting standard errors or confidence intervals."))
    reliability = design.get("small_area_reliability_status")
    checks.append(_check("small_area_reliability", "Small-area reliability review", "pass" if reliability in {"reviewed", "approved", "verified"} else "blocked", "Approved small-area reliability rule without an invented threshold", "Small-area reliability rules are reviewed." if reliability in {"reviewed", "approved", "verified"} else "No approved small-area reliability rule is recorded.", True, "Have a survey statistician document effective sample-size and reliability review requirements."))
    if ranking_requested:
        multiple_comparison = design.get("multiple_comparison_method")
        checks.append(_check("multiple_comparison_method", "Multiple-comparison treatment", "pass" if isinstance(multiple_comparison, str) and multiple_comparison else "blocked", "Approved multiple-comparison method", "A multiple-comparison method is documented." if isinstance(multiple_comparison, str) and multiple_comparison else "Rankings were requested without an approved multiple-comparison method.", True, "Obtain methodological approval before producing rankings or league tables."))
    else:
        checks.append(_check("multiple_comparison_method", "Multiple-comparison treatment", "not_applicable", "A ranking or multiple-comparison request", "No ranking was requested.", False, "No action required."))
    disclosure_fields = ("small_area_rule", "sensitive_combination_review", "geographic_detail_review", "export_review")
    disclosure_ok = (
        isinstance(disclosure_requirements, dict)
        and disclosure_requirements.get("status") in {"reviewed", "approved", "verified"}
        and all(disclosure_requirements.get(field) not in (None, "", []) for field in disclosure_fields)
    )
    checks.append(_check("disclosure_requirements", "Geographic disclosure review", "pass" if disclosure_ok else "blocked", "Documented review for small areas, sensitive combinations, geographic detail, and exports", "Geographic disclosure requirements are reviewed." if disclosure_ok else "Geographic disclosure requirements are missing or unreviewed.", True, "Record output-specific disclosure review; do not invent a small-area threshold."))
    if publication_requested:
        publication_ok = isinstance(calculation_metadata, dict) and calculation_metadata.get("publication_eligible") is True
        checks.append(_check("publication_approval", "Geographic publication approval", "pass" if publication_ok else "blocked", "Separate output-level publication approval", "Publication is approved." if publication_ok else "Publication approval is false or missing.", True, "Complete separate licensing, attribution, disclosure, and publication review."))
    else:
        checks.append(_check("publication_approval", "Geographic publication approval", "not_applicable", "A publication request", "No public visualization or export was requested.", False, "No action required."))
    return _report(checks, allowed=not any(item.status in {"fail", "blocked"} for item in checks))


def save_geographic_analysis_result(
    result: dict[str, Any],
    *,
    project_root: str | Path,
    output_path: str | Path = "artifacts/phase16_geographic_result.json",
) -> Path:
    """Persist only validated aggregate geographic diagnostics."""

    if not isinstance(result, dict) or result.get("status") != "validated" or result.get("analysis_eligible") is not True:
        raise IndicatorBlockedError("Only an analytically eligible validated geographic result may be persisted.")
    if (
        result.get("data_classification") in {"synthetic_test_data", "synthetic_test_only"}
        or result.get("is_synthetic") is True
    ) and (Path(project_root).resolve() / "data" / "metadata" / "dataset_registry.json").is_file():
        raise IndicatorBlockedError("Synthetic test results cannot be persisted as geographic research artifacts.")
    if contains_forbidden_raw_keys(result) or result.get("raw_records_included") is True:
        raise IndicatorBlockedError("Geographic result artifacts cannot contain raw rows, geometries, or coordinates.")
    join_validation = result.get("join_validation") or {}
    area_validation = result.get("area_validation") or {}
    if join_validation.get("status") != "validated" or area_validation.get("status") != "pass":
        raise IndicatorBlockedError("Geographic result validation is incomplete.")
    output = resolve_derived_output_path(output_path, project_root=project_root)
    safe_result = json.loads(json.dumps(result, sort_keys=True))
    safe_result["result_artifact_written"] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(safe_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _blocked(message: str, diagnostics: dict[str, Any] | None = None) -> GeographicJoinResult:
    return GeographicJoinResult(status="blocked", diagnostics=diagnostics or {}, messages=(message,))


__all__ = [
    "GeographicJoinResult",
    "GeographicResourceValidation",
    "join_approved_geographic_aggregate",
    "save_geographic_analysis_result",
    "validate_area_comparison",
    "validate_geographic_resource",
]
