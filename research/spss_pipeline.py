"""Second-source pipeline for the supplied SPSS file.

`data/Rwanda FinScope 2020_Final Data.sav` is a distinct survey extract:

* 12,480 rows — the row unit is the *individual respondent* (KEY is the
  household id; households can hold several rows), unlike the FinScope 2024
  master Stata file where rows are households.
* variable names are uppercase and some sections were renamed, so the master
  slice cannot be reconstructed from this file. A documented subset is mapped
  below; everything else stays out of the analytical frame.
* `QF4_*` here means *registered in own name* — a different concept from the
  master file's `QF4_*` (current use). Current use lives in `QF5_*`.
* `EF9` (emergency or rainy day funds, 1=Yes, 2=No) is the emergency-fund
  capability. Three of the four resilience-lens components (own money, saving
  behaviour, social safety net) have NO verified counterpart, so the
  resilience band and the predictive workflow are NOT reproducible on this
  source — the dashboard must report that instead of inventing proxies.
* No standards-unlocking extras were supplied either: no welfare aggregate,
  no poverty line, no strata documentation (`NUMVILL` is a documented PSU,
  which the master lacks, but strata/variance documentation remains absent).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

from research.catalog import SourceProfile
from research.data_pipeline import (
    DISTRICTS,
    PROVINCES,
    SEX,
    URBAN_RURAL,
    SourceLoadError,
    any_yes,
    yes,
)

SPSS_SOURCE_ID = "finscope_2020_spss"


def _code_fingerprint() -> str:
    """Fingerprint of this module's transformation code (runtime-derived)."""

    digest = hashlib.sha256()
    digest.update(Path(__file__).resolve().read_bytes())
    return f"finscope_spss_{digest.hexdigest()[:12]}"


SPSS_ANALYSIS_VERSION = _code_fingerprint()

# Documented subset only. Names are exactly as they appear in the file.
# C14A4 (internet access) and EF7 (income not covering living costs) carry the
# same question semantics as the master's c14_5 and e7 (label-verified:
# C14A4 1=Yes-have-access/2=No; EF7 1=monthly/2=sometimes/3=rarely/4=never).
SPSS_COLUMNS = [
    "ID", "KEY", "HH_WEIGHT", "Individuals_Weight", "TOTAL_IND", "NUMVILL",
    "A1", "A2", "A3", "B0", "B1", "B2", "C14A4", "EF7", "N4A", "N4B",
    *[f"QF5_{i:02d}" for i in range(1, 11)],
    "EF9",
]

# SPSS name -> master-frame name (these SHADOW the master names on purpose).
_RENAME = {
    "KEY": "key",
    "ID": "row_id",
    "HH_WEIGHT": "hh_wt",
    "Individuals_Weight": "pop_wt",
    "TOTAL_IND": "hh_size",
    "NUMVILL": "psu",
    "A1": "a1",       # province code
    "A2": "a2",       # district code
    "A3": "a3",       # urban/rural code (master uses a6; codes match 1/2)
    "B0": "b0",       # relationship to head (1 = household head)
    "B1": "b1",       # age of respondent (same label/semantics as the master's b1)
    "B2": "b2",       # respondent sex (1 male, 2 female)
    "C14A4": "c14_5", # internet access (Yes-have-access/No) — label-verified alias
    "EF7": "e7",      # income-coverage frequency — label-verified alias
    "N4A": "n11",     # monthly personal income band — label-verified income context
    "N4B": "n12",     # annual personal income band — label-verified income context
}

# Verified second-source aliases: the embedded SPSS label names the identical
# concept as the master variable. QF5 is the actual current-use module here
# (QF4 on this file is "registered in own name" — never conflated).
# NOTE: the master's qf4_02 (digital bank) has NO counterpart on this source
# and is never invented; FI-01's channel union therefore drops that channel
# transparently when this source is active.
_ALIASES: dict[str, str] = {
    "qf4_01": "qf5_01",   # commercial bank
    "qf4_03": "qf5_02",   # microfinance (non-umurenge)
    "qf4_04": "qf5_03",   # NDFI
    "qf4_05": "qf5_04",   # mobile money operator
    "qf4_06": "qf5_05",   # Umurenge SACCO
    "e9b": "ef9",         # emergency/rainy-day funds
}


