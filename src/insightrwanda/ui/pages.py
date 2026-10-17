"""Page renderers for the InsightRwanda Streamlit application."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pandas as pd

import plotly.graph_objects as go
import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from insightrwanda.data.loaders import load_geojson
from insightrwanda.data.quality import profile_geojson
from insightrwanda.analytics.phase12 import build_phase12_status
from insightrwanda.analytics.phase13 import build_phase13_status
from insightrwanda.analytics.phase14 import build_phase14_status, load_saved_calculation_result
from insightrwanda.analytics.geography import validate_geographic_resource
from insightrwanda.analytics.insights import build_indicator_summary_figure, build_phase17_status
from insightrwanda.analytics.local_material import (
    load_supplied_financial_inclusion,
    local_material_authorization,
    supplied_material_inventory,
    verified_codebook,
)
from insightrwanda.analytics.release import build_phase18_status
from insightrwanda.data.geography import summarize_geographic_resources
from .visualizations import build_evidence_status_figure, build_metadata_count_figure

from .components import (
    empty_state,
    indicator_card,
    metric_card,
    page_header,
    render_blocker_cards,
    render_catalogue_table,
    render_domain_card,
    build_evidence_blocker_records,
    build_indicator_readiness_summary,
    build_readiness_blocker_records,
    prepare_researcher_action_plan,
    render_indicator_readiness_summary,
    render_readiness_blocker_groups,
    render_researcher_action_plan,
    render_research_narrative,
    render_workflow_step,
    render_verified_result_filters,
    section_header,
)
from .metadata import (
    catalogue_summary,
    catalogue_readiness_summary,
    evaluate_catalogue_indicator,
    inventory_summary,
    load_dashboard_metadata,
    status_label,
)
from insightrwanda.data.registry import get_dataset, registry_summary


_BOUNDARY_REFERENCE_OPTIONS = {
    "Districts · simplified": Path("data/geo/rw_districts_adm2_simplified.geojson"),
    "Provinces · simplified": Path("data/geo/rw_provinces_adm1_simplified.geojson"),
}


def _metadata(project_root: Path):
    return load_dashboard_metadata(project_root)


def _authorized_local_inputs(metadata: Any, project_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    """Apply the recorded local authorization to UI-only readiness inputs."""

    registry = {key: dict(value) for key, value in metadata.registry.items()}
    source_verification = copy.deepcopy(metadata.source_verification)
    authorization = local_material_authorization(project_root)
    status = authorization.get("status")
    if status not in {"authorized_for_analysis", "authorized_for_analysis_and_publication"}:
        return registry, source_verification

    dataset = registry.get("local_dataset_stata")
    if dataset is not None:
        dataset["authorization_status"] = status
        dataset["permitted_processing_purpose"] = authorization.get("permitted_processing_purpose")
        # This is a local-analysis authorization override only. Other readiness
        # checks still decide whether a formal verified result is eligible.
        dataset["analytical_eligibility"] = True
    if isinstance(source_verification, dict):
        for source in source_verification.get("sources", []):
            if isinstance(source, dict) and source.get("dataset_id") == "local_dataset_stata":
                source["permission_status"] = "verified"
                source["access_authorization_status"] = "verified"
                source["analysis_approval_status"] = "verified"
    return registry, source_verification


def _phase13(metadata: Any, project_root: Path, dataset_id: str = "local_dataset_stata") -> dict[str, Any]:
    registry, source_verification = _authorized_local_inputs(metadata, project_root)
    return build_phase13_status(
        project_root,
        registry,
        metadata.catalogue,
        metadata.evidence,
        source_verification,
        dataset_id=dataset_id,
    )


def _phase14(metadata: Any, project_root: Path, dataset_id: str = "local_dataset_stata") -> dict[str, Any]:
    """Use the central Phase 14 evaluator and, only when valid, its saved aggregate."""

    registry, source_verification = _authorized_local_inputs(metadata, project_root)
    status = build_phase14_status(
        project_root,
        registry,
        metadata.catalogue,
        source_verification,
        dataset_id=dataset_id,
    )
    saved = load_saved_calculation_result(project_root)
    if saved and (status.get("readiness") or {}).get("analysis_eligible") is True:
        status["result"] = saved
        status["calculation_status"] = "calculated"
        status["status"] = "calculated"
    return status


def _phase17(metadata: Any, project_root: Path, phase14: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the insight decision from current Phase 14 state and catalogue metadata."""

    phase14_status = phase14 or _phase14(metadata, project_root)
    definition = metadata.catalogue.get("FI-ACCESS-001")
    return build_phase17_status(phase14_status, definition, intended_use="public_display")


def _phase18(metadata: Any, project_root: Path, dataset_id: str = "local_dataset_stata") -> dict[str, Any]:
    """Build the metadata-only end-to-end audit from current dashboard inputs."""

    registry, source_verification = _authorized_local_inputs(metadata, project_root)
    return build_phase18_status(
        project_root,
        registry,
        metadata.catalogue,
        metadata.evidence,
        source_verification,
        inventory=metadata.inventory,
        geographic_resources=list(metadata.geographic_resources),
        dataset_id=dataset_id,
        indicator_id="FI-ACCESS-001",
        intended_use="public_display",
    )


def _selected_dataset_id() -> str | None:
    selected = st.session_state.get("selected_dataset_id")
    return selected if isinstance(selected, str) and selected else None


def _catalogue_count_label(metadata: Any, count: int) -> str:
    """Avoid displaying an empty-catalogue zero when validation failed."""

    return "Unavailable" if metadata.catalogue_error else str(count)


def _publication_status_label(metadata: Any, readiness_summary: dict[str, int]) -> str:
    """Render publication state from readiness metadata, never a fabricated result."""

    if metadata.catalogue_error:
        return "Unavailable"
    return "Eligible" if readiness_summary["publication_eligible_count"] else "Not eligible"


def _research_readiness_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    """Convert machine-readable gates into safe, compact UI rows."""

    rows = []
    for requirement in report.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        rows.append(
            {
                "Requirement": str(requirement.get("requirement", "Unavailable")).replace("_", " ").title(),
                "Status": str(requirement.get("status", "unavailable")).replace("_", " ").title(),
                "Next action": str(requirement.get("next_action", "Review the readiness report.")),
            }
        )
    return rows


def financial_inclusion_filter_options(definitions: list[dict[str, Any]]) -> tuple[tuple[str, str | None], ...]:
    """Build selector options from catalogue metadata only."""

    options: list[tuple[str, str | None]] = [("All candidate concepts", None)]
    for definition in definitions:
        indicator_id = str(definition.get("indicator_id", ""))
        display_name = str(definition.get("display_name", "Unnamed indicator"))
        if indicator_id:
            options.append((f"{display_name} · {indicator_id}", indicator_id))
    return tuple(options)


def filter_indicator_definitions(
    definitions: list[dict[str, Any]], selected_indicator_id: str | None
) -> list[dict[str, Any]]:
    """Filter catalogue definitions without loading or calculating source data."""

    if selected_indicator_id is None:
        return list(definitions)
    return [
        definition
        for definition in definitions
        if definition.get("indicator_id") == selected_indicator_id
    ]


def available_boundary_options(project_root: Path) -> dict[str, Path]:
    """Return only known boundary references that exist below the project data root."""

    root = Path(project_root).resolve()
    return {
        label: relative_path
        for label, relative_path in _BOUNDARY_REFERENCE_OPTIONS.items()
        if (root / relative_path).is_file()
    }


def _safe_docs_link(project_root: Path, relative_path: str) -> str:
    path = project_root / relative_path
    return relative_path if path.is_file() else f"{relative_path} (not found)"


def _pretty_status(value: Any) -> str:
    """Render metadata states consistently without implying approval."""

    return str(value if value is not None else "unavailable").replace("_", " ").title()


def _metadata_status_table(records: list[dict[str, Any]], fields: list[tuple[str, str]]) -> None:
    """Render a compact table from already-validated metadata records."""

    rows = []
    for record in records:
        row = {}
        for label, field in fields:
            value = record.get(field, "Unavailable")
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            row[label] = _pretty_status(value) if field.endswith("_status") else value
        rows.append(row)
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        empty_state("No metadata records", "No validated metadata records are available for this view.", tone="blocked")


def render_overview(project_root: Path) -> None:
    metadata = _metadata(project_root)
    summary = catalogue_summary(metadata.catalogue)
    readiness_summary = catalogue_readiness_summary(metadata)
    page_header(
        "InsightRwanda · policy intelligence",
        "Evidence for better financial inclusion decisions.",
        "A disciplined workspace for exploring authorized evidence on financial access and poverty reduction in Rwanda. The foundation is ready; verified analytical outputs are still under review.",
    )
    st.markdown(
        "<div class='status-row'><span class='status-pill blocked'>"
        "Foundation mode · results not yet verified</span></div>",
        unsafe_allow_html=True,
    )

    metrics = st.columns(4, gap="medium")
    with metrics[0]:
        metric_card("Analysis-ready indicators", _catalogue_count_label(metadata, readiness_summary["analysis_eligible_count"]), "Eligibility requires explicit evidence")
    with metrics[1]:
        metric_card("Candidate concepts", _catalogue_count_label(metadata, summary["indicator_count"]), "Reviewable definitions, not estimates")
    with metrics[2]:
        metric_card("Publication status", _publication_status_label(metadata, readiness_summary), "No current indicator is approved for publication")
    with metrics[3]:
        metric_card("Registered datasets", str(registry_summary(metadata.registry)["dataset_count"]), "Metadata only; selection never loads a source")

    st.divider()
    section_header("Judge walkthrough", "A guided tour of the evidence pathway", "This presentation aid follows the live application state and does not change readiness or hide blockers.")
    presentation_steps = (
        ("1 · Research problem and public value", "The project is designed to support evidence on financial inclusion and poverty reduction; no verified research estimate is currently available.", "app_pages/overview.py", "Start at Overview"),
        ("2 · Architecture and data flow", "The application moves from registered source metadata through evidence, readiness, validation, analysis, and separate publication review.", "app_pages/research_readiness.py", "View Research Readiness"),
        ("3 · Provenance and authorization", "Show the source evidence and authorization requirements. A catalogue URL or local file alone does not grant permission.", "app_pages/evidence_provenance.py", "View Evidence & Provenance"),
        ("4 · Indicator and methodology", "FI-ACCESS-001 remains a candidate until its exact-release definition, mappings, and survey method are verified.", "app_pages/financial_inclusion.py", "View Financial Inclusion"),
        ("5 · Available findings", "Only eligible aggregate results can produce research charts. The current state has none; synthetic test fixtures are not findings.", "app_pages/poverty_insights.py", "View Poverty Insights"),
        ("6 · Geographic and statistical safeguards", "Geographic outputs require verified boundary provenance, compatible joins, supported survey methods, and separate disclosure review.", "app_pages/geographic_analysis.py", "View Geographic Analysis"),
        ("7 · Reproducibility and integrity", "Manifests and integrity checks trace approved inputs but do not prove authorization or statistical correctness.", "app_pages/research_readiness.py", "Review readiness details"),
        ("8 · Limitations and next evidence", "Real analysis requires authorized exact-release data, reviewed documentation, approved methods, passing quality checks, and distinct publication approval.", "app_pages/reports_exports.py", "View export gate"),
    )
    presentation_label = st.selectbox("Walkthrough step", [step[0] for step in presentation_steps], key="judge_walkthrough_step")
    selected_step = next(step for step in presentation_steps if step[0] == presentation_label)
    st.info(selected_step[1])
    try:
        st.page_link(selected_step[2], label=selected_step[3], icon=":material/arrow_forward:")
    except StreamlitPageNotFoundError:
        st.caption(f"{selected_step[3]} · use the sidebar navigation")

    st.divider()
    section_header("How the platform works", "A reviewable path from source to decision", "Every future result should carry its definition, provenance, weighting approach, and limitations.")
    workflow = st.columns(4, gap="medium")
    with workflow[0]:
        render_workflow_step("01", "Source review", "Confirm provenance, authorization, sensitivity, and permitted use before analysis.")
    with workflow[1]:
        render_workflow_step("02", "Quality checks", "Profile structure, missingness, weights, identifiers, and limitations without exposing records.")
    with workflow[2]:
        render_workflow_step("03", "Indicator review", "Define numerators, denominators, populations, and survey-design requirements.")
    with workflow[3]:
        render_workflow_step("04", "Decision context", "Present only approved aggregate evidence with clear uncertainty and interpretation cautions.")

    st.divider()
    section_header("Explore the workspace", "Built for transparent policy questions", "The sections below are ready for verified data when the evidence and permissions are in place.")
    domains = st.columns(2, gap="large")
    with domains[0]:
        render_domain_card("Financial inclusion", "Account access, savings, credit, digital services, and barriers — currently candidate concepts only.", "app_pages/financial_inclusion.py", "Open financial inclusion")
        render_domain_card("Poverty insights", "An approved poverty definition and source methodology are required before any estimate can be shown.", "app_pages/poverty_insights.py", "Open poverty insights")
    with domains[1]:
        boundary_message = (
            "Boundary reference files are available, but analytical joins and district estimates are not verified."
            if available_boundary_options(project_root)
            else "No boundary reference file is currently available; geographic joins and district estimates remain blocked."
        )
        render_domain_card("Geographic analysis", boundary_message, "app_pages/geographic_analysis.py", "Open geographic analysis")
        render_domain_card("Data quality", "Review aggregate inventory and catalogue readiness without loading source datasets.", "app_pages/data_quality.py", "Open data quality")

    st.divider()
    section_header("Current readiness", "A deliberately honest starting point")
    if metadata.catalogue_error:
        st.warning(metadata.catalogue_error)
    else:
        empty_state(
            "No verified analytical outputs yet",
            "The catalogue currently contains proposed or blocked concepts only. A real result will appear only after an authorized source, verified codebook mapping, dataset-specific survey design, and domain review are recorded.",
        )
    readiness_figure = build_evidence_status_figure(metadata.research_readiness)
    if readiness_figure is not None:
        section_header(
            "Evidence coverage",
            "What is recorded and what still needs review",
            "Counts are evidence-register statuses, not survey observations or research findings.",
        )
        st.plotly_chart(readiness_figure, width="stretch", config={"displayModeBar": False, "responsive": True})
        st.caption("Status labels and counts are shown directly; a provided document does not become verified until reviewed.")
    st.caption(
        f"Methodology: {_safe_docs_link(project_root, 'docs/indicator-methodology.md')} · "
        f"Governance: {_safe_docs_link(project_root, 'docs/data-governance.md')}"
    )


