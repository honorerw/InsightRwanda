"""Small presentation components shared by Streamlit pages."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from insightrwanda.analytics.readiness import ReadinessResult
from insightrwanda.analytics.insights import (
    filter_verified_insights,
    interpret_verified_insight,
    verified_filter_options,
)

from .metadata import status_label


_BLOCKER_CATEGORY_LABELS = {
    "authorization": "Dataset authorization and permitted use",
    "source": "Source verification and official release",
    "local_data": "Local dataset availability",
    "mapping": "Codebook and variable mappings",
    "methodology": "Indicator definition and calculation methodology",
    "quality": "Data quality and missing-value handling",
    "survey": "Survey weights and sampling design",
    "geography": "Geographic compatibility",
    "publication": "Disclosure control and publication approval",
    "other": "Other readiness requirements",
}

_BLOCKER_CATEGORY_ORDER = tuple(_BLOCKER_CATEGORY_LABELS)

_BLOCKER_ID_CATEGORIES = {
    "dataset_authorization": "authorization",
    "source_access_authorization": "authorization",
    "source_analysis_approval": "authorization",
    "permitted_use": "authorization",
    "source_provenance": "source",
    "source_reference_review": "source",
    "source_release_identity": "source",
    "source_document_review": "mapping",
    "dataset_documentation": "mapping",
    "approved_registered_path": "local_data",
    "source_file_availability": "local_data",
    "release_match": "source",
    "calculation_specification": "methodology",
    "calculation_specification_approval": "methodology",
    "definition_review": "methodology",
    "complete_definition_review": "methodology",
    "approved_definition_and_methodology": "methodology",
    "data_quality_acceptance": "quality",
    "eligibility_and_missingness_rules": "quality",
    "verified_variable_mappings": "mapping",
    "mapping_evidence": "mapping",
    "required_columns": "mapping",
    "value_semantics": "mapping",
    "questionnaire_and_codebook_review": "mapping",
    "survey_weight_and_design": "survey",
    "weight_variable_and_interpretation": "survey",
    "survey_design_supported": "survey",
    "variance_estimation_supported": "survey",
    "publication_permission": "publication",
    "disclosure_status": "publication",
    "disclosure_requirements": "publication",
    "publication_eligibility": "publication",
    "publication_status": "publication",
    "geographic_resource_verified": "geography",
    "geographic_assets": "geography",
    "geographic_crosswalk": "geography",
}

_EVIDENCE_CATEGORY_CATEGORIES = {
    "authorization": "authorization",
    "dataset_provenance": "source",
    "documentation": "mapping",
    "licensing": "publication",
    "data_quality": "quality",
    "survey_design": "survey",
    "variable_mapping": "mapping",
    "indicator_methodology": "methodology",
    "geography": "geography",
    "disclosure_publication": "publication",
}

_ACTION_GROUP_ORDER = (
    "source_acquisition",
    "authorization_and_permitted_use",
    "codebook_acquisition",
    "variable_mapping_review",
    "survey_methodology_and_weighting",
    "data_quality_review",
    "publication_and_disclosure_review",
    "geographic_resources",
)

_ACTION_GROUP_LABELS = {
    "source_acquisition": "Confirm dataset identity and official release",
    "authorization_and_permitted_use": "Confirm authorization and permitted use",
    "codebook_acquisition": "Obtain the matching codebook and questionnaire",
    "variable_mapping_review": "Verify indicator definition and source-variable mappings",
    "survey_methodology_and_weighting": "Verify survey weights and sampling design",
    "data_quality_review": "Complete data-quality and missing-value review",
    "publication_and_disclosure_review": "Obtain disclosure and publication approval",
    "geographic_resources": "Verify geographic compatibility",
}


def _readable_status(value: Any) -> str:
    return str(value or "unavailable").replace("_", " ").title()


def _category_for_blocker(identifier: Any, evidence_category: Any = None) -> str:
    identifier_text = str(identifier or "")
    if identifier_text in _BLOCKER_ID_CATEGORIES:
        return _BLOCKER_ID_CATEGORIES[identifier_text]
    return _EVIDENCE_CATEGORY_CATEGORIES.get(str(evidence_category or ""), "other")


def _title_for_blocker(identifier: Any, category: str) -> str:
    explicit = {
        "dataset_authorization": "Dataset authorization",
        "source_provenance": "Official source provenance",
        "source_release_identity": "Exact official release identity",
        "source_file_availability": "Local dataset availability",
        "verified_variable_mappings": "Verified codebook mappings",
        "mapping_evidence": "Mapping evidence",
        "calculation_specification": "Calculation specification",
        "definition_review": "Indicator definition review",
        "data_quality_acceptance": "Data-quality acceptance",
        "survey_weight_and_design": "Survey weights and sampling design",
        "publication_permission": "Publication permission",
    }
    return explicit.get(str(identifier), str(identifier or _BLOCKER_CATEGORY_LABELS.get(category, "Readiness requirement")).replace("_", " ").title())


def _scoped_evidence_items(
    report: dict[str, Any] | None,
    *,
    indicator_id: str | None = None,
    dataset_id: str | None = None,
    include_geography: bool = True,
) -> list[dict[str, Any]]:
    evidence = report.get("evidence") if isinstance(report, dict) else None
    items = evidence.get("blockers") if isinstance(evidence, dict) else None
    if not isinstance(items, list):
        items = evidence.get("items") if isinstance(evidence, dict) else []
    result = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") in {"verified", "not_applicable"}:
            continue
        if not include_geography and "geography" in (item.get("blocks") or []) and item.get("category") == "geography":
            continue
        related_indicator = item.get("related_indicator_id")
        related_dataset = item.get("related_dataset_id")
        if indicator_id or dataset_id:
            is_related = related_indicator == indicator_id or related_dataset == dataset_id
            is_global_publication = not related_indicator and not related_dataset and item.get("category") == "disclosure_publication"
            if not is_related and not is_global_publication:
                continue
        result.append(item)
    return result


def build_evidence_blocker_records(
    report: dict[str, Any] | None,
    *,
    indicator_id: str | None = None,
    dataset_id: str | None = None,
    include_geography: bool = True,
) -> list[dict[str, Any]]:
    """Convert existing evidence-register blockers into readable UI records."""

    records = []
    for item in _scoped_evidence_items(
        report,
        indicator_id=indicator_id,
        dataset_id=dataset_id,
        include_geography=include_geography,
    ):
        category = _category_for_blocker(item.get("evidence_id"), item.get("category"))
        records.append(
            {
                "identifier": item.get("evidence_id") or "evidence_requirement",
                "requirement_id": item.get("evidence_id"),
                "title": item.get("description") or "Evidence requirement",
                "category": category,
                "category_label": _BLOCKER_CATEGORY_LABELS[category],
                "status": item.get("status", "missing"),
                "why_it_matters": item.get("reason_for_blocking") or "Supporting evidence is not verified.",
                "required_action": item.get("next_action") or "Record and review the required evidence.",
                "evidence_needed": [item.get("description") or "Documented supporting evidence"],
                "evidence_ids": [item.get("evidence_id")] if item.get("evidence_id") else [],
                "evidence_references": [item.get("evidence_reference")] if item.get("evidence_reference") else [],
                "related_dataset_id": item.get("related_dataset_id"),
                "related_indicator_id": item.get("related_indicator_id"),
            }
        )
    return records


def build_readiness_blocker_records(
    readiness: dict[str, Any] | None,
    report: dict[str, Any] | None,
    *,
    indicator_id: str | None = None,
    dataset_id: str | None = None,
    include_geography: bool = False,
) -> list[dict[str, Any]]:
    """Enrich central readiness blockers with matching evidence metadata.

    This is a presentation transform only. Eligibility and evidence status are
    still read from the central evaluator and validated readiness report.
    """

    readiness = readiness if isinstance(readiness, dict) else {}
    blocked_checks = [str(item) for item in readiness.get("blocked_checks", []) if item]
    publication_checks = [str(item) for item in readiness.get("publication_blocked_checks", []) if item]
    messages = [str(item) for item in readiness.get("messages", []) if item]
    check_messages = dict(zip(blocked_checks + publication_checks, messages))
    evidence_items = _scoped_evidence_items(
        report,
        indicator_id=indicator_id,
        dataset_id=dataset_id,
        include_geography=include_geography,
    )
    records: list[dict[str, Any]] = []
    for identifier in dict.fromkeys([*blocked_checks, *publication_checks]):
        category = _category_for_blocker(identifier)
        candidates = [
            item
            for item in evidence_items
            if _category_for_blocker(item.get("evidence_id"), item.get("category")) == category
        ]
        evidence_needed = list(dict.fromkeys(
            str(item.get("description"))
            for item in candidates
            if item.get("description")
        ))
        evidence_ids = list(dict.fromkeys(
            str(item.get("evidence_id"))
            for item in candidates
            if item.get("evidence_id")
        ))
        evidence_references = list(dict.fromkeys(
            str(item.get("evidence_reference"))
            for item in candidates
            if item.get("evidence_reference")
        ))
        required_action = next(
            (str(item.get("next_action")) for item in candidates if item.get("next_action")),
            "Record and review the supporting evidence in the existing readiness register.",
        )
        records.append(
            {
                "identifier": identifier,
                "requirement_id": identifier,
                "title": _title_for_blocker(identifier, category),
                "category": category,
                "category_label": _BLOCKER_CATEGORY_LABELS[category],
                "status": "blocked",
                "why_it_matters": check_messages.get(identifier) or "This readiness requirement is unresolved.",
                "required_action": required_action,
                "evidence_needed": evidence_needed or ["A reviewed evidence record linked to this requirement"],
                "evidence_ids": evidence_ids,
                "evidence_references": evidence_references,
                "evidence_statuses": list(dict.fromkeys(str(item.get("status", "missing")) for item in candidates)),
                "related_dataset_id": dataset_id,
                "related_indicator_id": indicator_id,
            }
        )
    if records:
        return records
    return build_evidence_blocker_records(
        report,
        indicator_id=indicator_id,
        dataset_id=dataset_id,
        include_geography=include_geography,
    )


def render_readiness_blocker_groups(records: Iterable[dict[str, Any]]) -> None:
    """Render readable, grouped blocker cards without concatenated warnings."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if isinstance(record, dict):
            grouped.setdefault(str(record.get("category", "other")), []).append(record)
    if not grouped:
        empty_state("No unresolved blockers", "No unresolved readiness records are available for this scope.")
        return
    for category in [*(_BLOCKER_CATEGORY_ORDER), *sorted(set(grouped) - set(_BLOCKER_CATEGORY_ORDER))]:
        items = grouped.get(category, [])
        if not items:
            continue
        with st.expander(f"{_BLOCKER_CATEGORY_LABELS.get(category, category.title())} · {len(items)} blocker(s)"):
            for record in items:
                with st.container(border=True):
                    st.markdown(f"**{record.get('title') or record.get('identifier') or 'Readiness requirement'}**")
                    identifier = record.get("identifier") or record.get("requirement_id") or "Not recorded"
                    st.caption(f"Requirement: {identifier} · Status: {_readable_status(record.get('status'))}")
                    st.markdown("**Why it matters**")
                    st.write(record.get("why_it_matters") or "Explanation not recorded.")
                    st.markdown("**Required action**")
                    st.write(record.get("required_action") or "Review the readiness register.")
                    evidence_needed = record.get("evidence_needed") or []
                    if evidence_needed:
                        st.markdown("**Evidence needed**")
                        for item in evidence_needed:
                            st.write(f"• {item}")
                    evidence_ids = record.get("evidence_ids") or []
                    evidence_statuses = record.get("evidence_statuses") or []
                    if evidence_ids:
                        st.caption(f"Evidence ID(s): {', '.join(str(item) for item in evidence_ids)}")
                    else:
                        st.caption(f"Evidence ID: not recorded · requirement ID: {identifier}")
                    if evidence_statuses:
                        st.caption("Evidence status: " + ", ".join(_readable_status(item) for item in evidence_statuses))
                    references = record.get("evidence_references") or []
                    if references:
                        st.caption("Recorded reference: " + ", ".join(str(item) for item in references))


