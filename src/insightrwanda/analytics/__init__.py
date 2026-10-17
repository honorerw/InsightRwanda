"""Reusable analytical primitives for documented, approved indicators."""

from .catalogue import get_indicator, load_indicator_catalogue
from .authorized import (
    AuthorizedLoadResult,
    calculate_authorized_proportion,
    load_authorized_dataset,
    prepare_publication_aggregate,
)
from .geography import (
    GeographicJoinResult,
    GeographicResourceValidation,
    join_approved_geographic_aggregate,
    save_geographic_analysis_result,
    validate_area_comparison,
    validate_geographic_resource,
)
from .mappings import mapping_readiness, summarize_mapping_records, validate_mapping_records
from .indicators import (
    assert_indicator_calculable,
    calculate_proportion,
    calculate_weighted_proportion,
    validate_weights,
)
from .insights import (
    build_indicator_summary_figure,
    build_phase17_status,
    build_verified_time_series_figure,
    build_verified_grouped_comparison_figure,
    build_verified_comparison_figure,
    build_verified_insight,
    interpret_verified_insight,
)
from .exports import build_public_export_payload, validate_public_export
from .release import WORKFLOW_STAGES, build_phase18_status, save_workflow_audit
from .reproducibility import (
    append_audit_event,
    build_audit_event,
    build_phase20_status,
    build_reproducibility_manifest,
    canonical_json,
    canonical_sha256,
    compare_reproduced_results,
    detect_reproducibility_changes,
    validate_manifest,
)
from .readiness import ReadinessResult, evaluate_indicator_readiness

__all__ = [
    "assert_indicator_calculable",
    "AuthorizedLoadResult",
    "calculate_proportion",
    "calculate_authorized_proportion",
    "calculate_weighted_proportion",
    "get_indicator",
    "load_indicator_catalogue",
    "ReadinessResult",
    "evaluate_indicator_readiness",
    "GeographicJoinResult",
    "GeographicResourceValidation",
    "join_approved_geographic_aggregate",
    "save_geographic_analysis_result",
    "validate_area_comparison",
    "validate_geographic_resource",
    "mapping_readiness",
    "summarize_mapping_records",
    "validate_mapping_records",
    "load_authorized_dataset",
    "prepare_publication_aggregate",
    "validate_weights",
    "build_verified_insight",
    "build_indicator_summary_figure",
    "build_verified_time_series_figure",
    "build_verified_grouped_comparison_figure",
    "build_verified_comparison_figure",
    "interpret_verified_insight",
    "build_public_export_payload",
    "validate_public_export",
    "build_phase17_status",
    "WORKFLOW_STAGES",
    "build_phase18_status",
    "save_workflow_audit",
    "append_audit_event",
    "build_audit_event",
    "build_phase20_status",
    "build_reproducibility_manifest",
    "canonical_json",
    "canonical_sha256",
    "compare_reproduced_results",
    "detect_reproducibility_changes",
    "validate_manifest",
]

