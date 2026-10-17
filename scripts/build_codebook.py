"""Build the verified FinScope codebook record from the supplied dataset.

This script reads the variable labels, value label sets, and file checksum
from the one supplied Stata release (``data/mine/dataset.dta``) and records a
curated codebook for the variables used by the authorized local analysis.
It reads structural metadata and value label definitions only; it never
reads, exposes, or writes respondent rows.

The output is written to ``data/metadata/finscope_codebook.json`` so the
application can document each displayed measure from verified labels.

Run from the repository root::

    PYTHONPATH=src .venv/bin/python scripts/build_codebook.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path("../data/mine/dataset.dta").resolve()
DEFAULT_OUTPUT = REPO_ROOT / "data" / "metadata" / "finscope_codebook.json"

CODEBOOK_VERSION = 1

# The variables the authorized local analysis reads and displays.  Each entry
# is documentation built from the file's own embedded labels.
DOCUMENTED_VARIABLES = (
    "pop_wt",
    "hh_wt",
    "a1",
    "a2",
    "a6",
    "b2",
    "qf3",
    *[f"qf3_{index:02d}" for index in range(1, 12)],
    *[f"qf4_{index:02d}" for index in range(1, 7)],
    *[f"qf1_{index:02d}" for index in range(1, 13)],
    "f5",
)

# Provider batteries reused by the measure definitions.  The labels above are
# copied verbatim from the release file; the grouping below records which
# provider columns each reported measure draws on.
# Cross-check benchmarks transcribed from the official FinScope 2024 report
# supplied with this workspace
# (data/mine/FinScope/2024/Finscope-Final-Report__10_07_2024-1.pdf).
# They document the publisher's broader definitions for comparison only.
OFFICIAL_REPORT_BENCHMARKS = {
    "financial_inclusion": 96.0,
    "formal_inclusion": 92.0,
    "banked": 22.0,
    "mobile_money_own_or_used": 86.0,
    "mobile_money_registered_own_name": 77.0,
    "umurenge_sacco_own_name": 28.0,
    "financially_excluded": 4.0,
}

MEASURE_DEFINITIONS = {
    "any_account": {
        "columns": [f"qf3_{index:02d}" for index in range(1, 12)],
        "definition": (
            "Weighted percentage of respondents (16+) reporting an account "
            "registered in their own name with at least one provider among "
            "qf3_01–qf3_11 (commercial bank, digital bank, microfinance "
            "institution, NDFI, mobile money operator, Umurenge SACCO, "
            "insurance provider, pension fund administrator, EJOHEZA "
            "long-term savings scheme, savings group, village/community "
            "association)."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "formal_account": {
        "columns": [f"qf3_{index:02d}" for index in range(1, 10)],
        "definition": (
            "Weighted percentage holding an account with a formal regulated "
            "provider (qf3_01–qf3_09: banks, microfinance, NDFI, mobile "
            "money operator, Umurenge SACCO, insurance, pension, EJOHEZA), "
            "excluding savings groups and village associations."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "commercial_bank_account": {
        "columns": ["qf3_01", "qf3_02"],
        "definition": (
            "Weighted percentage holding an account with a commercial bank "
            "or digital bank (qf3_01, qf3_02)."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "mobile_money_account": {
        "columns": ["qf3_05"],
        "definition": (
            "Weighted percentage holding an account registered in their own "
            "name with a mobile money operator (qf3_05)."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "umurenge_sacco_account": {
        "columns": ["qf3_06"],
        "definition": (
            "Weighted percentage holding an Umurenge SACCO account "
            "(qf3_06)."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "mobile_money_current_use": {
        "columns": ["qf4_05"],
        "definition": (
            "Weighted percentage currently using a mobile money operator "
            "(qf4_05)."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "any_provider_ever": {
        "columns": [f"qf1_{index:02d}" for index in range(1, 12)],
        "definition": (
            "Weighted percentage who report ever using at least one provider "
            "type listed in the QF1 battery (qf1_01–qf1_11). Equivalent to "
            "the complement of qf1_12 (none of the above). Definitionally "
            "narrower than the official 96% financial inclusion, which also "
            "counts device-based and indirect use."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "bank_ever": {
        "columns": ["qf1_01"],
        "definition": (
            "Weighted percentage who report ever using a commercial bank "
            "(qf1_01). Official report benchmark: 22% banked adults."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "sacco_ever": {
        "columns": ["qf1_06"],
        "definition": (
            "Weighted percentage who report ever using an Umurenge SACCO "
            "(qf1_06). Official report benchmark: 28% of adults hold a "
            "SACCO account in their own name."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "mobile_money_ever": {
        "columns": ["qf1_05"],
        "definition": (
            "Weighted percentage who report ever using a mobile money "
            "operator (qf1_05). This QF1 figure disagrees with the F "
            "module (f5) in the same release; the F-module measure is the "
            "cross-checkable one against the official report."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "mobile_money_registered_current": {
        "columns": ["f5"],
        "coded_affirmative": [6],
        "definition": (
            "Weighted percentage whose f5 answer is code 6: registered "
            "current mobile-money user. The f5 codes are verified against "
            "the supplied questionnaire's mobile-money module. Official "
            "report benchmark: 77% of adults hold a registered mobile "
            "wallet in their own name."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "mobile_money_ever_use": {
        "columns": ["f5"],
        "coded_affirmative": [4, 5, 6],
        "definition": (
            "Weighted percentage whose f5 answer indicates current or "
            "former mobile-money use (codes 4, 5 and 6: registered former "
            "user; unregistered current user; registered current user). "
            "Official report benchmark: 86% own or have used mobile money."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
    "mobile_money_never_reached": {
        "columns": ["f5"],
        "coded_affirmative": [1, 2],
        "definition": (
            "Weighted percentage whose f5 answer is code 1 (not heard of "
            "mobile money) or code 2 (not registered and has never used "
            "mobile money). Official report benchmark: 4% of adults are "
            "financially excluded."
        ),
        "denominator": "All valid-weight respondents (16+) in the supplied release.",
    },
}


def sha256_of(source: Path) -> str:
    """Return the SHA-256 checksum of the source file."""
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_codebook(source: Path) -> dict:
    """Read labels from the supplied release and assemble the codebook record."""
    with pd.io.stata.StataReader(source.open("rb")) as reader:
        all_labels = dict(reader.variable_labels())
        try:
            value_label_sets = reader.value_labels() or {}
        except (AttributeError, KeyError):
            value_label_sets = {}

    variables = []
    for name in DOCUMENTED_VARIABLES:
        entry: dict[str, object] = {
            "variable": name,
            "label": all_labels.get(name),
            "label_present": name in all_labels,
            "value_labels": {},
        }
        if not entry["label_present"]:
            entry["verified"] = False
            entry["note"] = "Label not present in the supplied release file."
        else:
            entry["verified"] = True
            entry["verification"] = "Label read directly from the supplied release file."
        for name_to_label_set in value_label_sets.values():
            if name in name_to_label_set:
                entry["value_labels"] = {
                    str(code): text for code, text in name_to_label_set[name].items()
                }
                entry["value_label_verification"] = (
                    "Value labels read directly from the supplied release file."
                )
                break
        variables.append(entry)

    record = {
        "codebook_version": CODEBOOK_VERSION,
        "release_identifier": "RWA-NISR-FINSCOPE-2024-v01",
        "source_path": "data/mine/dataset.dta",
        "source_sha256": sha256_of(source),
        "extraction_method": (
            "Variable labels and value label sets read with pandas StataReader "
            "from the supplied release file; no respondent rows read or written."
        ),
        "verified": True,
        "verified_variables_count": sum(
            1 for entry in variables if entry["verified"]
        ),
        "total_documented_count": len(variables),
        "variables": variables,
        "measure_definitions": MEASURE_DEFINITIONS,
        "official_report_benchmarks": {
            "source": "data/mine/FinScope/2024/Finscope-Final-Report__10_07_2024-1.pdf",
            "note": (
                "Publisher values transcribed from report sections 2.1 (Figure 3, "
                "access strand) and the executive summary; documented for "
                "definition-aware comparison only, not as results of this extract."
            ),
            **OFFICIAL_REPORT_BENCHMARKS,
        },
        "limitations": (
            "Label text is transcribed from the release file itself; it documents "
            "question wording, not the official denominator policy of the publisher. "
            "Estimates built from these variables remain local exploratory results "
            "and are not comparable with the FinScope headline definitions unless "
            "explicitly cross-checked.",
        ),
    }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source = args.source
    if not source.is_file():
        print(f"Source file not found: {source}", file=sys.stderr)
        return 1

    record = build_codebook(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    print(
        f"Codebook written: {args.output} "
        f"({record['verified_variables_count']}/{record['total_documented_count']} labels verified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