def render_financial_inclusion(project_root: Path) -> None:
    metadata = _metadata(project_root)
    page_header(
        "Analytical area",
        "Financial inclusion",
        "A structured view of access, use, and barriers to financial services using your authorized local material.",
    )
    local_result = load_supplied_financial_inclusion(str(project_root))
    local_authorization = local_material_authorization(project_root)
    local_analysis_active = (
        local_result.status == "exploratory"
        and bool(local_result.national)
        and local_authorization.get("status") in {"authorized_for_analysis", "authorized_for_analysis_and_publication"}
    )
    _render_supplied_local_material(project_root)
    definitions = [item for item in metadata.catalogue.values() if str(item.get("indicator_id", "")).startswith("FI-")]
    if metadata.catalogue_error:
        st.error(metadata.catalogue_error)
        return
    selected_id = _selected_dataset_id()
    active_dataset_id = "local_dataset_stata"
    dashboard_registry, _ = _authorized_local_inputs(metadata, project_root)
    selected_dataset = get_dataset(dashboard_registry, active_dataset_id)
    phase12 = build_phase12_status(
        dashboard_registry,
        metadata.catalogue,
        project_root=project_root,
        dataset_id=active_dataset_id,
    )
    if selected_dataset is None:
        st.info("The supplied local material remains available below; no matching registry metadata was found for the formal review panel.")
    else:
        st.info(f"Using supplied dataset: {selected_dataset.get('display_name', 'Unavailable')}. The authorized local-material analysis is shown below.")
    if not definitions:
        empty_state("No financial-inclusion concepts found", "The catalogue does not currently contain financial-inclusion entries.")
        return
    phase13 = _phase13(metadata, project_root, dataset_id=active_dataset_id)
    phase14 = _phase14(metadata, project_root, dataset_id=active_dataset_id)
    phase17 = _phase17(metadata, project_root, phase14)
    fi_readiness = phase13.get("readiness") or {}
    readiness_report = metadata.research_readiness
    blocker_records = build_readiness_blocker_records(
        fi_readiness,
        readiness_report,
        indicator_id="FI-ACCESS-001",
        dataset_id=active_dataset_id,
        include_geography=False,
    )
    indicator_summary = build_indicator_readiness_summary(
        phase13,
        phase14,
        indicator_id="FI-ACCESS-001",
        blocker_count=len(blocker_records) if readiness_report is not None else None,
    )
    if local_analysis_active:
        section_header(
            "Local analysis status",
            "Authorization recognized",
            "The supplied dataset.dta is authorized and already used above. The formal publication gate is separate and does not block this local analysis.",
        )
        st.success("Authorized local analysis is active for data/mine/dataset.dta.")
    else:
        section_header(
            "FI-ACCESS-001 · readiness",
            "Indicator status and evidence blockers",
            "This summary is derived from the existing central readiness decision. It reports no estimate until a valid aggregate result exists.",
        )
        render_indicator_readiness_summary(
            **indicator_summary,
        )
        st.caption("Local-data status: authorized and used above. The separate verified-result and publication status remains under methodological review.")
        section_header(
            "Formal result review",
            "Evidence and required actions for official publication",
            "These cards describe the separate formal result and publication review. They do not deny your permission to use the supplied dataset locally.",
        )
        render_readiness_blocker_groups(blocker_records)
        action_tasks = prepare_researcher_action_plan(
            (readiness_report or {}).get("researcher_action_plan"),
            indicator_id="FI-ACCESS-001",
            dataset_id=active_dataset_id,
            include_geography=False,
        )
        section_header(
            "Researcher action plan",
            "What to resolve next",
            "Tasks and statuses come from the existing evidence register; a task is not complete until its supporting evidence is verified.",
        )
        render_researcher_action_plan(action_tasks)
    section_header(
        "Formal verified-result gate",
        "Local authorized result shown above" if phase14.get("calculation_status") != "calculated" else "Approved aggregate result",
        "The local authorized analysis is separate from the central verified-result artifact and publication workflow.",
    )
    if phase14.get("calculation_status") != "calculated":
        st.info("Your authorized local analysis is available above. No separate official aggregate artifact has been approved or written yet.")
    else:
        if phase17.get("status") == "verified":
            st.metric(
                "Verified research metric",
                f"{phase17.get('display_estimate')} {phase17.get('unit')}",
                label_visibility="visible",
            )
            st.caption("Displayed only after central analytical, disclosure, and publication checks pass.")
        else:
            st.info("An aggregate calculation is present, but this public-facing page withholds its value until the separate disclosure and publication gates pass.")
    section_header(
        "Phase 17 · verified insights",
        "Formal insight review pending" if phase17.get("status") != "verified" else "Verified insight",
        "Formal charts and interpretations require the separate aggregate validation and publication review.",
    )
    if phase17.get("status") != "verified":
        st.info("No formal publication insight is displayed yet. This does not prevent use of your authorized local analysis above.")
    else:
        eligible_insights = render_verified_result_filters([phase17], intended_use="public_display", key_prefix="fi")
        if not eligible_insights:
            st.info("No result matches the selected verified filters; no value is substituted for missing results.")
        for insight in eligible_insights or []:
            figure = build_indicator_summary_figure(insight, intended_use="public_display")
            if figure is None:
                st.info("The aggregate is not approved for this public visualization, so no chart is shown.")
                continue
            st.plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True})
            render_research_narrative(insight)
    filter_options = financial_inclusion_filter_options(definitions)
    filter_labels = [label for label, _ in filter_options]
    selected_filter_label = st.selectbox("Indicator definition · not a result filter", filter_labels, key="financial_inclusion_indicator")
    selected_filter_id = dict(filter_options)[selected_filter_label]
    visible_definitions = filter_indicator_definitions(definitions, selected_filter_id)
    if selected_filter_id in {None, "FI-ACCESS-001"}:
        review = metadata.catalogue.get("FI-ACCESS-001", {}).get("definition_review", {})
        review_fields = review.get("fields", []) if isinstance(review, dict) else []
        section_header(
            "FI-ACCESS-001 definition review",
            "Authorized local definition for dataset.dta",
            "The fields below document the measure used for the authorized local dataset.dta analysis; formal publication review remains separate.",
        )
        if review_fields:
            for item in review_fields:
                label = str(item.get("label") or item.get("field_id") or "Definition field")
                with st.expander(f"{label} · {_pretty_status(item.get('status'))}"):
                    st.markdown("**Definition value**")
                    st.write(item.get("value") or "Not established")
                    st.markdown("**Evidence needed / next action**")
                    st.write(item.get("next_action") or "Review the exact-release documentation.")
    section_header(
        "Indicator catalogue",
        "Financial-inclusion indicator definition" if selected_filter_id else "Financial-inclusion indicator definitions",
        "Definitions and readiness gates are shown separately from the authorized local aggregate result.",
    )
    for start in range(0, len(visible_definitions), 2):
        columns = st.columns(2, gap="large")
        for column, definition in zip(columns, visible_definitions[start : start + 2]):
            with column:
                indicator_card(
                    definition,
                    evaluate_catalogue_indicator(metadata, definition, dataset_id=active_dataset_id),
                    authorization_status=local_authorization.get("status") if local_analysis_active else None,
                )
    st.divider()
    section_header("Release gate", "What must be true before a value appears here")
    st.write(
        "For an official published result, the project still needs an authoritative codebook mapping, documented eligible population, dataset-specific weight decision where required, and separate publication review. Your local authorization is already recorded."
    )