def prepare_researcher_action_plan(
    action_plan: dict[str, list[dict[str, Any]]] | None,
    *,
    indicator_id: str | None = None,
    dataset_id: str | None = None,
    include_geography: bool = False,
) -> list[dict[str, Any]]:
    """Select and order existing unresolved action-plan tasks for display."""

    if not isinstance(action_plan, dict):
        return []
    ordered_groups = [*(_ACTION_GROUP_ORDER), *sorted(set(action_plan) - set(_ACTION_GROUP_ORDER))]
    tasks: list[dict[str, Any]] = []
    for priority, group in enumerate(ordered_groups, start=1):
        for task in action_plan.get(group, []) or []:
            if not isinstance(task, dict) or task.get("status") in {"verified", "not_applicable"}:
                continue
            task_dataset = task.get("related_dataset_id") or task.get("affected_dataset_id")
            task_indicator = task.get("related_indicator_id") or task.get("affected_indicator_id")
            if dataset_id and task_dataset and task_dataset != dataset_id:
                continue
            if indicator_id and task_indicator and task_indicator != indicator_id:
                continue
            if not include_geography and "geography" in (task.get("blocks") or []):
                continue
            tasks.append(
                {
                    **task,
                    "group": group,
                    "group_label": _ACTION_GROUP_LABELS.get(group, group.replace("_", " ").title()),
                    "priority": priority,
                }
            )
    return tasks


