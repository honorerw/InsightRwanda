from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from insightrwanda.analytics.geography import (
    join_approved_geographic_aggregate,
    save_geographic_analysis_result,
    validate_area_comparison,
    validate_geographic_resource,
)
from insightrwanda.data.errors import IndicatorBlockedError
from insightrwanda.data.geography import load_geographic_resource_registry


def resource_fixture() -> dict[str, object]:
    return {
        "resource_id": "synthetic-district-boundaries",
        "display_name": "Synthetic district boundaries",
        "source_url": "https://example.invalid/official-boundaries",
        "producing_organization": "Synthetic test authority",
        "administrative_level": "district",
        "boundary_release": "boundary-test-v1",
        "reference_date": "2024-01-01",
        "coordinate_reference_system": "EPSG:4326",
        "feature_id_field": "district_code",
        "feature_name_field": "district_name",
        "geometry_types": ["Polygon"],
        "source_path": "geo/synthetic.geojson",
        "source_checksum": "b" * 64,
        "provenance_status": "verified",
        "license_status": "verified",
        "permitted_use_status": "verified",
        "verification_status": "verified",
        "publication_status": "approved",
        "intended_use": "synthetic tests only",
        "limitations": ["Synthetic fixture; not an official Rwanda boundary."],
        "evidence_references": ["synthetic-boundary-review#v1"],
        "disclosure_requirements": {"status": "reviewed"},
    }


def document_fixture(*, duplicate: bool = False, missing_id: bool = False, invalid_geometry: bool = False) -> dict[str, object]:
    def feature(code: str) -> dict[str, object]:
        properties = {"district_code": code, "district_name": f"District {code}"}
        if missing_id:
            properties.pop("district_code")
        geometry: dict[str, object] = {
            "type": "Polygon",
            "coordinates": [[[29.5, -2.0], [29.6, -2.0], [29.6, -1.9], [29.5, -2.0]]],
        }
        if invalid_geometry:
            geometry["coordinates"] = []
        return {"type": "Feature", "properties": properties, "geometry": geometry}

    return {"type": "FeatureCollection", "features": [feature("D01"), feature("D01" if duplicate else "D02")]}


def dataset_fixture(**overrides: object) -> dict[str, object]:
    dataset = {
        "dataset_id": "synthetic-survey",
        "geography_status": "verified",
        "geographic_crosswalk_status": "verified",
        "geographic_variable": "district_code",
        "geographic_join_method": "documented_identifier",
        "geographic_level": "district",
        "boundary_release": "boundary-test-v1",
    }
    dataset.update(overrides)
    return dataset


def calculation_fixture(**overrides: object) -> dict[str, object]:
    calculation = {
        "status": "calculated",
        "calculation_status": "calculated",
        "analysis_eligible": True,
        "publication_eligible": False,
        "readiness": {"analysis_eligible": True},
        "validation": {"input_validation": {"status": "pass"}},
    }
    calculation.update(overrides)
    return calculation


def verified_resource_validation() -> dict[str, object]:
    return {"status": "verified", "resource_id": "synthetic-district-boundaries"}


class Phase16ResourceTests(unittest.TestCase):
    def test_empty_registry_and_missing_resource_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "geographic_resources.json"
            path.write_text(json.dumps({"registry_version": 1, "resources": []}), encoding="utf-8")
            self.assertEqual(load_geographic_resource_registry(path), [])
            result = validate_geographic_resource(None, project_root=directory)
        self.assertEqual(result.status, "blocked")
        self.assertIn("resource_registered", {item["check_id"] for item in result.as_dict()["checks"]})

    def test_missing_provenance_license_and_local_file_do_not_verify_resource(self):
        resource = resource_fixture()
        resource.update({"source_path": "geo/missing.geojson", "provenance_status": "unverified", "license_status": "unverified"})
        result = validate_geographic_resource(resource, project_root=tempfile.mkdtemp())
        statuses = {item["check_id"]: item["status"] for item in result.as_dict()["checks"]}
        self.assertEqual(result.status, "blocked")
        self.assertEqual(statuses["boundary_resource_presence"], "blocked")
        self.assertEqual(statuses["boundary_provenance"], "blocked")
        self.assertEqual(statuses["boundary_license_terms"], "blocked")

    def test_invalid_geometry_identifiers_and_crs_fail_safely(self):
        resource = resource_fixture()
        resource["coordinate_reference_system"] = "not-a-crs"
        with tempfile.TemporaryDirectory() as directory:
            result = validate_geographic_resource(
                resource,
                project_root=directory,
                document=document_fixture(invalid_geometry=True, missing_id=True),
                allow_in_memory=True,
            )
        statuses = {item["check_id"]: item["status"] for item in result.as_dict()["checks"]}
        self.assertEqual(result.status, "blocked")
        self.assertEqual(statuses["boundary_metadata"], "blocked")
        self.assertEqual(statuses["feature_identifiers"], "fail")
        self.assertEqual(statuses["geometry_validity"], "fail")
        self.assertNotIn('"coordinates":', json.dumps(result.as_dict()))

    def test_duplicate_feature_identifiers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = validate_geographic_resource(
                resource_fixture(),
                project_root=directory,
                document=document_fixture(duplicate=True),
                allow_in_memory=True,
            )
        checks = {item["check_id"]: item for item in result.as_dict()["checks"]}
        self.assertEqual(checks["feature_identifiers"]["status"], "fail")
        self.assertEqual(result.as_dict()["diagnostics"]["duplicate_feature_identifier_count"], 1)