def _render_supplied_local_material(project_root: Path) -> None:
    """Show aggregates calculated only from the user's supplied raw material."""

    section_header(
        "Supplied raw material",
        "Authorized dataset.dta view",
        "This section reads only the supplied local Stata dataset and matching questionnaire. It does not load another dataset, display respondent rows, or change the publication gate.",
    )
    result = load_supplied_financial_inclusion(str(project_root))
    if result.status != "exploratory" or not result.national:
        st.info("The supplied FinScope material is not available for local analysis: " + "; ".join(result.messages))
        return

    measures = result.measures or {}
    authorization = local_material_authorization(project_root)
    codebook = verified_codebook(project_root)
    inventory = supplied_material_inventory(project_root)
    st.caption(
        f"Project authorization: {_pretty_status(authorization.get('status'))} · "
        f"Codebook: {'verified against the supplied release file' if codebook.get('verified') else 'not yet generated'} · "
        f"Supplied material inventory: {inventory.get('file_count', 0)} files "
        f"({inventory.get('categories', {}).get('tabular', 0)} tabular, "
        f"{inventory.get('categories', {}).get('documentation', 0)} documentation, "
        f"{inventory.get('categories', {}).get('media', 0)} media)."
    )

    measure_cards = (
        ("any_account", "Any financial account", "Share of adults (16+) with an account in own name"),
        ("formal_account", "Formal account ownership", "Formal regulated providers, incl. mobile money; excl. informal groups"),
        ("mobile_money_account", "Mobile money account", "Account with a mobile money operator"),
        ("current_formal_use", "Currently uses a formal provider", "Current use of at least one formal provider"),
    )
    metrics = st.columns(4, gap="medium")
    with metrics[0]:
        metric_card("Respondents read", f"{result.rows:,}", "From the supplied dataset.dta")
    for column, (measure_id, title, subtitle) in zip(metrics[1:], measure_cards):
        share = (measures.get(measure_id) or {}).get("national", {}).get("share_percent")
        with column:
            metric_card(title, f"{share:.1f}%" if isinstance(share, (int, float)) else "Unavailable", subtitle)

    st.caption(
        f"Source: {result.source_path} · Definition reference: {result.questionnaire_path}. "
        "All shares are weighted by the release file's individual weight (pop_wt, 16+)."
    )
    st.caption(
        "Authorized local-source result · not an official or publication-approved estimate.")
    _render_official_cross_check(measures)
    st.caption(
        "Data-quality caveat: within this extract the QF access module disagrees with the mobile-money "
        "module — 35.5% weighted ever used a mobile money operator (qf1_05) versus 76.3% current or "
        "former users (f5) — so QF-battery mobile-money figures must be read alongside the F-module "
        "cross-check above, not in isolation."
    )
    _render_local_measure_charts(measures)


def _render_official_cross_check(measures: dict[str, dict[str, Any]]) -> None:
    """Render the documented cross-check between extract measures and the official report."""

    section_header(
        "Official report cross-check",
        "Extract measures vs published FinScope 2024 figures",
        "The official values are transcribed from the supplied FinScope 2024 report (sections 2.1 and the executive summary). They use the publisher's broader definitions; the comparison documents where the supplied extract agrees with, differs from, or cannot reproduce those definitions.",
    )

    def local_share(measure_id: str) -> str:
        share = (measures.get(measure_id) or {}).get("national", {}).get("share_percent")
        return f"{share:.1f}%" if isinstance(share, (int, float)) else "Unavailable"

    rows = (
        {
            "metric": "Financially included",
            "official": "96%",
            "official_definition": "Uses any formal or informal financial product (report §2.1, Figure 3)",
            "local_extract": local_share("any_provider_ever"),
            "local_measure": "Ever uses ≥1 of the 11 QF1 provider types",
            "reading": "Definition gap: QF1 battery excludes device-based and indirect use",
        },
        {
            "metric": "Formally served",
            "official": "92%",
            "official_definition": "Uses any formal regulated product (report §2.1, Figure 3)",
            "local_extract": local_share("current_formal_use"),
            "local_measure": "Currently uses ≥1 of the 6 QF4 formal providers",
            "reading": "Definition gap plus QF-module undercount below",
        },
        {
            "metric": "Registered mobile wallet (own name)",
            "official": "77%",
            "official_definition": "Registered mobile wallet in own name (executive summary)",
            "local_extract": local_share("mobile_money_registered_current"),
            "local_measure": "F5 code 6 · registered current mobile-money user",
            "reading": "F5 module agrees with the official report",
        },
        {
            "metric": "Own or have used mobile money",
            "official": "86%",
            "official_definition": "Owns or has used mobile money (executive summary)",
            "local_extract": local_share("mobile_money_ever_use"),
            "local_measure": "F5 codes 4·5·6 · current or former use",
            "reading": "F5 module agrees within ~10 points; QF1 battery does not",
        },
        {
            "metric": "Mobile money · QF1 battery",
            "official": "— ",
            "official_definition": "No direct official counterpart",
            "local_extract": local_share("mobile_money_ever"),
            "local_measure": "Ever used · qf1_05",
            "reading": "Extract inconsistency: 35.5% vs 76.3% in the F5 module",
        },
        {
            "metric": "Banked adults",
            "official": "22%",
            "official_definition": "Served by commercial banks, own-name accounts (report §2.1)",
            "local_extract": local_share("bank_ever"),
            "local_measure": "Ever uses a commercial bank · qf1_01",
            "reading": "Moderate gap: extract undercounts vs official",
        },
        {
            "metric": "Umurenge SACCO account",
            "official": "28%",
            "official_definition": "Own-name SACCO accounts (report, executive summary table)",
            "local_extract": local_share("umurenge_sacco_account"),
            "local_measure": "Own-name SACCO account · qf3_06",
            "reading": "Moderate gap: extract undercounts vs official",
        },
    )
    table = pd.DataFrame(rows)
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "metric": st.column_config.TextColumn("Metric", width="medium"),
            "official": st.column_config.TextColumn("Official", width="small"),
            "official_definition": st.column_config.TextColumn("Official definition", width="medium"),
            "local_extract": st.column_config.TextColumn("Local extract", width="small"),
            "local_measure": st.column_config.TextColumn("Local measure", width="medium"),
            "reading": st.column_config.TextColumn("Reading", width="medium"),
        },
    )
    st.caption(
        "Source of official values: data/mine/FinScope/2024/Finscope-Final-Report__10_07_2024-1.pdf "
        "(§2.1 financial inclusion levels and access strand; executive summary product table). "
        "Local values: weighted aggregates of data/mine/dataset.dta with the release weight (pop_wt). "
        "Rows listed as agreeing or moderately different still describe different constructs; "
        "they are cross-checks, not estimates of the official figures."
    )


def _render_local_measure_charts(measures: dict[str, dict[str, Any]]) -> None:
    """Render the verified measure battery as aggregate charts."""

    chart_measures = (
        ("any_account", "Any account", "#0e7490"),
        ("formal_account", "Formal account", "#155e75"),
        ("mobile_money_account", "Mobile money", "#0284c7"),
        ("umurenge_sacco_account", "Umurenge SACCO", "#0891b2"),
        ("commercial_bank_account", "Bank", "#06b6d4"),
        ("current_formal_use", "Current use", "#6366f1"),
    )

    national_figure = go.Figure(
        go.Bar(
            x=[share_label for _, share_label, _ in chart_measures],
            y=[
                (measures.get(mid) or {}).get("national", {}).get("share_percent")
                for mid, _, _ in chart_measures
            ],
            text=[
                f"{share:.1f}%"
                if isinstance((share := (measures.get(mid) or {}).get("national", {}).get("share_percent")), (int, float))
                else "Unavailable"
                for mid, _, _ in chart_measures
            ],
            textposition="auto",
            marker_color=[color for _, _, color in chart_measures],
            hovertemplate="%{x}<br>Weighted share: %{y:.1f}%<extra></extra>",
        )
    )
    national_figure.update_layout(
        title="Key measures · national (weighted, adults 16+)",
        yaxis_title="Weighted share (% of adults 16+)",
        yaxis=dict(range=[0, 100]),
        margin=dict(l=20, r=20, t=50, b=20),
        height=380,
    )
    st.plotly_chart(national_figure, width="stretch", config={"displayModeBar": False, "responsive": True})

    dimension_panels = (
        ("a1", "By province · any account vs formal account", ("any_account", "formal_account")),
        ("a6", "Urban vs rural", ("any_account", "formal_account")),
        ("b2", "Male vs female", ("any_account", "formal_account")),
    )
    for dimension, title, (primary_id, secondary_id) in dimension_panels:
        primary = measures.get(primary_id) or {}
        secondary = measures.get(secondary_id) or {}
        primary_rows = list((primary.get("groups") or {}).get(dimension, ()))
        secondary_rows = list((secondary.get("groups") or {}).get(dimension, ()))
        if not primary_rows:
            continue
        groups = [str(row.get("group")) for row in primary_rows]
        figure = go.Figure()
        for id_, color in ((primary_id, "#0e7490"), (secondary_id, "#f59e0b")):
            rows = primary_rows if id_ == primary_id else secondary_rows
            figure.add_trace(
                go.Bar(
                    name=(measures.get(id_) or {}).get("label") or id_,
                    x=groups,
                    y=[row.get("share_percent") for row in rows],
                    text=[
                        f"{row.get('share_percent'):.1f}%"
                        if isinstance(row.get("share_percent"), (int, float))
                        else "Unavailable"
                        for row in rows
                    ],
                    textposition="auto",
                    marker_color=color,
                    hovertemplate="%{x}<br>Weighted share: %{y:.1f}%<extra></extra>",
                )
            )
        figure.update_layout(
            title=title,
            barmode="group",
            yaxis_title="Weighted share (% of adults 16+)",
            xaxis_title=None,
            yaxis=dict(range=[0, 100]),
            margin=dict(l=20, r=20, t=50, b=20),
            height=380,
            legend=dict(orientation="h", y=-0.15),
        )
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True})
    st.caption(
        "All values are weighted aggregates of the supplied release file; respondent rows are never "
        "loaded into the application or displayed. Definitions cite the exact QF variables and are "
        "documented in data/metadata/finscope_codebook.json with the file checksum."
    )


def render_poverty_insights(project_root: Path) -> None:
    metadata = _metadata(project_root)
    page_header(
        "Analytical area",
        "Poverty insights",
        "A future space for approved poverty measures, presented with their official definitions, source methodology, and uncertainty.",
    )
    definition = metadata.catalogue.get("POVERTY-001")
    if metadata.catalogue_error or not definition:
        st.warning("The poverty indicator definition is unavailable; no estimate can be shown.")
        return
    label, class_name = status_label(definition.get("status"))
    readiness = evaluate_catalogue_indicator(metadata, definition, dataset_id=_selected_dataset_id())
    st.markdown(f"<span class='status-pill {class_name}'>{label}</span>", unsafe_allow_html=True)
    st.caption(
        "Analysis readiness: "
        + ("eligible" if readiness.analysis_eligible else "blocked pending evidence")
        + " · Publication: "
        + ("eligible" if readiness.publication_eligible else "not eligible")
    )
    st.write("")
    empty_state(
        "Poverty measure awaiting evidence",
        "No poverty threshold, poverty status, trend, ranking, or district estimate is calculated in this phase. The project needs an approved definition, verified source variables, authorization, and survey-design documentation first.",
    )
    st.divider()
    section_header("Readiness checklist", "The evidence required for a defensible poverty view")
    checklist = st.columns(3, gap="medium")
    with checklist[0]:
        render_workflow_step("01", "Definition", "Record the official measure, population, unit, and valid interpretation.")
    with checklist[1]:
        render_workflow_step("02", "Source mapping", "Verify the codebook, variables, exclusions, weights, and source authorization.")
    with checklist[2]:
        render_workflow_step("03", "Uncertainty", "Document the sampling design and variance method before reporting precision.")
    with st.expander("Catalogue review blockers"):
        st.write(list(dict.fromkeys([*(definition.get("review_blockers") or []), *readiness.messages])))


def _coordinate_rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        return [ring for ring in coordinates if isinstance(ring, list)]
    if geometry_type == "MultiPolygon":
        return [ring for polygon in coordinates for ring in polygon if isinstance(ring, list)]
    return []