def render_researcher_action_plan(tasks: Iterable[dict[str, Any]]) -> None:
    """Render action tasks as responsive cards, preserving metadata status."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        if isinstance(task, dict):
            grouped.setdefault(str(task.get("group", "other")), []).append(task)
    if not grouped:
        empty_state("No unresolved action items", "All supplied action-plan requirements are verified or not applicable.")
        return
    for group, group_tasks in grouped.items():
        label = str(group_tasks[0].get("group_label", group.replace("_", " ").title()))
        with st.expander(f"{label} · {len(group_tasks)} task(s)"):
            for task in group_tasks:
                with st.container(border=True):
                    status = _readable_status(task.get("status"))
                    st.markdown(f"**Priority {task.get('priority', '—')} · {status}**")
                    st.write(task.get("description") or task.get("next_action") or "Research task not described.")
                    st.markdown("**Required task**")
                    st.write(task.get("next_action") or "Review the linked evidence requirement.")
                    st.markdown("**Expected evidence**")
                    st.write(task.get("description") or "A documented evidence record linked to the requirement.")
                    st.caption(
                        "Evidence ID: " + str(task.get("evidence_id") or task.get("source_id") or "Not recorded")
                        + " · Dataset: " + str(task.get("related_dataset_id") or task.get("candidate_dataset_name") or "Not recorded")
                        + " · Indicator: " + str(task.get("related_indicator_id") or "Not recorded")
                    )
                    st.caption("Current status: " + status)
                    st.caption(task.get("completion_criterion") or "Manual reviewer confirmation is required.")


def page_header(eyebrow: str, title: str, description: str) -> None:
    """Render the consistent application brand and page heading."""

    st.markdown(
        f"""
        <div class="app-header">
          <div class="app-brand">InsightRwanda</div>
          <div class="app-header-meta"><span>Research workspace</span><span class="header-status">Foundation mode</span></div>
        </div>
        <div class="page-heading">
          <div class="eyebrow">{eyebrow}</div>
          <h1 class="page-title">{title}</h1>
          <p class="hero-copy">{description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(kicker: str, title: str, description: str | None = None) -> None:
    st.markdown(
        f"<div class='section-kicker'>{kicker}</div><h2>{title}</h2>",
        unsafe_allow_html=True,
    )
    if description:
        st.markdown(f"<p class='section-description'>{description}</p>", unsafe_allow_html=True)


def metric_card(label: str, value: str, note: str) -> None:
    st.markdown(
        f"<div class='metric-card' role='group' aria-label='{label}'>"
        f"<div class='metric-label'>{label}</div>"
        f"<div class='metric-value'>{value}</div><div class='metric-note'>{note}</div></div>",
        unsafe_allow_html=True,
    )


def render_indicator_readiness_summary(
    *,
    indicator_id: str,
    analysis_status: str,
    estimate_status: str,
    publication_status: str,
    blocker_count: int | None,
) -> None:
    """Render a compact indicator status strip without numeric fallbacks."""

    metrics = st.columns(5, gap="small")
    values = (
        ("Indicator ID", indicator_id, "Versioned catalogue identifier"),
        ("Status", analysis_status, "Central analytical readiness"),
        ("Estimate", estimate_status, "Aggregate result status"),
        ("Publication", publication_status, "Separate publication gate"),
        ("Blockers", str(blocker_count) if blocker_count is not None else "Unavailable", "Scoped readiness records"),
    )
    for column, (label, value, note) in zip(metrics, values):
        with column:
            metric_card(label, value, note)


def build_indicator_readiness_summary(
    phase13: dict[str, Any] | None,
    phase14: dict[str, Any] | None,
    *,
    indicator_id: str,
    blocker_count: int | None,
) -> dict[str, Any]:
    """Build display labels from existing readiness/calculation states."""

    phase13 = phase13 if isinstance(phase13, dict) else {}
    phase14 = phase14 if isinstance(phase14, dict) else {}
    result = phase14.get("result") if isinstance(phase14.get("result"), dict) else {}
    estimate_status = (
        "Calculated"
        if phase14.get("calculation_status") == "calculated" and result.get("estimate") is not None
        else "Not calculated"
    )
    publication_status = (
        "Approved"
        if phase14.get("publication_status") in {"approved", "eligible"}
        or phase13.get("publication_eligible") is True
        else "Not approved"
    )
    return {
        "indicator_id": indicator_id,
        "analysis_status": "Eligible" if phase13.get("analysis_eligible") is True else "BLOCKED",
        "estimate_status": estimate_status,
        "publication_status": publication_status,
        "blocker_count": blocker_count,
    }


def empty_state(title: str, message: str, *, tone: str = "default") -> None:
    class_name = "empty-state" if tone == "default" else f"empty-state {tone}"
    st.markdown(
        f"<div class='{class_name}' role='status' aria-live='polite'><h3>{title}</h3><p>{message}</p></div>",
        unsafe_allow_html=True,
    )


def render_blocker_cards(blockers: Iterable[dict[str, Any]]) -> None:
    """Render full blocker details in responsive native expanders, not a wide grid."""

    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        identifier = blocker.get("identifier") or blocker.get("Blocker ID") or blocker.get("Blocker") or "Blocker"
        reason = blocker.get("message") or blocker.get("Why it matters") or "Explanation unavailable."
        action = blocker.get("next_action") or blocker.get("Required action") or blocker.get("Human action") or "Review the readiness record for the next step."
        title = " ".join(str(reason).split())
        if len(title) > 104:
            title = title[:101].rstrip() + "…"
        with st.expander(f"{identifier} · {title}"):
            st.markdown("**Blocker ID**")
            st.write(str(identifier))
            st.markdown("**Why it matters**")
            st.write(str(reason))
            st.markdown("**Required action**")
            st.write(str(action))


def status_pill(status: str | None) -> None:
    label, class_name = status_label(status)
    st.markdown(f"<span class='status-pill {class_name}'>{label}</span>", unsafe_allow_html=True)


def indicator_card(
    definition: dict[str, Any],
    readiness: ReadinessResult | None = None,
    *,
    authorization_status: str | None = None,
) -> None:
    """Render catalogue metadata, never an estimate."""

    indicator_id = str(definition.get("indicator_id", "Unknown ID"))
    name = str(definition.get("display_name", "Unnamed indicator"))
    description = str(definition.get("description", "No description is available."))
    status = definition.get("status")
    label, class_name = status_label(status)
    blockers = definition.get("review_blockers") or []
    source_candidates = definition.get("source_dataset_candidates") or []
    with st.container(border=True):
        st.markdown(f"<div class='indicator-id'>{indicator_id}</div>", unsafe_allow_html=True)
        st.markdown(f"### {name}")
        st.markdown(f"<p class='muted'>{description}</p>", unsafe_allow_html=True)
        st.markdown(f"<span class='status-pill {class_name}'>{label}</span>", unsafe_allow_html=True)
        with st.expander("What is needed before calculation"):
            if readiness is not None:
                st.caption(
                    f"Readiness: {'Eligible for analysis' if readiness.analysis_eligible else 'Blocked pending evidence'} · "
                    f"Publication: {'Eligible' if readiness.publication_eligible else 'Not eligible'}"
                )
                blockers = list(dict.fromkeys([*blockers, *readiness.messages]))
            if blockers:
                st.write("Review requirements:")
                st.write([str(item) for item in blockers])
            else:
                st.write("No review requirements are recorded in the catalogue.")
            st.caption(f"Authorization: {authorization_status or definition.get('authorization_status', 'unavailable')}")
            st.caption(f"Publication: {definition.get('publication_status', 'unavailable')}")
            if source_candidates:
                st.caption("Candidate source: " + ", ".join(str(item) for item in source_candidates))


def render_domain_card(title: str, message: str, page_path: str, label: str) -> None:
    st.markdown(
        f"<div class='domain-card'><div class='section-kicker'>Analytical area</div>"
        f"<h3>{title}</h3><p>{message}</p></div>",
        unsafe_allow_html=True,
    )
    try:
        st.page_link(page_path, label=label, icon=":material/arrow_forward:")
    except StreamlitPageNotFoundError:
        # Standalone page execution is useful for smoke tests; the configured
        # app entry point still provides the real navigation link.
        st.caption(f"{label} · use the sidebar navigation")


def render_workflow_step(number: str, title: str, message: str) -> None:
    st.markdown(
        f"<div class='workflow-card'><div class='workflow-number'>{number}</div>"
        f"<h3>{title}</h3><p>{message}</p></div>",
        unsafe_allow_html=True,
    )


def render_research_narrative(insight: dict[str, Any] | None) -> bool:
    """Render a public-facing narrative only from an eligible verified insight."""

    if (
        not isinstance(insight, dict)
        or insight.get("status") != "verified"
        or insight.get("insight_status") != "verified"
        or insight.get("intended_use") != "public_display"
        or insight.get("analytical_eligibility") is not True
        or insight.get("publication_eligibility") is not True
        or insight.get("validation_status") != "pass"
        or insight.get("data_classification") != "authorized_aggregate"
    ):
        blocked_narrative = interpret_verified_insight(insight)
        st.info(blocked_narrative.get("text") or "A research narrative is unavailable because the linked aggregate is not eligible.")
        if blocked_narrative.get("next_actions"):
            st.caption("Next evidence: " + " ".join(blocked_narrative["next_actions"]))
        return False
    narrative = interpret_verified_insight(insight)
    if narrative.get("status") != "verified":
        st.info("A research narrative is unavailable because the verified aggregate interpretation could not be constructed.")
        return False

    st.subheader("Evidence-linked interpretation")
    st.write("**Research question:**", narrative["research_question"])
    st.write("**Indicator definition:**", narrative["indicator_definition"])
    st.write("**Source and release:**", f"{narrative['dataset_id']} · {narrative['dataset_release']}")
    st.write("**Population and period:**", f"{narrative['population_scope']} · {narrative['reference_period']}")
    st.write("**Supported descriptive finding:**", narrative["text"])
    if narrative.get("uncertainty"):
        interval = narrative["uncertainty"]
        st.write("**Validated uncertainty interval:**", f"{interval['lower']:g}–{interval['upper']:g} {interval['unit']}")
    else:
        st.caption("No uncertainty interval is displayed because validated unit-matched interval metadata is unavailable.")
    limitations = narrative.get("limitations") or []
    if limitations:
        st.write("**Limitations:**")
        for limitation in limitations:
            st.write(f"- {limitation}")
    st.caption("Descriptive result only; it does not establish causality, policy effectiveness, or impact.")
    return True


def render_verified_result_filters(
    insights: list[dict[str, Any]], *, intended_use: str = "public_display", key_prefix: str = "research"
) -> list[dict[str, Any]] | None:
    """Offer only evidence-backed filters and return an eligible subset.

    No selectors are shown for a single result. Every selected value is
    validated again by the analytics-layer filter before it is returned.
    """

    options = {
        field: verified_filter_options(insights, field, intended_use=intended_use)
        for field in ("indicator_id", "reference_period", "comparison_category")
    }
    filters: dict[str, str] = {}
    for field, values in options.items():
        if len(values) < 2:
            continue
        label = {
            "indicator_id": "Approved indicator",
            "reference_period": "Compatible survey period",
            "comparison_category": "Verified category",
        }[field]
        selected = st.selectbox(label, ["All eligible options", *values], key=f"{key_prefix}_{field}")
        if selected != "All eligible options":
            filters[field] = selected
    return filter_verified_insights(insights, filters=filters, intended_use=intended_use)


def render_catalogue_table(
    definitions: Iterable[dict[str, Any]], readiness_by_id: dict[str, ReadinessResult] | None = None
) -> None:
    rows = []
    for definition in definitions:
        label, _ = status_label(definition.get("status"))
        rows.append(
            {
                "Indicator": definition.get("display_name", "Unavailable"),
                "Status": label,
                "Authorization": definition.get("authorization_status", "Unavailable"),
                "Publication": definition.get("publication_status", "Unavailable"),
                "Analysis readiness": (
                    "Eligible"
                    if readiness_by_id and readiness_by_id.get(definition.get("indicator_id"), None) and readiness_by_id[definition.get("indicator_id")].analysis_eligible
                    else "Blocked"
                ),
            }
        )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        empty_state("Catalogue unavailable", "The indicator catalogue could not be validated, so no indicator statuses are shown.")