class SpssLoadError(RuntimeError):
    """Raised when the SPSS source cannot be read as the expected FinScope file."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_spss_analysis_data(path: str | Path) -> pd.DataFrame:
    """Read only the documented SPSS subset, renamed to the master schema.

    The original file is never modified. A missing documented column raises
    instead of silently producing empty results.
    """

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"SPSS source does not exist: {source}")

    try:
        frame, _meta = pyreadstat.read_sav(
            source,
            usecols=SPSS_COLUMNS,
        )
    except Exception as exc:  # pyreadstat raises assorted low-level types
        raise SpssLoadError(
            f"Could not read {source} as a compatible SPSS source with the documented fields. "
            f"Original error: {exc}"
        ) from exc

    missing = [name for name in SPSS_COLUMNS if name not in frame.columns]
    if missing:
        raise SpssLoadError(f"SPSS source is missing documented columns: {', '.join(missing)}")

    frame = frame[list(SPSS_COLUMNS)].rename(columns={name: _RENAME.get(name, name.lower()) for name in frame.columns})
    for column in frame.select_dtypes(include=["object", "str"]).columns:
        frame[column] = frame[column].mask(frame[column].eq(""), np.nan)

    # Geography and demographics: identical code frames to the master file.
    frame["key"] = frame["key"].astype(str)
    frame["psu"] = pd.to_numeric(frame["psu"], errors="coerce")
    frame["hh_size"] = pd.to_numeric(frame["hh_size"], errors="coerce")
    frame["province"] = frame["a1"].map(PROVINCES).fillna("Unknown")
    frame["district"] = frame["a2"].map(DISTRICTS).fillna("Unknown")
    frame["setting"] = frame["a3"].map(URBAN_RURAL).fillna("Unknown")
    frame["sex"] = frame["b2"].map(SEX).fillna("Unknown")
    frame["head_sex"] = frame["b0"].eq(1).map({True: "selected respondent is the head"}).fillna("not the head")
    return frame


def enrich_spss_analysis_data(frame: pd.DataFrame) -> pd.DataFrame:
    """Derived analysis variables using the master pipeline's validity rules.

    Only components with a verified counterpart on this source are created.
    The resilience components are deliberately absent — see the module docstring.
    """

    out = frame.copy()
    # Master-schema aliases first, then derived columns computed on those
    # canonical names so no second interpretation of the codes can appear.
    for alias, source_column in _ALIASES.items():
        out[alias] = out[source_column]
    # N4A uses code 14 for irregular/seasonal income, while the master
    # n11 schema uses code 16. The embedded value labels establish the same
    # category; normalize only that code before shared estimators run.
    out["n11"] = out["n11"].replace({14: 16})
    # Five channels — the master's qf4_02 (digital bank) does not exist on
    # this source and is never invented; FI-01 reports the reduced union.
    out["active_access"] = any_yes(out, ["qf4_01", "qf4_03", "qf4_04", "qf4_05", "qf4_06"])
    out["mobile_money"] = yes(out["qf4_05"])
    # Commercial banks only here: the digital-bank channel is absent, so this
    # is a lower bound of the master's bank_use concept.
    out["bank_use"] = yes(out["qf4_01"])
    out["sacco_use"] = yes(out["qf4_06"])
    out["emergency_fund"] = yes(out["e9b"])
    out["internet_access"] = yes(out["c14_5"])
    out["income_pressure"] = out["e7"].isin([1, 2]).astype(float).mask(out["e7"].isna())
    return out


def build_spss_profile(path: str | Path) -> SourceProfile:
    """Inspect source metadata without changing or exporting the source file.

    Returns the same profile structure as the master file so every governance
    gate and Methods view works uniformly. Extra second-source facts (row unit,
    PSU documentation) live in ``notes``.
    """

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"SPSS source does not exist: {source}")
    _frame, meta = pyreadstat.read_sav(source, metadataonly=True)
    return SourceProfile(
        source_id=SPSS_SOURCE_ID,
        path=str(source),
        format="SPSS .sav",
        file_size_mb=round(source.stat().st_size / (1024 * 1024), 2),
        source_sha256=_sha256(source),
        analysis_version=SPSS_ANALYSIS_VERSION,
        rows=int(meta.number_rows or len(_frame)),
        source_variables=len(meta.column_names or []),
        analytical_variables=len(SPSS_COLUMNS),
        mapped_variables=len(SPSS_COLUMNS),
        psu_documented=True,
        source_release="Not documented in supplied materials",
        population_period="Not documented in supplied materials (FinScope 2020 wave indicated by file name only)",
        metadata_status="Inspected: embedded SPSS variable and value labels available",
        analysis_status="Ready for the documented QF5/EF9/income-band subset; resilience lens and predictive modeling not reproducible on this source",
        authorization_status="Unknown: no authorization record supplied",
        publication_status="Not approved: no disclosure/publication approval supplied",
        documentation=("2026 Hackathon Competition.pdf", "Embedded SPSS variable labels and value labels"),
        notes=(
            "Row unit is the individual respondent; households repeat across selected members (12,480 rows at intake).",
            "PSU is documented on this source (NUMVILL); strata, variance method and poverty methodology remain undocumented.",
            "QF4 on this file means 'registered in own name' — the master's QF4 (current use) maps to QF5 here.",
            "Channel set: no digital-bank variable exists on this source; its channel is excluded from FI-01's union, never imputed.",
            "N4A/N4B are label-verified monthly and annual personal-income bands; N4A code 14 is normalized to the master n11 irregular-income code 16.",
            "The dashboard does not expose household-level records by default and does not publish the source file.",
        ),
    )


# Column contract for pages: what this source explicitly does NOT support.
# These components have no label-verified counterpart on this file; pages must
# degrade honestly rather than fabricate them. (internet_access and
# income_pressure and income bands ARE reproducible via C14A4/EF7/N4A/N4B.)
SPSS_WITHHELD = (
    "financial_stress", "owns_money", "saves_regularly", "social_safety_net",
    "phone_ownership", "microinsurance", "has_pension", "emergency_difficult",
    "resilience_score", "resilience_band",
)

# Reproducible derived supports (positive list for UI capability checks).
SPSS_SUPPORTED = (
    "active_access", "mobile_money", "bank_use", "sacco_use", "emergency_fund",
    "internet_access", "income_pressure",
)