def _boundary_figure(document: dict[str, Any]) -> go.Figure:
    """Draw boundary lines only; no analytical fill or fabricated values."""

    traces = []
    for feature in document.get("features", []):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        label = str(properties.get("shapeName", "Administrative boundary"))
        longitudes: list[float | None] = []
        latitudes: list[float | None] = []
        for ring in _coordinate_rings(geometry):
            for coordinate in ring:
                if isinstance(coordinate, list) and len(coordinate) >= 2:
                    longitudes.append(float(coordinate[0]))
                    latitudes.append(float(coordinate[1]))
            longitudes.append(None)
            latitudes.append(None)
        if longitudes:
            traces.append(
                go.Scattergeo(
                    lon=longitudes,
                    lat=latitudes,
                    mode="lines",
                    line={"color": "#1ca6b7", "width": 1.15},
                    text=[label] * len(longitudes),
                    hovertemplate="%{text}<extra>Boundary reference</extra>",
                    showlegend=False,
                )
            )
    figure = go.Figure(traces)
    figure.update_layout(
        height=620,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        geo={
            "showland": True,
            "landcolor": "#f1f5f8",
            "showocean": True,
            "oceancolor": "#ffffff",
            "showlakes": True,
            "lakecolor": "#ffffff",
            "showframe": False,
            "fitbounds": "locations",
            "projection_type": "mercator",
        },
    )
    return figure


def render_geographic_analysis(project_root: Path) -> None:
    page_header(
        "Analytical area",
        "Geographic analysis",
        "A boundary reference for future approved comparisons. Geography is shown without coloring or ranking districts by unsupported estimates.",
    )
    boundary_options = available_boundary_options(project_root)
    if boundary_options:
        st.warning("Boundary presence does not establish licensing, compatible survey geography, or support for district-level estimates.")
    page_metadata = _metadata(project_root)
    research_report = page_metadata.research_readiness
    resource_records = list(page_metadata.geographic_resources)
    resource_summary = summarize_geographic_resources(resource_records, project_root=project_root)
    section_header(
        "Geographic resource readiness",
        "No verified resource registered" if not resource_records else "Registered resources",
        "Registration, local presence, provenance, licensing, analytical authorization, and public visualization approval are separate states.",
    )
    if page_metadata.geographic_resources_error:
        st.error(page_metadata.geographic_resources_error)
    elif not resource_records:
        empty_state(
            "No geographic boundary resource is registered",
            "No official administrative-boundary resource is currently present in the geographic resource registry. No map or area estimate is available.",
            tone="blocked",
        )
    else:
        resource_rows = []
        resource_summary_by_id = {
            row.get("resource_id"): row
            for row in resource_summary.get("resources", [])
            if isinstance(row, dict)
        }
        for resource in resource_records:
            validation = validate_geographic_resource(resource, project_root=project_root)
            summary_row = resource_summary_by_id.get(resource.get("resource_id"), {})
            resource_rows.append(
                {
                    "Resource": resource.get("display_name"),
                    "Level": resource.get("administrative_level") or "Unavailable",
                    "Release": resource.get("boundary_release") or "Unavailable",
                    "Local presence": summary_row.get("local_presence", "missing").title(),
                    "Verification": validation.status,
                    "License": resource.get("license_status", "unverified"),
                    "Publication": resource.get("publication_status", "not_approved"),
                }
            )
        st.dataframe(resource_rows, hide_index=True, width="stretch")
        st.caption(f"Registered: {resource_summary['resource_count']} · verified: {resource_summary['verified_resource_count']} · locally present: {resource_summary['locally_present_count']}")
    boundary_requirement = next(
        (
            requirement
            for requirement in (research_report or {}).get("requirements", [])
            if isinstance(requirement, dict) and requirement.get("requirement") == "geographic_assets"
        ),
        None,
    )
    if boundary_requirement:
        status = str(boundary_requirement.get("status", "unavailable")).replace("_", " ").title()
        st.caption(f"Boundary asset readiness: {status}. {boundary_requirement.get('next_action', '')}")
    geographic_definition = page_metadata.catalogue.get("GEO-COMP-001")
    if geographic_definition:
        geographic_readiness = evaluate_catalogue_indicator(
            page_metadata,
            geographic_definition,
            dataset_id=_selected_dataset_id(),
            requested_geography=True,
        )
        st.caption(
            "Geographic comparison readiness: "
            + ("eligible for analysis" if geographic_readiness.analysis_eligible else "blocked pending validated geography and survey evidence")
        )
    section_header(
        "Boundary reference",
        "Geographic context without unsupported estimates",
        "Choose a neutral administrative boundary. No indicator values are attached to the map.",
    )
    verified_paths = {
        str(resource.get("source_path"))
        for resource in resource_records
        if isinstance(resource, dict)
        and validate_geographic_resource(resource, project_root=project_root).status == "verified"
    }
    boundary_options = {
        label: path
        for label, path in boundary_options.items()
        if path.as_posix() in verified_paths or str(path).replace("\\", "/") in verified_paths
    }
    if not boundary_options:
        empty_state(
            "Boundary reference unavailable · verified visualization unavailable",
            "No boundary file is both locally present and verified in the geographic resource registry. Add a reviewed official boundary resource before display; no map or geographic values are shown.",
        )
        return
    selected_label = st.selectbox("Boundary reference", list(boundary_options))
    selected_path = boundary_options[selected_label]
    try:
        document = load_geojson(selected_path, project_root=project_root)
        profile = profile_geojson(document)
    except Exception:
        st.error("The selected boundary file could not be validated. No map was rendered.")
        return
    left, right = st.columns([2.4, 1], gap="large")
    with left:
        st.plotly_chart(_boundary_figure(document), width="stretch", config={"displayModeBar": False})
        st.caption("Neutral boundary reference only. Hover a boundary for its source label; no indicator values are attached.")
    with right:
        metric_card("Features", str(profile["feature_count"]), "Structural count from the selected boundary file")
        st.write("")
        metric_card("Analytical join", "Not ready", "Geographic keys and survey design require verification")
        st.write("")
        metric_card("Publication", "Review needed", "Local boundary provenance and licensing are unverified")
    st.divider()
    empty_state(
        "No district or province estimates",
        "The map intentionally contains boundaries only. Financial-inclusion or poverty values will not be joined to geography until compatible identifiers, survey design, authorization, and publication review are documented.",
    )


def render_data_quality(project_root: Path) -> None:
    metadata = _metadata(project_root)
    page_header(
        "Operational readiness",
        "Data quality",
        "Aggregate metadata for source readiness and indicator review — without loading source datasets or exposing records.",
    )
    if metadata.inventory_error:
        st.warning(metadata.inventory_error)
        inventory = None
    else:
        inventory = inventory_summary(metadata.inventory)
    summary = catalogue_summary(metadata.catalogue)
    registry = registry_summary(metadata.registry)
    readiness_report = metadata.research_readiness
    intake_status = build_phase12_status(metadata.registry, metadata.catalogue, project_root=project_root, dataset_id=_selected_dataset_id())
    phase14_status = _phase14(metadata, project_root)
    inventory_state = (readiness_report or {}).get("inventory", {})
    inventory_is_current = inventory_state.get("status") == "current"
    if metadata.research_readiness_error:
        st.warning(metadata.research_readiness_error)
    elif readiness_report and not inventory_is_current:
        st.warning(
            "The source inventory is not current relative to the approved data directory. "
            "Its counts are not treated as current; review the approved scope and run "
            "scripts/inventory_sources.py before relying on inventory details."
        )
    st.info("Phase 12 intake is metadata-only while authorization is unverified. No dataset records were read; source file presence and outstanding review gates are shown in Research Readiness.")
    if readiness_report:
        source_quality_rows = []
        for dataset in readiness_report.get("datasets", []):
            if not isinstance(dataset, dict):
                continue
            present = dataset.get("source_presence") == "discovered"
            source_quality_rows.append(
                {
                    "Dataset": dataset.get("display_name", "Unavailable"),
                    "Source availability": "Present" if present else "Missing",
                    "Quality assessment": dataset.get("data_quality_status", "unverified") if present else "Not assessed — source missing",
                }
            )
        section_header("Source availability vs quality", "No quality result without an available source", "Missing files are distinguished from validation failures; no source rows or fabricated quality statistics are shown.")
        if source_quality_rows:
            st.dataframe(source_quality_rows, hide_index=True, width="stretch")
    if readiness_report:
        columns = st.columns(4, gap="medium")
        with columns[0]:
            metric_card("Current data files", str(inventory_state.get("current_file_count", 0)), "Regular files currently below the approved data root")
        with columns[1]:
            metric_card("Inventory snapshot", str(inventory_state.get("status", "unavailable")).replace("_", " ").title(), "Currentness is checked before counts are relied upon")
        with columns[2]:
            metric_card("Documentation files", str(readiness_report.get("documentation", {}).get("documentation_file_count", 0)), "Presence only; review and authorization remain separate")
        with columns[3]:
            metric_card("Authorization", str(registry["authorization_counts"].get("unverified", 0)), "Registered datasets still unverified")
        if inventory_is_current and inventory:
            st.caption(
                f"Duplicate checksum groups requiring review: {inventory['duplicate_checksum_group_count']}. "
                "The inventory records metadata only and does not expose source contents."
            )
            format_figure = build_metadata_count_figure(
                inventory.get("formats"),
                title="Current inventory by recorded file format",
                category_axis="Recorded format",
                count_axis="Files in current inventory",
            )
            if format_figure is not None:
                st.plotly_chart(format_figure, width="stretch", config={"displayModeBar": False, "responsive": True})
                st.caption("This describes inventory structure only. It is not a data-quality score and does not establish authorization.")
    elif inventory:
        columns = st.columns(2, gap="medium")
        with columns[0]:
            metric_card("Inventory files", str(inventory["file_count"]), "Files represented in the available snapshot")
        with columns[1]:
            metric_card("Authorization", str(registry["authorization_counts"].get("unverified", 0)), "Registered datasets still unverified")
    validation_status = str((phase14_status.get("quality_validation") or {}).get("status", "not_run"))
    section_header(
        "Calculation validation",
        validation_status.replace("_", " ").title(),
        "Quality checks are distinct from source availability and central analytical eligibility.",
    )
    st.caption(
        "Checks cannot run against the live FinScope candidate until central analytical eligibility is true; no real-data quality metrics are reported."
        if validation_status == "not_run"
        else "Validation outcomes are aggregate metadata only."
    )
    readiness_by_id = {
        definition.get("indicator_id"): evaluate_catalogue_indicator(metadata, definition, dataset_id=_selected_dataset_id())
        for definition in metadata.catalogue.values()
        if definition.get("indicator_id")
    }
    section_header("Indicator readiness", "Catalogue status", "These counts are read from the machine-readable catalogue and do not represent analytical results.")
    if metadata.catalogue_error:
        st.error(metadata.catalogue_error)
    else:
        columns = st.columns(3, gap="medium")
        with columns[0]:
            metric_card("Verified mappings", str(summary["verified_mapping_count"]), "Currently available in the catalogue")
        with columns[1]:
            metric_card("Review blockers", str(summary["indicators_with_review_blockers"]), "Definitions still requiring evidence")
        with columns[2]:
            metric_card("Candidate concepts", _catalogue_count_label(metadata, summary["indicator_count"]), "Not approved for publication")
        render_catalogue_table(metadata.catalogue.values(), readiness_by_id)
    st.divider()
    section_header(
        "Research readiness",
        "Evidence and verification gates",
        "A discovered file, an available document, and a successful parser check do not by themselves grant analytical or publication eligibility.",
    )
    if readiness_report:
        readiness_status = str(readiness_report.get("overall_status", "blocked")).replace("_", " ").title()
        st.info(
            f"Overall status: {readiness_status}. "
            f"Analytical eligibility: {bool(readiness_report.get('analytical_eligibility'))}. "
            f"Publication eligibility: {bool(readiness_report.get('publication_eligibility'))}."
        )
        rows = _research_readiness_rows(readiness_report)
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.warning("Research-readiness metadata is unavailable; no readiness conclusion is shown.")
    st.divider()
    empty_state(
        "Safe operating boundary",
        "The dashboard does not enumerate, load, cache, or profile source datasets during startup or selection. Quality reports, registry records, and source inventories remain metadata; authorization and publication decisions must be made outside the UI.",
    )