class Phase16JoinTests(unittest.TestCase):
    def _join(self, aggregate=None, boundaries=None, **kwargs):
        aggregate = aggregate if aggregate is not None else pd.DataFrame({"district_code": ["D01", "D02"], "estimate": [0.2, 0.4]})
        boundaries = boundaries if boundaries is not None else pd.DataFrame({"district_code": ["D01", "D02"], "district_name": ["A", "B"]})
        return join_approved_geographic_aggregate(
            aggregate,
            boundaries,
            dataset=kwargs.pop("dataset", dataset_fixture()),
            aggregate_key="district_code",
            boundary_key="district_code",
            geographic_level=kwargs.pop("geographic_level", "district"),
            calculation_metadata=kwargs.pop("calculation_metadata", calculation_fixture()),
            resource_metadata=kwargs.pop("resource_metadata", resource_fixture()),
            resource_validation=kwargs.pop("resource_validation", verified_resource_validation()),
            **kwargs,
        )

    def test_valid_join_returns_only_aggregate_diagnostics(self):
        result = self._join()
        self.assertEqual(result.status, "validated")
        diagnostics = result.as_dict()["diagnostics"]
        self.assertEqual(diagnostics["matched_identifier_count"], 2)
        self.assertEqual(diagnostics["final_joined_row_count"], 2)
        self.assertNotIn("joined", result.as_dict())
        self.assertNotIn("D01", json.dumps(result.as_dict()))

    def test_unmatched_duplicate_multiplicity_and_type_mismatch_are_blocked(self):
        unmatched = self._join(aggregate=pd.DataFrame({"district_code": ["D99"], "estimate": [0.2]}))
        self.assertEqual(unmatched.status, "blocked")
        self.assertEqual(unmatched.unmatched_aggregate_count, 1)
        duplicate = self._join(aggregate=pd.DataFrame({"district_code": ["D01", "D01"], "estimate": [0.2, 0.3]}))
        self.assertEqual(duplicate.status, "blocked")
        self.assertTrue(duplicate.as_dict()["diagnostics"]["unexpected_join_multiplicity"])
        mismatched = self._join(boundaries=pd.DataFrame({"district_code": [1, 2]}))
        self.assertEqual(mismatched.status, "blocked")

    def test_level_release_eligibility_and_publication_gates_are_separate(self):
        self.assertEqual(self._join(dataset=dataset_fixture(geographic_level="province")).status, "blocked")
        self.assertEqual(self._join(resource_metadata=resource_fixture() | {"boundary_release": "other-release"}).status, "blocked")
        self.assertEqual(self._join(calculation_metadata=calculation_fixture(analysis_eligible=False)).status, "blocked")
        self.assertEqual(self._join(resource_validation={"status": "blocked"}).status, "blocked")
        self.assertEqual(self._join(publication_requested=True).status, "blocked")

    def test_area_method_blocks_unsupported_design_and_missing_disclosure(self):
        join = self._join()
        blocked = validate_area_comparison(
            readiness={"analysis_eligible": True},
            join_result=join,
            survey_design={"status": "unverified"},
            disclosure_requirements=None,
            uncertainty_requested=True,
            ranking_requested=True,
        )
        self.assertEqual(blocked.status, "blocked")
        ids = {item["check_id"] for item in blocked.as_dict()["checks"] if item["status"] == "blocked"}
        self.assertIn("survey_domain_method", ids)
        self.assertIn("variance_method_support", ids)
        self.assertIn("disclosure_requirements", ids)
        self.assertIn("multiple_comparison_method", ids)

    def test_analytical_false_leaves_area_checks_not_run(self):
        report = validate_area_comparison(
            readiness={"analysis_eligible": False},
            join_result=None,
            survey_design=None,
            disclosure_requirements=None,
        )
        self.assertEqual(report.status, "blocked")
        statuses = {item["check_id"]: item["status"] for item in report.as_dict()["checks"]}
        self.assertEqual(statuses["central_analytical_eligibility"], "blocked")
        self.assertEqual(statuses["area_comparison_inputs"], "not_run")

    def test_supported_synthetic_diagnostics_can_be_saved_without_raw_records(self):
        join = self._join()
        design = {
            "status": "approved",
            "point_estimate_supported": True,
            "domain_estimation_supported": True,
            "weights_documented": True,
            "strata_documented": True,
            "clusters_documented": True,
            "sampling_design": "Synthetic documented complex survey",
            "domain_estimation_method": "approved_domain_estimation",
            "variance_estimation_supported": True,
            "variance_method": "linearization",
            "small_area_reliability_status": "reviewed",
        }
        area = validate_area_comparison(
            readiness={"analysis_eligible": True},
            join_result=join,
            survey_design=design,
            disclosure_requirements={
                "status": "reviewed",
                "small_area_rule": "Statistician review required",
                "sensitive_combination_review": "Completed",
                "geographic_detail_review": "District level approved for analysis",
                "export_review": "Not approved for public export",
            },
        )
        self.assertEqual(area.status, "pass")
        artifact = {
            "status": "validated",
            "analysis_eligible": True,
            "data_classification": "synthetic_test_data",
            "join_validation": join.as_dict(),
            "area_validation": area.as_dict(),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = save_geographic_analysis_result(artifact, project_root=directory)
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(saved["result_artifact_written"])
        self.assertNotIn("joined", saved)
        self.assertNotIn("geometry", json.dumps(saved))

    def test_blocked_geographic_result_cannot_be_saved(self):
        blocked = {
            "status": "blocked",
            "analysis_eligible": False,
            "join_validation": {"status": "blocked"},
            "area_validation": {"status": "blocked"},
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(IndicatorBlockedError):
                save_geographic_analysis_result(blocked, project_root=directory)
            self.assertFalse((Path(directory) / "artifacts" / "phase16_geographic_result.json").exists())


if __name__ == "__main__":
    unittest.main()
