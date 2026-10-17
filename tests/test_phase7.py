from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from insightrwanda.analytics.readiness import evaluate_indicator_readiness
from insightrwanda.ui.pages import (
    _boundary_figure,
    available_boundary_options,
    filter_indicator_definitions,
    financial_inclusion_filter_options,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Phase7InteractionTests(unittest.TestCase):
    def test_unvalidated_geographic_key_blocks_comparison(self) -> None:
        definition = {
            "indicator_id": "SYNTHETIC-GEO-001",
            "status": "derived_from_verified_variables",
            "evidence_status": "verified_codebook_mapping",
            "required_variables": ["respondent_status"],
            "definition_approval_status": "approved",
            "methodology_approval_status": "approved",
            "value_semantics_verified": True,
            "survey_weight_requirements": "",
        }
        dataset = {
            "authorization_status": "authorized_for_analysis",
            "analytical_eligibility": True,
            "codebook_status": "verified",
            "geography_status": "verified",
            "geographic_crosswalk_status": "verified",
            "geographic_variable": "district_id",
        }

        result = evaluate_indicator_readiness(
            definition,
            dataset,
            available_columns={"respondent_status"},
            requested_geography=True,
        )

        self.assertIn("validated_geography", result.blocked_checks)
        self.assertFalse(result.analysis_eligible)

    def test_indicator_filter_options_are_catalogue_backed(self) -> None:
        definitions = [
            {"indicator_id": "FI-ONE", "display_name": "First concept"},
            {"indicator_id": "FI-TWO", "display_name": "Second concept"},
        ]

        options = financial_inclusion_filter_options(definitions)

        self.assertEqual(options[0], ("All candidate concepts", None))
        self.assertEqual(options[1], ("First concept · FI-ONE", "FI-ONE"))
        self.assertEqual(
            [item["indicator_id"] for item in filter_indicator_definitions(definitions, "FI-TWO")],
            ["FI-TWO"],
        )
        self.assertEqual(filter_indicator_definitions(definitions, "FI-MISSING"), [])

    def test_boundary_options_include_only_existing_reviewed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boundary_dir = root / "data" / "geo"
            boundary_dir.mkdir(parents=True)
            (boundary_dir / "rw_districts_adm2_simplified.geojson").write_text("{}", encoding="utf-8")

            options = available_boundary_options(root)

        self.assertEqual(list(options), ["Districts · simplified"])
        self.assertNotIn("Provinces · simplified", options)

    def test_boundary_only_page_does_not_crash_when_references_are_missing(self) -> None:
        app = AppTest.from_file(PROJECT_ROOT / "app_pages" / "geographic_analysis.py").run(timeout=20)

        self.assertFalse(app.exception)
        self.assertTrue(any("Boundary reference unavailable" in item.value for item in app.markdown))

    def test_boundary_figure_contains_lines_without_analytical_fill(self) -> None:
        document = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"shapeName": "Synthetic boundary"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[29.5, -2.0], [29.6, -2.0], [29.6, -1.9], [29.5, -2.0]]],
                    },
                }
            ],
        }

        figure = _boundary_figure(document)

        self.assertEqual(len(figure.data), 1)
        self.assertEqual(figure.data[0].mode, "lines")
        self.assertIsNone(figure.data[0].fill)

    def test_indicator_filter_changes_the_displayed_catalogue_card(self) -> None:
        app = AppTest.from_file(PROJECT_ROOT / "app_pages" / "financial_inclusion.py").run(timeout=20)

        self.assertFalse(app.exception)
        self.assertEqual(len(app.selectbox), 1)
        selected = "Formal financial access · FI-ACCESS-001"
        self.assertIn(selected, list(app.selectbox[0].options))

        app.selectbox[0].set_value(selected).run(timeout=20)
        self.assertFalse(app.exception)
        rendered = "\n".join(item.value for item in app.markdown)
        self.assertIn("Formal financial access", rendered)
        self.assertNotIn("Use of savings services", rendered)


class Phase7PageSmokeTests(unittest.TestCase):
    def test_main_app_and_all_pages_render_without_exceptions(self) -> None:
        paths = [
            "app.py",
            "app_pages/overview.py",
            "app_pages/financial_inclusion.py",
            "app_pages/poverty_insights.py",
            "app_pages/geographic_analysis.py",
            "app_pages/data_quality.py",
            "app_pages/methodology_sources.py",
            "app_pages/dataset_registry.py",
            "app_pages/source_inventory.py",
            "app_pages/codebooks_variables.py",
            "app_pages/indicator_catalogue.py",
            "app_pages/variable_mapping.py",
            "app_pages/statistical_analysis.py",
            "app_pages/research_methodology.py",
            "app_pages/research_readiness.py",
            "app_pages/reports_exports.py",
            "app_pages/evidence_provenance.py",
        ]

        for path in paths:
            with self.subTest(path=path):
                app = AppTest.from_file(PROJECT_ROOT / path).run(timeout=20)
                self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