def _readiness_evidence_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = report.get("evidence") or {}
    rows = []
    for item in evidence.get("blockers", []):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Category": str(item.get("category", "Unavailable")).replace("_", " ").title(),
                "Evidence ID": str(item.get("evidence_id", "Unavailable")),
                "Status": str(item.get("status", "Unavailable")).replace("_", " ").title(),
                "Affects": ", ".join(str(scope) for scope in item.get("blocks", [])),
                "Why blocked": str(item.get("reason_for_blocking", "Review required.")),
                "Next action": str(item.get("next_action", "Review the evidence register.")),
            }
        )
    return rows


def render_research_readiness(project_root: Path) -> None:
    """Render the metadata-only Phase 10 Evidence Center."""

    metadata = _metadata(project_root)
    page_header(
        "Evidence center",
        "Research readiness",
        "A reviewable record of what is known, what is missing, and what must be verified before analysis, geographic comparison, or publication.",
    )
    report = metadata.research_readiness
    if metadata.evidence_error:
        st.error(metadata.evidence_error)
    if report is None:
        empty_state(
            "Readiness report unavailable",
            "The application could not validate the current metadata. No readiness conclusion or analytical result is shown.",
            tone="blocked",
        )
        return

    evidence = report.get("evidence") or {}
    summary = evidence.get("summary") or {}
    overall_status = str(report.get("overall_status", "blocked")).replace("_", " ").title()
    st.markdown(
        f"<span class='status-pill blocked'>{overall_status} · evidence review required</span>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Analytical eligibility: "
        + ("eligible" if report.get("analytical_eligibility") else "blocked")
        + " · Publication eligibility: "
        + ("eligible" if report.get("publication_eligibility") else "not eligible")
    )
    st.info(
        "Readiness is evidence-based. A discovered file, a successful parser check, or a provided document does not independently verify ownership, permission, variable meaning, or publication safety."
    )
    st.caption(
        "Software validation is established by the repository test suite, not inferred from research readiness; "
        "tests are not executed by this dashboard. Run `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests` "
        "to validate software. Passing tests do not authorize research or publication."
    )
    phase13 = _phase13(metadata, project_root)
    phase14 = _phase14(metadata, project_root)
    phase17 = _phase17(metadata, project_root, phase14)
    phase18 = _phase18(metadata, project_root)
    phase20 = phase18.get("reproducibility") if isinstance(phase18.get("reproducibility"), dict) else {
        "status": "not_configured",
        "manifest_status": "invalid_or_missing",
        "integrity_status": "not_run",
        "lineage_status": "incomplete",
        "reproduction_status": "not_run",
        "blocker_ids": ["reproducibility_manifest_missing"],
    }
    st.caption(
        "Source-access readiness: "
        + ("eligible" if phase13.get("analysis_eligible") else "blocked")
        + " · Indicator-definition readiness: "
        + ("eligible" if (phase13.get("readiness") or {}).get("definition_review") else "blocked")
        + " · Calculation validation: "
        + str((phase14.get("quality_validation") or {}).get("status", "not_run")).replace("_", " ")
        + " · Publication: "
        + ("eligible" if phase13.get("publication_eligible") else "not eligible")
        + " · Verified insight: "
        + ("available" if phase17.get("status") == "verified" else "blocked or unavailable")
        + " · End-to-end release readiness: "
        + str(phase18.get("status", "blocked"))
        + " · Reproducibility: "
        + str(phase20.get("status", "not_configured"))
    )
    st.divider()
    section_header(
        "Phase 18 · end-to-end release readiness",
        "Release blocked" if phase18.get("status") != "ready" else "Release-ready workflow",
        "This audit composes the existing gates; it does not authorize analysis or publication.",
    )
    workflow_rows = [
        {
            "Transition": stage.get("label"),
            "Status": str(stage.get("status", "blocked")).replace("_", " ").title(),
            "Blocker IDs": ", ".join(stage.get("blocker_ids", [])) or "None",
            "Authority": stage.get("authority"),
        }
        for stage in phase18.get("stages", [])
        if isinstance(stage, dict)
    ]
    if workflow_rows:
        st.dataframe(workflow_rows, hide_index=True, width="stretch")
    st.info("No release artifact or public research output is approved while any applicable transition remains blocked. Software tests do not authorize research or publication.")
    section_header(
        "Phase 20 · reproducibility and audit trail",
        str(phase20.get("status", "not_configured")).replace("_", " ").title(),
        "A manifest records traceability; it does not grant authorization, analytical eligibility, or publication approval.",
    )
    st.caption(
        "Manifest: " + str(phase20.get("manifest_status", "invalid_or_missing"))
        + " · Integrity: " + str(phase20.get("integrity_status", "not_run"))
        + " · Lineage: " + str(phase20.get("lineage_status", "incomplete"))
        + " · Reproduction: " + str(phase20.get("reproduction_status", "not_run"))
    )
    if phase20.get("blocker_ids"):
        st.warning("Reproducibility is unavailable or blocked: " + ", ".join(str(item) for item in phase20.get("blocker_ids", [])))
    st.divider()
    section_header("Phase 13 · source access and documentation", "Access checklist", "Statuses are resolved from the official source record and evidence register; creating a checklist item does not verify it.")
    access = phase13.get("access_checklist", {})
    access_rows = [
        {
            "Requirement": row.get("label"),
            "Status": _pretty_status(row.get("status")),
            "Evidence needed": row.get("evidence_needed"),
            "Responsible action": row.get("responsible_action"),
            "Next step": row.get("next_action"),
        }
        for row in access.get("rows", []) if isinstance(row, dict)
    ]
    st.caption(f"FinScope access checklist: {access.get('verified', 0)} verified of {access.get('total', 0)} · analytical eligibility: {'yes' if phase13.get('analysis_eligible') else 'no'} · publication eligibility: {'yes' if phase13.get('publication_eligible') else 'no'}")
    if access_rows:
        st.dataframe(access_rows, hide_index=True, width="stretch")
    definition_review = phase13.get("definition_review", {})
    st.caption(f"FI-ACCESS-001 definition review: {definition_review.get('verified_field_count', 0)} verified of {definition_review.get('field_count', 0)} fields for release {definition_review.get('target_release_identifier') or 'not established'}.")
    review_rows = [
        {"Field": row.get("label"), "Status": _pretty_status(row.get("status")), "Next action": row.get("next_action")}
        for row in definition_review.get("fields", []) if isinstance(row, dict)
    ]
    if review_rows:
        st.dataframe(review_rows, hide_index=True, width="stretch")
    readiness_state = phase13.get("readiness") or {}
    st.info(
        "Analysis remains blocked while the central readiness decision has unresolved requirements. "
        f"{len(readiness_state.get('blocked_checks', []))} analytical blocker(s) and "
        f"{len(readiness_state.get('publication_blocked_checks', []))} publication blocker(s) are recorded below."
    )
    st.info("Publication is an additional gate: it requires separate permission, licensing, disclosure-risk, attribution, and output-level review even if analysis is later approved.")

    st.divider()
    section_header(
        "Phase 14 · first verified indicator",
        "Calculation blocked" if phase14.get("calculation_status") != "calculated" else "Aggregate calculated",
        "No numeric estimate is shown unless the central analytical eligibility decision is true and an aggregate-only result artifact is valid.",
    )
    if phase14.get("calculation_status") != "calculated":
        st.info(
            "FI-ACCESS-001: no estimate was calculated. The calculation workflow stopped before "
            "observation processing. This is the expected state while the recorded prerequisites "
            "remain unresolved."
        )
        phase14_rows = [
            {
                "Blocker ID": item.get("identifier"),
                "Missing prerequisite": item.get("message"),
                "Human action": item.get("next_action"),
            }
            for item in phase14.get("blockers", [])
            if isinstance(item, dict)
        ]
        if phase14_rows:
            render_blocker_cards([
                {"identifier": row["Blocker ID"], "message": row["Missing prerequisite"], "next_action": row["Human action"]}
                for row in phase14_rows
            ])
    else:
        st.info("An aggregate calculation may exist, but its numeric value is withheld here unless analytical, disclosure, and publication eligibility all pass.")

    section_header(
        "Evidence summary",
        "Current verification state",
        "Counts below are calculated from the validated evidence register and existing readiness report.",
    )
    metrics = st.columns(4, gap="medium")
    with metrics[0]:
        metric_card("Evidence requirements", str(summary.get("total", 0)), "Register items in scope")
    with metrics[1]:
        metric_card("Verified", str(summary.get("verified", 0)), "Explicitly reviewed evidence only")
    with metrics[2]:
        metric_card("Missing", str(summary.get("missing", 0)), "No supporting evidence recorded")
    with metrics[3]:
        metric_card("Provided · unverified", str(summary.get("provided_unverified", 0)), "Present but not independently verified")
    metrics = st.columns(3, gap="medium")
    with metrics[0]:
        metric_card("Rejected", str(summary.get("rejected", 0)), "Evidence requiring replacement or review")
    with metrics[1]:
        metric_card("Analysis blockers", str(summary.get("analysis_blocking", 0)), "Mandatory evidence blocking analysis")
    with metrics[2]:
        metric_card("Publication blockers", str(summary.get("publication_blocking", 0)), "Permission, disclosure, or licensing gates")
    evidence_figure = build_evidence_status_figure(report)
    if evidence_figure is not None:
        st.plotly_chart(evidence_figure, width="stretch", config={"displayModeBar": False, "responsive": True})
        st.caption("This chart summarizes evidence records only. It is not a measure of sample size, indicator values, or statistical quality.")
    else:
        empty_state("Evidence visualization unavailable", "The validated readiness report contains no evidence-status records to chart.", tone="blocked")

    st.divider()
    section_header("Dataset readiness", "Registered sources", "Registration identifies a source for review; it does not authorize loading or analysis.")
    dataset_rows = []
    for dataset in report.get("datasets", []):
        if not isinstance(dataset, dict):
            continue
        dataset_rows.append(
            {
                "Dataset": dataset.get("display_name", "Unavailable"),
                "Local presence": str(dataset.get("source_presence", "Unavailable")).replace("_", " ").title(),
                "Provenance": str(dataset.get("provenance_status", "Unavailable")).replace("_", " ").title(),
                "Authorization": str(dataset.get("authorization_status", "Unavailable")).replace("_", " ").title(),
                "Documentation": str(dataset.get("documentation_status", "Unavailable")).replace("_", " ").title(),
                "Analysis": "Eligible" if dataset.get("analytical_eligibility") else "Blocked",
                "Publication": "Eligible" if dataset.get("publication_eligibility") else "Not eligible",
            }
        )
    if dataset_rows:
        st.dataframe(dataset_rows, hide_index=True, width="stretch")
    else:
        empty_state("No registered datasets", "No dataset metadata is available to review.", tone="blocked")

    st.divider()
    section_header("Indicator readiness", "Proposed concepts remain separate from approved results", "A proposed catalogue entry is not a verified mapping, an approved specification, or a calculated statistic.")
    indicator_rows = []
    for indicator in report.get("indicators", []):
        if not isinstance(indicator, dict):
            continue
        indicator_rows.append(
            {
                "Indicator": indicator.get("display_name", "Unavailable"),
                "Catalogue status": str(indicator.get("catalogue_status", "Unavailable")).replace("_", " ").title(),
                "Variable mapping": str(indicator.get("mapping_status", "Unavailable")).replace("_", " ").title(),
                "Methodology": str(indicator.get("methodology_status", "Unavailable")).replace("_", " ").title(),
                "Analysis": "Eligible" if indicator.get("analytical_eligibility") else "Blocked",
                "Blockers": "; ".join(str(item) for item in indicator.get("blockers", [])),
            }
        )
    if indicator_rows:
        st.dataframe(indicator_rows, hide_index=True, width="stretch")
    else:
        empty_state("Indicator catalogue unavailable", "No indicator readiness state is shown because the catalogue could not be validated.", tone="blocked")

    st.divider()
    section_header("Source verification", "Official references and unresolved source questions", "A public source page supports discovery and citation; it does not prove that a local file is the same release or that microdata may be analyzed or redistributed.")
    if metadata.source_verification_error:
        st.warning(metadata.source_verification_error)
    source_rows = []
    for source in (report.get("source_verification") or {}).get("sources", []):
        if not isinstance(source, dict):
            continue
        identity = source.get("dataset_id") or source.get("candidate_dataset_name") or "Unavailable"
        source_rows.append(
            {
                "Source": source.get("source_title") or "Unidentified source",
                "Dataset or candidate": identity,
                "Organization": source.get("source_organization") or "Unknown",
                "References": len(source.get("source_references", [])),
                "Reference status": str(source.get("source_reference_status", "missing")).replace("_", " ").title(),
                "Documentation": str(source.get("documentation_status", "missing")).replace("_", " ").title(),
                "Documentation review": str(source.get("documentation_review_status", "missing")).replace("_", " ").title(),
                "Source information": str(source.get("source_information_status", "missing")).replace("_", " ").title(),
                "Access authorization": str(source.get("access_authorization_status", "missing")).replace("_", " ").title(),
                "Analysis approval": str(source.get("analysis_approval_status", "missing")).replace("_", " ").title(),
                "Publication approval": str(source.get("publication_approval_status", "missing")).replace("_", " ").title(),
                "Permission": str(source.get("permission_status", "unverified")).replace("_", " ").title(),
                "License": str(source.get("license_status", "unverified")).replace("_", " ").title(),
                "Verification": str(source.get("verification_status", "unavailable")).replace("_", " ").title(),
                "Manual review": "Required" if source.get("manual_verification_required") else "Not recorded",
            }
        )
    if source_rows:
        st.dataframe(source_rows, hide_index=True, width="stretch")
        for source in (report.get("source_verification") or {}).get("sources", []):
            if not isinstance(source, dict) or not source.get("source_references"):
                continue
            label = source.get("source_title") or source.get("candidate_dataset_name") or "Source references"
            with st.expander(f"References · {label}"):
                for reference in source.get("source_references", []):
                    if isinstance(reference, dict):
                        st.markdown(
                            f"- [{reference.get('label', 'Source reference')}]({reference.get('url', '')}) — {reference.get('supports', 'Reference scope unavailable')} · status: `{reference.get('status', 'unavailable')}`"
                        )
                if source.get("unresolved_questions"):
                    st.caption("Unresolved questions")
                    st.write(source["unresolved_questions"])
    else:
        empty_state("Source-verification matrix unavailable", "No source reference or verification conclusion is shown.", tone="blocked")

    st.divider()
    section_header("Codebook coverage", "Mapping evidence traceability", "A source variable is not approved merely because it appears in a schema. Verified mappings require documented meaning, coding, universe, denominator, missing-value rules, and codebook evidence.")
    mapping_summary = report.get("mapping_summary") or {}
    mapping_columns = st.columns(3, gap="medium")
    with mapping_columns[0]:
        metric_card("Candidate indicators", str(mapping_summary.get("indicator_count", 0)), "Catalogue definitions")
    with mapping_columns[1]:
        metric_card("Documented mappings", str(mapping_summary.get("indicators_with_documented_mappings", 0)), "Mapping records in catalogue metadata")
    with mapping_columns[2]:
        metric_card("Verified mappings", str(mapping_summary.get("indicators_with_verified_mappings", 0)), "Codebook-backed and independently reviewed")
    mapping_rows = []
    for row in mapping_summary.get("rows", []):
        if isinstance(row, dict):
            evidence_blockers = [item for item in row.get("evidence_blockers", []) if isinstance(item, dict)]
            mapping_rows.append(
                {
                    "Indicator": row.get("display_name", "Unavailable"),
                    "Mapping status": str(row.get("mapping_status", "unavailable")).replace("_", " ").title(),
                    "Mapping records": row.get("mapping_count", 0),
                    "Evidence references": "; ".join(str(item) for item in row.get("evidence_references", []) if item),
                    "Why blocked": "; ".join(str(item.get("why_it_matters", "Review required.")) for item in evidence_blockers) or "; ".join(str(item) for item in row.get("blockers", [])),
                    "Next action": "; ".join(str(item.get("next_action", "Review the mapping.")) for item in evidence_blockers) or "Review the authoritative codebook and mapping record.",
                }
            )
    if mapping_rows:
        st.dataframe(mapping_rows, hide_index=True, width="stretch")
    else:
        empty_state("No mapping records", "The catalogue has no codebook-backed variable mappings. Candidate concepts remain blocked.", tone="blocked")

    st.divider()
    section_header("Geographic readiness", "Boundaries and joins", "Boundary presence is not evidence of a valid survey join or permission to publish a geographic output.")
    geographic_assets = report.get("geographic_assets") or {}
    geo_columns = st.columns(4, gap="medium")
    with geo_columns[0]:
        metric_card("Boundary assets", str(geographic_assets.get("asset_count", 0)), "Structural presence only")
    with geo_columns[1]:
        metric_card("Structurally valid", str(geographic_assets.get("valid_asset_count", 0)), "Parser validation, not authorization")
    with geo_columns[2]:
        metric_card("Registered resources", str((report.get("geographic_resources") or {}).get("resource_count", 0)), "Metadata records, not verification")
    with geo_columns[3]:
        metric_card("Valid joins", "0", "No verified aggregate join is recorded")
    st.caption("Geographic visualization remains unavailable until identifiers, crosswalks, coverage, provenance, and publication permission are verified.")

    st.divider()
    section_header("Actionable blockers", "What to resolve next", "Blockers are grouped from the same evidence register used by the readiness report.")
    render_readiness_blocker_groups(build_evidence_blocker_records(report))

    st.divider()
    section_header("Researcher action plan", "Manual work required to progress", "Completion means that a responsible reviewer records acceptable evidence, reference, date, and status; creating this checklist does not complete any task.")
    action_plan = report.get("researcher_action_plan") or {}
    render_researcher_action_plan(prepare_researcher_action_plan(action_plan, include_geography=True))

    st.divider()
    section_header("Provenance and audit", "How this view was built", "The report uses metadata and safe path checks only; it does not inspect or display source records.")
    report_metadata = report.get("report_metadata") or {}
    source_timestamp = report_metadata.get("source_inventory_generated_at_utc")
    st.caption(
        "Source inventory timestamp: "
        + (str(source_timestamp) if source_timestamp else "not recorded")
        + " · Runtime report: computed from current metadata and approved data-path snapshot."
    )
    st.caption("Report sources: " + ", ".join(str(item) for item in report_metadata.get("source_references", [])))
    st.info(
        "Verification is intentionally manual. A reviewer must record documentary evidence and its status in the metadata register; this page has no action that approves a dataset, indicator, or publication output."
    )


def render_dataset_registry(project_root: Path) -> None:
    """Render the validated dataset registry without loading registered sources."""

    metadata = _metadata(project_root)
    page_header(
        "Data management",
        "Dataset registry",
        "Review the datasets known to the project and their governance state. Selecting a record never loads, previews, or authorizes its source.",
    )
    if metadata.registry_error:
        st.error(metadata.registry_error)
        return
    records = list(metadata.registry.values())
    if not records:
        empty_state("Dataset registry is empty", "No dataset records are available for review.", tone="blocked")
        return
    summary = registry_summary(metadata.registry)
    metrics = st.columns(4, gap="medium")
    with metrics[0]:
        metric_card("Registered datasets", str(summary["dataset_count"]), "Metadata records only")
    with metrics[1]:
        metric_card("Authorization", str(summary["authorization_counts"].get("unverified", 0)), "Still requiring review")
    with metrics[2]:
        metric_card("Codebooks", str(summary["codebook_counts"].get("verified", 0)), "Verified registry state")
    with metrics[3]:
        metric_card("Publication eligible", str(summary["publication_eligibility_counts"].get("True", 0)), "Explicit status only")

    st.divider()
    section_header("Registered sources", "Governance status at a glance", "Paths and source contents remain outside this page; the fields below come from the validated registry.")
    _metadata_status_table(
        records,
        [
            ("Dataset", "display_name"),
            ("Format", "file_format"),
            ("Provenance", "provenance_status"),
            ("Authorization", "authorization_status"),
            ("Codebook", "codebook_status"),
            ("Analysis", "analytical_eligibility"),
            ("Publication", "eligible_for_publication"),
        ],
    )
    st.divider()
    section_header("Inspect one record", "Explicit session-level selection", "The selection is shared with analytical-area pages, but it does not grant permission or initiate data loading.")
    labels = [f"{record.get('display_name', 'Unnamed dataset')} · {record.get('dataset_id', 'unknown')}" for record in records]
    current_id = _selected_dataset_id()
    current_index = next(
        (index for index, record in enumerate(records) if record.get("dataset_id") == current_id),
        0,
    )
    selected_label = st.selectbox("Registered dataset", labels, index=current_index, key="dataset_registry_selection")
    selected = records[labels.index(selected_label)]
    st.session_state["selected_dataset_id"] = selected.get("dataset_id")
    details = [
        {"Field": "Dataset ID", "Value": selected.get("dataset_id", "Unavailable")},
        {"Field": "Source organization", "Value": selected.get("source_organization") or "Not recorded"},
        {"Field": "Reporting period", "Value": selected.get("reporting_period") or "Not recorded"},
        {"Field": "Documentation", "Value": _pretty_status(selected.get("documentation_status"))},
        {"Field": "Survey design", "Value": _pretty_status(selected.get("survey_design_status"))},
        {"Field": "Survey weight", "Value": _pretty_status(selected.get("survey_weight_status"))},
        {"Field": "Data quality", "Value": _pretty_status(selected.get("data_quality_status"))},
        {"Field": "Limitations", "Value": "; ".join(str(item) for item in selected.get("limitations", [])) or "Not recorded"},
    ]
    st.dataframe(details, hide_index=True, width="stretch")
    st.info("This registry is a formal review boundary. Your supplied local material is authorized for local analysis; formal analytical and publication eligibility are separate metadata decisions.")


def render_source_inventory(project_root: Path) -> None:
    """Render aggregate source-inventory metadata without exposing file records."""

    metadata = _metadata(project_root)
    page_header(
        "Data management",
        "Source inventory",
        "A safe aggregate snapshot of the approved data directory. The inventory identifies structure and readiness state without displaying source records.",
    )
    if metadata.inventory_error or not metadata.inventory:
        empty_state("Source inventory unavailable", metadata.inventory_error or "No inventory snapshot is available.", tone="blocked")
        return
    summary = inventory_summary(metadata.inventory)
    if summary is None:
        empty_state("Source inventory could not be summarized", "The inventory shape is not valid, so no counts are shown.", tone="blocked")
        return
    freshness = (metadata.research_readiness or {}).get("inventory", {})
    if freshness.get("status") != "current":
        st.warning("The inventory snapshot is not current relative to the approved data directory. Counts are shown for review only; regenerate the inventory before relying on them.")
    metrics = st.columns(4, gap="medium")
    with metrics[0]:
        metric_card("Inventory files", str(summary["file_count"]), "Aggregate file count")
    with metrics[1]:
        metric_card("Formats", str(len(summary["formats"])), "Distinct recorded formats")
    with metrics[2]:
        metric_card("Duplicate groups", str(summary["duplicate_checksum_group_count"]), "Checksum review signal")
    with metrics[3]:
        metric_card("Authorization", str(summary["authorization_counts"].get("unverified", 0)), "Files still unverified")
    st.divider()
    section_header("Inventory snapshot", "Structural metadata only", "No filenames, paths, checksums, rows, columns, or source values are rendered here.")
    snapshot_rows = [
        {"Field": "Inventory version", "Value": str(metadata.inventory.get("inventory_version", "Unavailable"))},
        {"Field": "Generated at (UTC)", "Value": str(metadata.inventory.get("generated_at_utc", "Unavailable"))},
        {"Field": "Freshness", "Value": _pretty_status(freshness.get("status", "unavailable"))},
        {"Field": "Current approved files", "Value": str(freshness.get("current_file_count", "Unavailable"))},
        {"Field": "Publication-eligible files", "Value": str(summary["publication_counts"].get("True", 0))},
    ]
    st.dataframe(snapshot_rows, hide_index=True, width="stretch")
    format_rows = [{"Format": key.upper(), "Count": value} for key, value in sorted(summary["formats"].items())]
    if format_rows:
        section_header("Recorded formats", "Aggregate counts", "Format counts are inventory metadata and do not establish permission to open or publish a source.")
        st.dataframe(format_rows, hide_index=True, width="stretch")
    st.info("Inventory presence is not authorization. See Research Readiness and Evidence & Provenance for the review gates that remain outstanding.")


def render_codebooks_variables(project_root: Path) -> None:
    """Render catalogue-linked documentation and variable metadata."""

    metadata = _metadata(project_root)
    page_header(
        "Data management",
        "Codebooks & variables",
        "Trace candidate concepts to their documented source references and variable requirements without inferring meaning from names or opening source records.",
    )
    if metadata.catalogue_error:
        st.error(metadata.catalogue_error)
        return
    definitions = list(metadata.catalogue.values())
    rows = []
    for definition in definitions:
        documentation = definition.get("source_documentation") or []
        rows.append(
            {
                "Indicator": definition.get("display_name", "Unavailable"),
                "Candidate sources": ", ".join(str(item) for item in definition.get("source_dataset_candidates", [])) or "Not recorded",
                "Documentation references": len(documentation),
                "Required variables": len(definition.get("required_variables") or []),
                "Codebook evidence": _pretty_status(definition.get("evidence_status")),
            }
        )
    section_header("Catalogue-linked documentation", "What is documented today", "A local questionnaire or report is recorded as a reference only; it does not verify the matching data release or authorize analysis.")
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    for definition in definitions:
        with st.expander(f"{definition.get('display_name', 'Unnamed concept')} · {definition.get('indicator_id', 'unknown')}"):
            st.write(definition.get("description", "Description unavailable."))
            st.caption(f"Evidence status: {_pretty_status(definition.get('evidence_status'))}")
            documentation = definition.get("source_documentation") or []
            if documentation:
                st.write(
                    [
                        {"Reference": item.get("path", "Unavailable"), "Status": _pretty_status(item.get("status"))}
                        for item in documentation
                        if isinstance(item, dict)
                    ]
                )
            else:
                st.write("No source-documentation reference is recorded for this concept.")
            st.write(f"Required variables: {', '.join(str(item) for item in definition.get('required_variables', [])) or 'None verified'}")
            st.write(f"Missing-value treatment: {definition.get('missing_value_treatment') or 'Not documented'}")
    st.warning("No variable meaning, response coding, universe, denominator, or codebook mapping is approved unless it appears as independently verified mapping metadata.")


def render_indicator_catalogue(project_root: Path) -> None:
    """Render the complete reviewable indicator catalogue."""

    metadata = _metadata(project_root)
    page_header(
        "Research & analytics",
        "Indicator catalogue",
        "The catalogue defines candidate policy concepts and their release gates. It is not a collection of calculated statistics.",
    )
    if metadata.catalogue_error:
        st.error(metadata.catalogue_error)
        return
    summary = catalogue_summary(metadata.catalogue)
    metrics = st.columns(4, gap="medium")
    with metrics[0]:
        metric_card("Candidate concepts", str(summary["indicator_count"]), "Reviewable definitions")
    with metrics[1]:
        metric_card("Verified mappings", str(summary["verified_mapping_count"]), "Codebook-backed only")
    with metrics[2]:
        metric_card("With blockers", str(summary["indicators_with_review_blockers"]), "Evidence still required")
    with metrics[3]:
        metric_card("Publication eligible", str(catalogue_readiness_summary(metadata)["publication_eligible_count"]), "Current metadata state")
    st.divider()
    readiness_by_id = {
        definition.get("indicator_id"): evaluate_catalogue_indicator(metadata, definition)
        for definition in metadata.catalogue.values()
        if definition.get("indicator_id")
    }
    render_catalogue_table(metadata.catalogue.values(), readiness_by_id)
    st.caption("Definitions, statuses, and blockers are metadata. No indicator value is calculated on this page.")


def render_variable_mapping(project_root: Path) -> None:
    """Render codebook mapping coverage and the records currently present."""

    metadata = _metadata(project_root)
    page_header(
        "Research & analytics",
        "Variable mapping",
        "Review the link between catalogue concepts and exact source variables. Similar variable names are never treated as a verified mapping.",
    )
    report = metadata.research_readiness
    if report is None:
        empty_state("Mapping report unavailable", "No mapping conclusion is shown because the readiness metadata could not be validated.", tone="blocked")
        return
    mapping_summary = report.get("mapping_summary") or {}
    metrics = st.columns(3, gap="medium")
    with metrics[0]:
        metric_card("Catalogue indicators", str(mapping_summary.get("indicator_count", 0)), "Definitions in scope")
    with metrics[1]:
        metric_card("Documented mappings", str(mapping_summary.get("indicators_with_documented_mappings", 0)), "Records present in metadata")
    with metrics[2]:
        metric_card("Verified mappings", str(mapping_summary.get("indicators_with_verified_mappings", 0)), "Independently reviewed")
    st.divider()
    section_header("Mapping coverage", "Indicator-level status", "A verified mapping requires codebook evidence, exact variable meaning, response coding, universe, denominator, and missing-value treatment.")
    rows = []
    for row in mapping_summary.get("rows", []):
        if isinstance(row, dict):
            rows.append(
                {
                    "Indicator": row.get("display_name", "Unavailable"),
                    "Status": _pretty_status(row.get("mapping_status")),
                    "Mapping records": row.get("mapping_count", 0),
                    "Evidence references": "; ".join(str(item) for item in row.get("evidence_references", []) if item) or "None recorded",
                }
            )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    documented = [
        record
        for definition in metadata.catalogue.values()
        for record in definition.get("mapping_records", [])
        if isinstance(record, dict)
    ]
    if documented:
        section_header("Documented records", "Source-variable detail", "These records remain subject to the status shown in the catalogue.")
        st.dataframe(
            [
                {
                    "Indicator": record.get("indicator_id", "Unavailable"),
                    "Dataset": record.get("source_dataset_id", "Unavailable"),
                    "Source variable": record.get("source_variable", "Unavailable"),
                    "Status": _pretty_status(record.get("status")),
                    "Codebook reference": record.get("codebook_reference", "Unavailable"),
                }
                for record in documented
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        empty_state("No mapping records", "The catalogue currently contains no codebook-backed mapping records. All candidate concepts remain blocked.", tone="blocked")


def render_statistical_analysis(project_root: Path) -> None:
    """Show the calculation boundary without exposing an unapproved analysis control."""

    metadata = _metadata(project_root)
    page_header(
        "Research & analytics",
        "Statistical analysis",
        "A controlled calculation boundary for future approved estimates. Current sources and indicator definitions do not satisfy the required gates.",
    )
    readiness = catalogue_readiness_summary(metadata)
    metrics = st.columns(3, gap="medium")
    with metrics[0]:
        metric_card("Analysis-ready indicators", str(readiness["analysis_eligible_count"]), "Explicit eligibility only")
    with metrics[1]:
        metric_card("Publication-ready indicators", str(readiness["publication_eligible_count"]), "Separate publication gate")
    with metrics[2]:
        metric_card("Blocked indicators", str(readiness["blocked_count"]), "No estimate is produced")
    st.divider()
    empty_state(
        "Analysis is currently blocked",
        "No statistical estimate, model, ranking, trend, or geographic comparison is calculated because the current registry entries lack verified authorization, codebook mappings, approved methodology, survey-design evidence, and publication review.",
        tone="blocked",
    )
    section_header("Calculation gate", "Requirements before an estimate can appear", "The analytical service rejects unresolved definitions and unavailable verified variables; this page does not bypass those controls.")
    for number, (title, message) in enumerate(
        [
            ("Authorized source", "Record provenance, permitted processing purpose, and applicable terms."),
            ("Verified mapping", "Map exact source variables to approved populations, denominators, coding, and missing-value rules."),
            ("Defensible method", "Approve weights, survey design, uncertainty, quality checks, and interpretation limits."),
            ("Publication review", "Complete disclosure and publication review separately from analytical eligibility."),
        ],
        start=1,
    ):
        render_workflow_step(f"0{number}", title, message)


def render_research_methodology(project_root: Path) -> None:
    """Render the statistical-methodology workflow and current approval state."""

    metadata = _metadata(project_root)
    page_header(
        "Research & analytics",
        "Research methodology",
        "The statistical definitions, populations, weighting decisions, uncertainty rules, and limitations required for defensible analysis.",
    )
    section_header("Methodology framework", "Definitions before estimates", "The project records methodology gates explicitly and does not infer approval from a working parser or a similarly named variable.")
    columns = st.columns(2, gap="large")
    with columns[0]:
        render_workflow_step("01", "Define the measure", "Record the numerator, denominator, eligible population, unit, exclusions, and interpretation.")
        render_workflow_step("02", "Review source variables", "Use an authoritative codebook and questionnaire to document response coding and missing values.")
    with columns[1]:
        render_workflow_step("03", "Respect survey design", "Identify approved weights, strata, clusters, and the variance method for the dataset.")
        render_workflow_step("04", "Publish carefully", "Separate analytical eligibility from disclosure, licensing, and publication permission.")
    st.divider()
    section_header("Current methodology gates", "Readiness from validated metadata", "These statuses are current evidence states, not claims that a method has been approved.")
    report = metadata.research_readiness
    requirements = (report or {}).get("requirements", [])
    rows = [
        {
            "Requirement": _pretty_status(item.get("requirement")),
            "Status": _pretty_status(item.get("status")),
            "Next action": item.get("next_action", "Review required."),
        }
        for item in requirements
        if isinstance(item, dict)
    ]
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        empty_state("Methodology status unavailable", "No readiness requirements are available for review.", tone="blocked")
    st.divider()
    section_header("Source documents", "Project methodology references")
    st.markdown(
        f"- [Methodology template]({_safe_docs_link(project_root, 'docs/methodology.md')})\n"
        f"- [Indicator methodology]({_safe_docs_link(project_root, 'docs/indicator-methodology.md')})\n"
        f"- [Data quality guidance]({_safe_docs_link(project_root, 'docs/data-quality.md')})\n"
        f"- [Controlled analytics boundary]({_safe_docs_link(project_root, 'docs/phase9-analytics.md')})"
    )


def render_reports_exports(project_root: Path) -> None:
    """Explain the safe export boundary without exporting ineligible results."""

    metadata = _metadata(project_root)
    page_header(
        "Governance & reports",
        "Reports & exports",
        "A publication-safe boundary for future approved reports. Restricted data and publication-ineligible outputs are never exported from this page.",
    )
    report = metadata.research_readiness
    publication_eligible = bool((report or {}).get("publication_eligibility"))
    metrics = st.columns(3, gap="medium")
    with metrics[0]:
        metric_card("Publication eligibility", "Eligible" if publication_eligible else "Not eligible", "Current readiness conclusion")
    with metrics[1]:
        metric_card("Approved outputs", "0", "No approved report artifact is recorded")
    with metrics[2]:
        metric_card("Disclosure review", "Required", "Separate from analytical readiness")
    st.divider()
    if publication_eligible:
        st.info("Publication eligibility is recorded, but this interface still requires an explicit approved output definition before adding an export action.")
    else:
        empty_state(
            "Exports are currently unavailable",
            "There are no publication-eligible indicators or approved report artifacts. The page intentionally exposes no download control for restricted or unverified data.",
            tone="blocked",
        )
    section_header("Export gate", "What must be recorded first", "A future export must be tied to an approved aggregate, source provenance, disclosure review, licensing terms, and a reproducible report specification.")
    for title, message in [
        ("Approved analytical output", "The underlying indicator must pass the controlled analytical eligibility checks."),
        ("Publication and disclosure review", "A responsible reviewer must approve the output scope and disclosure risk."),
        ("Provenance and limitations", "The report must identify its source, vintage, definitions, weighting, uncertainty, and limitations."),
    ]:
        st.markdown(f"**{title}** — {message}")


def render_evidence_provenance(project_root: Path) -> None:
    """Render evidence-register and source-matrix provenance in a focused view."""

    metadata = _metadata(project_root)
    page_header(
        "Governance & reports",
        "Evidence & provenance",
        "Trace the evidence behind source identity, authorization, mappings, methodology, geography, and publication decisions.",
    )
    report = metadata.research_readiness
    if report is None:
        empty_state("Evidence report unavailable", "No provenance conclusion is shown because the readiness metadata could not be validated.", tone="blocked")
        return
    evidence = report.get("evidence") or {}
    evidence_summary = evidence.get("summary") or {}
    source = report.get("source_verification") or {}
    source_summary = source.get("summary") or {}
    metrics = st.columns(4, gap="medium")
    with metrics[0]:
        metric_card("Evidence requirements", str(evidence_summary.get("total", 0)), "Validated register items")
    with metrics[1]:
        metric_card("Verified evidence", str(evidence_summary.get("verified", 0)), "Explicitly reviewed only")
    with metrics[2]:
        metric_card("Source records", str(source_summary.get("source_count", 0)), "Source-verification matrix")
    with metrics[3]:
        metric_card("Manual reviews", str(source_summary.get("manual_verification_count", 0)), "Still requiring human review")
    st.divider()
    section_header("Evidence register", "Status by evidence category", "The register records what is missing or unverified; this page cannot approve or upgrade a status.")
    category_rows = [{"Category": _pretty_status(key), "Count": value} for key, value in sorted((evidence_summary.get("category_counts") or {}).items())]
    if category_rows:
        st.dataframe(category_rows, hide_index=True, width="stretch")
    else:
        empty_state("No evidence categories", "The evidence register contains no validated categories.", tone="blocked")
    st.divider()
    section_header("Source verification", "Public references versus verified provenance", "A public URL can support discovery or citation, but it does not prove that a local file is the same release or that microdata may be analyzed or redistributed.")
    source_rows = []
    for item in source.get("sources", []):
        if isinstance(item, dict):
            source_rows.append(
                {
                    "Source": item.get("source_title") or item.get("candidate_dataset_name") or "Unavailable",
                    "Organization": item.get("source_organization") or "Unknown",
                    "Verification": _pretty_status(item.get("verification_status")),
                    "Permission": _pretty_status(item.get("permission_status")),
                    "References": len(item.get("source_references", [])),
                    "Manual review": "Required" if item.get("manual_verification_required") else "Not recorded",
                }
            )
    if source_rows:
        st.dataframe(source_rows, hide_index=True, width="stretch")
    else:
        empty_state("Source matrix unavailable", "No source-verification records are shown.", tone="blocked")
    st.info("Evidence and provenance are intentionally read-only in the application. A responsible reviewer must update the metadata register before any eligibility state changes.")


def render_methodology_sources(project_root: Path) -> None:
    metadata = _metadata(project_root)
    page_header(
        "Trust and provenance",
        "Methodology & sources",
        "The rules behind every future result: source authorization, indicator definitions, survey design, uncertainty, and publication review.",
    )
    st.markdown(
        "The application is designed to make uncertainty visible. A candidate concept is not an approved statistic, and a file available locally is not automatically authorized for analysis or publication."
    )
    columns = st.columns(2, gap="large")
    with columns[0]:
        section_header("Data governance", "Controlled by default")
        st.markdown(
            "- Raw or restricted microdata must remain in controlled storage.\n"
            "- Derived outputs need provenance and disclosure-risk review.\n"
            "- Source authorization, licensing, and attribution are recorded separately.\n"
            "- No household-level linkage is inferred from similar schemas."
        )
        st.caption(f"Reference: {_safe_docs_link(project_root, 'docs/data-governance.md')}")
    with columns[1]:
        section_header("Indicator methodology", "Definitions before estimates")
        st.markdown(
            "- Numerators, denominators, eligibility, and exclusions are explicit.\n"
            "- Weights are dataset-specific and never silently replaced by unweighted estimates.\n"
            "- Missingness is reported, not automatically treated as an error.\n"
            "- Representativeness and confidence intervals require sampling-design evidence."
        )
        st.caption(f"Reference: {_safe_docs_link(project_root, 'docs/indicator-methodology.md')}")
    st.divider()
    phase13 = _phase13(metadata, project_root)
    section_header("Phase 13 candidate specification", "FI-ACCESS-001 remains uncalculated", "No numerator, denominator, response coding, or verified variable mapping has been established from a release-matched reviewed codebook.")
    st.warning("A genuine estimate is blocked pending authorized microdata, written permitted-use terms, reviewed codebook/questionnaire and survey-design documentation, independent mapping review, approved data quality, and domain approval. No variable names or statistics are inferred.")
    st.caption(f"Candidate status: {phase13.get('status', 'blocked')} · Publication eligible: {'yes' if phase13.get('publication_eligible') else 'no'}")
    definition_fields = (phase13.get("definition_review") or {}).get("fields", [])
    if definition_fields:
        st.dataframe(
            [
                {"FI-ACCESS-001 field": row.get("label"), "Status": _pretty_status(row.get("status")), "Value": row.get("value") or "Not established", "Evidence": row.get("evidence_reference") or "None reviewed", "Next action": row.get("next_action")}
                for row in definition_fields
            ],
            hide_index=True,
            width="stretch",
        )
    source_rows = []
    for source in (metadata.source_verification or {}).get("sources", []):
        for reference in source.get("source_references", []):
            source_rows.append({
                "Source": source.get("source_title") or source.get("candidate_dataset_name"),
                "Release": reference.get("release_identifier") or source.get("release_version") or "Not recorded",
                "Type": _pretty_status(reference.get("source_type")),
                "Official URL": reference.get("url"),
                "Reference status": _pretty_status(reference.get("status")),
                "Exact-release applicability": _pretty_status(reference.get("exact_release_applicability")),
                "Last checked": reference.get("last_checked") or "Not recorded",
            })
    if source_rows:
        section_header("Official source references", "Public page, document review, and access are distinct", "A reference status does not establish that a document was downloaded/reviewed or microdata access was granted.")
        st.dataframe(source_rows, hide_index=True, width="stretch", column_config={"Official URL": st.column_config.LinkColumn("Official URL")})
    document_rows = [
        {"Source": source.get("source_title") or source.get("candidate_dataset_name"), "Document": doc.get("document_id"), "Type": doc.get("document_type"), "Path": doc.get("path"), "Release": doc.get("release_identifier"), "Document status": _pretty_status(doc.get("status")), "Exact release": _pretty_status(doc.get("exact_release_status")), "Review": _pretty_status(doc.get("review_status")), "SHA-256": doc.get("sha256") or "Not recorded"}
        for source in (metadata.source_verification or {}).get("sources", [])
        for doc in source.get("documentation_records", [])
    ]
    if document_rows:
        st.dataframe(document_rows, hide_index=True, width="stretch")
    st.divider()
    section_header("Current evidence status", "What the project can say today")
    if metadata.catalogue_error:
        st.warning(metadata.catalogue_error)
    else:
        summary = catalogue_summary(metadata.catalogue)
        readiness_summary = catalogue_readiness_summary(metadata)
        st.write(
            f"The catalogue contains {summary['indicator_count']} candidate concepts and "
            f"{readiness_summary['blocked_count']} are blocked by current evidence. Current entries remain unverified for authorization and publication."
        )
        readiness_by_id = {
            definition.get("indicator_id"): evaluate_catalogue_indicator(metadata, definition)
            for definition in metadata.catalogue.values()
            if definition.get("indicator_id")
        }
        render_catalogue_table(metadata.catalogue.values(), readiness_by_id)
    st.divider()
    section_header(
        "Source verification workflow",
        "What remains before research use",
        "The readiness report records evidence gaps without changing authorization or indicator status.",
    )
    if metadata.research_readiness:
        blocked = [
            row
            for row in _research_readiness_rows(metadata.research_readiness)
            if row.get("Status") not in {"Verified", "Not Applicable"}
        ]
        if blocked:
            st.dataframe(blocked, hide_index=True, width="stretch")
        else:
            st.success("All documented gates are satisfied; publication eligibility still requires explicit approval.")
    else:
        st.warning("Source verification status is unavailable because the readiness report could not be validated.")
    st.divider()
    section_header("Dataset registry", "Safe metadata and governance state")
    if metadata.registry_error:
        st.warning(metadata.registry_error)
    else:
        st.write(
            f"The registry contains {len(metadata.registry)} dataset records. "
            "All current records remain unverified and unavailable for public analytical output until explicit evidence is recorded."
        )
    st.divider()
    section_header("Project documents", "Review the source-of-truth templates")
    st.markdown(
        f"- [README.md]({_safe_docs_link(project_root, 'README.md')})\n"
        f"- [docs/methodology.md]({_safe_docs_link(project_root, 'docs/methodology.md')})\n"
        f"- [docs/data-quality.md]({_safe_docs_link(project_root, 'docs/data-quality.md')})\n"
        f"- [docs/phase9-analytics.md]({_safe_docs_link(project_root, 'docs/phase9-analytics.md')})"
        f"\n- [docs/phase11-source-verification.md]({_safe_docs_link(project_root, 'docs/phase11-source-verification.md')})"
    )
    st.caption("These repository references are documentation links, not claims of NISR approval or official endorsement.")
