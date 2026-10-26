"""Combined analysis of the two supplied FinScope sources.

What "combine" can and cannot mean here
---------------------------------------
`data/FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta` (13,994 rows,
household level, 4-5 digit integer `key`) and
`data/Rwanda FinScope 2020_Final Data.sav` (12,480 rows, respondent level,
14-15 digit string `KEY`) share **no record identifier** — the intersection of
their keys is empty. A household-level merge is therefore impossible and is
not attempted anywhere in this module. `linkage_audit` measures that fact so a
reader can check it rather than take it on trust.

The two files answer the same FinScope question set. The variables
used here were matched on their embedded labels (bank / MFI / NDFI / mobile
money / SACCO current use, emergency/rainy-day funds, internet access, income
coverage, province, district, urban/rural, age, sex, household size). Combining
them therefore means **pooling two independent samples of the same survey
programme** on the harmonized variables, with the source kept as an explicit
dimension and weights rescaled so one file cannot dominate by sheer size.

Wave / year handling
--------------------
The SPSS file is the FinScope 2020 wave (its release name, the NISR FinScope
2020 release and the file's 2020 creation timestamp agree; official fieldwork
ran September-November 2019). The Stata file is supplied as the FinScope 2024
wave by its release name (`FinScope 2024, Financial Inclusion in Rwanda`),
which is the documented year used throughout. `WAVE_YEARS` is the single
place to revise a documented year; the `wave_year` column and every view
built on it will then update on their own.

Prediction
----------
`evaluate_transport` trains the same non-leaking model (logistic regression on
demographics, household size, internet access, income pressure and emergency
funds) five ways: within each source, across sources in both directions, and a
pooled model tested on each source. Every target-defining indicator is
excluded from the features, so a "prediction" only uses information a
practitioner would actually have before the outcome is observed.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


# Documented wave years, from the supplied release names. `None` would mean an
# undocumented file; both waves are documented here. Revise only with a source.
WAVE_YEARS: dict[str, int | None] = {
    "master": 2024,   # FinScope 2024 wave (supplied release name)
    "spss": 2020,     # FinScope 2020 release; fieldwork Sept-Nov 2019
}

SOURCE_LABELS: dict[str, str] = {
    "master": "FinScope 2024 (master Stata)",
    "spss": "FinScope 2020 (SPSS)",
}

MEASURES: dict[str, str] = {
    "active_access": "Active formal financial access",
    "mobile_money": "Current mobile-money use",
    "bank_use": "Bank current use",
    "sacco_use": "Umurenge SACCO current use",
    "emergency_fund": "Emergency fund coverage",
    "internet_access": "Internet access",
    "income_pressure": "Income pressure",
}

# Columns every source must carry before a joint frame can be built. Names are
# the harmonized ones produced by the two pipelines, not the file-native names.
REQUIRED_SHARED = (
    "key", "hh_wt", "hh_size", "b1", "b2", "province", "district", "setting", "sex",
    *MEASURES,
)

# Targets the combined model can predict: both exist, with the same semantics,
# on both supplied sources.
TARGETS: dict[str, str] = {
    "active_access": "Active formal financial access",
    "mobile_money": "Current mobile-money use",
}

CATEGORICAL_FEATURES = ["sex", "setting", "province"]
NUMERIC_FEATURES = ["age", "hh_size", "internet_access", "income_pressure", "emergency_fund"]
FEATURES = [*CATEGORICAL_FEATURES, *NUMERIC_FEATURES]

# Indicators that DEFINE a target. They may never be predictors of it.
TARGET_COMPONENTS: dict[str, frozenset[str]] = {
    "active_access": frozenset({"active_access", "bank_use", "sacco_use", "mobile_money"}),
    "mobile_money": frozenset({"mobile_money", "active_access", "bank_use", "sacco_use"}),
}

COMBINED_COLUMNS: tuple[str, ...] = (
    "record_id", "source", "wave_year", "wave_label",
    "province", "district", "setting", "sex",
    "age", "age_band", "hh_size", "weight", "weight_share",
    *MEASURES,
)

COMBINED_COLUMN_NOTES: dict[str, str] = {
    "record_id": "Deterministic hash of source + source key; the original survey key is not carried into the combined file.",
    "source": "master (FinScope 2024, Financial Inclusion in Rwanda - Rwanda.dta) or spss (Rwanda FinScope 2020_Final Data.sav).",
    "wave_year": "2024 for the master file; 2020 for the SPSS file (fieldwork Sept-Nov 2019).",
    "wave_label": "Human-readable source/wave label used in the dashboard.",
    "province": "Harmonized province name from the source's A1/A2 codes.",
    "district": "Harmonized district name.",
    "setting": "Urban or Rural.",
    "sex": "Respondent sex, Male or Female.",
    "age": "Respondent age in completed years (master b1 / SPSS B1).",
    "age_band": "16-24, 25-34, 35-44, 45-54, 55-64, 65+, or Unknown.",
    "hh_size": "Household size as supplied.",
    "weight": "The source's own household weight (hh_wt).",
    "weight_share": "Weight rescaled to sum to 1 within each source, for equal-source pooled estimates.",
    **{measure: label for measure, label in MEASURES.items()},
}

RANDOM_STATE = 42
N_SPLITS = 5


class JointFrameError(ValueError):
    """Raised when a source cannot support the combined analytical frame."""


# -----------------------------------------------------------------------------
# Linkage audit
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class LinkageAudit:
    master_rows: int
    master_unique_keys: int
    spss_rows: int
    spss_unique_keys: int
    shared_keys: int
    composite_pairs: int
    composite_spss_rows: int
    composite_agreement_share: float
    verdict: str = field(default="")

    @property
    def linkable(self) -> bool:
        return self.shared_keys > 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalized_keys(values: Iterable[object]) -> pd.Series:
    keys = pd.Series(values, dtype="object").astype(str).str.strip()
    keys = keys.str.replace(r"\.0$", "", regex=True)
    return keys.str.lstrip("0")


def linkage_audit(master: pd.DataFrame, spss: pd.DataFrame) -> LinkageAudit:
    """Measure whether the two supplied files can be record-linked.

    The composite-key block answers the obvious follow-up question ("maybe the
    IDs were regenerated?") by counting pairs that match on province, district,
    age and sex and then reporting how often those pairs also agree on every
    jointly observed indicator. A true re-keyed sample would agree nearly
    always; coincidental pairs agree far less often.
    """

    for frame, name in ((master, "master"), (spss, "spss")):
        if "key" not in frame.columns:
            raise JointFrameError(f"The {name} frame has no key column to audit")

    master_keys = _normalized_keys(master["key"])
    spss_keys = _normalized_keys(spss["key"])
    shared = len(set(master_keys) & set(spss_keys))

    composite_pairs = 0
    composite_spss_rows = 0
    agreement_share = float("nan")
    required = {"province", "district", "b1", "b2", "key", *MEASURES}
    if required.issubset(master.columns) and required.issubset(spss.columns):
        left = spss[list(required)].copy()
        right = master[list(required)].copy()
        pairs = left.merge(
            right,
            on=["province", "district", "b1", "b2"],
            suffixes=("_spss", "_master"),
        )
        composite_pairs = int(len(pairs))
        if composite_pairs:
            composite_spss_rows = int(pairs["key_spss"].nunique())
            agree = pd.Series(True, index=pairs.index)
            observed = pd.Series(False, index=pairs.index)
            for measure in MEASURES:
                a = pairs[f"{measure}_spss"]
                b = pairs[f"{measure}_master"]
                both = a.notna() & b.notna()
                agree &= (~both) | a.eq(b)
                observed |= both
            if observed.any():
                agreement_share = float(agree[observed].mean())

    if shared:
        verdict = (
            f"{shared:,} shared record key(s) found — record-level linkage is possible and should be "
            "reviewed before any pooled claim."
        )
    else:
        verdict = (
            "No shared record key: the two files cannot be joined at household or respondent level. "
            "They are analysed as two independent samples of the same survey programme, and the "
            "source stays an explicit dimension in every combined result."
        )

    return LinkageAudit(
        master_rows=int(len(master)),
        master_unique_keys=int(master_keys.nunique()),
        spss_rows=int(len(spss)),
        spss_unique_keys=int(spss_keys.nunique()),
        shared_keys=int(shared),
        composite_pairs=composite_pairs,
        composite_spss_rows=composite_spss_rows,
        composite_agreement_share=agreement_share,
        verdict=verdict,
    )


# -----------------------------------------------------------------------------
# Joint frame
# -----------------------------------------------------------------------------
def build_joint_frame(
    master: pd.DataFrame,
    spss: pd.DataFrame,
    wave_years: dict[str, int | None] | None = None,
) -> pd.DataFrame:
    """Stack both sources on the harmonized variables, with source and wave kept.

    Weights are carried twice:

    * ``weight`` — the source's own household weight, for within-source estimates;
    * ``weight_share`` — the weight rescaled to sum to 1 within each source, so a
      pooled estimate gives each supplied file equal influence instead of letting
      the larger file dominate.
    """

    wave_years = {**WAVE_YEARS, **(wave_years or {})}
    parts: list[pd.DataFrame] = []
    for source, frame in (("master", master), ("spss", spss)):
        missing = [column for column in REQUIRED_SHARED if column not in frame.columns]
        if missing:
            raise JointFrameError(
                f"The {source} source cannot join the combined frame; missing columns: {', '.join(missing)}"
            )
        part = frame[list(REQUIRED_SHARED)].copy()
        part["source"] = source
        part["wave_year"] = pd.array([wave_years.get(source)] * len(part), dtype="Int64")
        part["wave_label"] = SOURCE_LABELS[source]
        part["weight"] = pd.to_numeric(part["hh_wt"], errors="coerce")
        part["age"] = pd.to_numeric(part["b1"], errors="coerce")
        for column in MEASURES:
            part[column] = pd.to_numeric(part[column], errors="coerce")

        usable = part["weight"].notna() & part["weight"].gt(0) & np.isfinite(part["weight"])
        total = float(part.loc[usable, "weight"].sum())
        part["weight_share"] = part["weight"] / total if total > 0 else np.nan
        parts.append(part)

    joint = pd.concat(parts, ignore_index=True)
    joint["age_band"] = pd.cut(
        joint["age"],
        bins=[15, 25, 35, 45, 55, 65, np.inf],
        labels=["16-24", "25-34", "35-44", "45-54", "55-64", "65+"],
        right=False,
    ).astype(object)
    joint["age_band"] = joint["age_band"].where(joint["age_band"].notna(), "Unknown")
    return joint


def build_combined_dataset(
    master: pd.DataFrame,
    spss: pd.DataFrame,
    wave_years: dict[str, int | None] | None = None,
) -> pd.DataFrame:
    """One stacked, harmonized dataset ready to save as a single file.

    This is the pooled frame with its analysis columns only. The original
    survey keys are replaced by a deterministic ``record_id`` (SHA-256 of
    source and key, truncated), so the file can be analysed without carrying
    supplied identifiers. Duplicate keys inside a source would still receive
    distinct ids.
    """

    joint = build_joint_frame(master, spss, wave_years=wave_years)
    parts = joint.copy()
    duplicate_rank = parts.groupby(["source", "key"], sort=False).cumcount()
    parts["record_id"] = [
        hashlib.sha256(f"{source}:{key}:{rank}".encode("utf-8")).hexdigest()[:16]
        for source, key, rank in zip(parts["source"], parts["key"], duplicate_rank)
    ]
    if parts["record_id"].duplicated().any():
        raise JointFrameError("Combined record ids are not unique; refuse to write a dataset with collisions")
    return parts[list(COMBINED_COLUMNS)].reset_index(drop=True)


def weighted_rate(frame: pd.DataFrame, measure: str, weight: str = "weight") -> float:
    """Weighted share of a 0/1 measure over records with a usable weight."""

    if measure not in frame.columns or weight not in frame.columns:
        raise JointFrameError(f"Missing columns for a weighted rate: {measure}, {weight}")
    values = pd.to_numeric(frame[measure], errors="coerce")
    weights = pd.to_numeric(frame[weight], errors="coerce")
    valid = values.notna() & weights.notna() & weights.gt(0) & np.isfinite(weights)
    if not valid.any():
        return float("nan")
    return float(np.average(values.loc[valid], weights=weights.loc[valid]))


def pooled_estimates(frame: pd.DataFrame) -> pd.DataFrame:
    """Each shared measure by source, the gap, and an equal-source pooled figure."""

    rows = []
    for measure, label in MEASURES.items():
        row: dict[str, object] = {"Measure": label}
        for source, column in (("master", SOURCE_LABELS["master"]), ("spss", SOURCE_LABELS["spss"])):
            subset = frame.loc[frame["source"].eq(source)]
            row[column] = weighted_rate(subset, measure)
            row[f"{source} n"] = int(
                (subset[measure].notna() & subset["weight"].gt(0)).sum()
            )
        gap = row[SOURCE_LABELS["spss"]] - row[SOURCE_LABELS["master"]]
        row["Gap (pp)"] = gap * 100 if pd.notna(gap) else float("nan")
        row["Pooled (equal source weight)"] = weighted_rate(frame, measure, weight="weight_share")
        rows.append(row)
    return pd.DataFrame(rows)


def weighted_correlation(
    frame: pd.DataFrame,
    columns: Iterable[str] | None = None,
    weight: str = "weight_share",
) -> pd.DataFrame:
    """Pairwise-complete weighted Pearson correlations.

    Each pair uses only records where both values and the weight are usable, so
    a missing answer never silently becomes a zero.
    """

    columns = list(columns or MEASURES)
    missing = [column for column in [*columns, weight] if column not in frame.columns]
    if missing:
        raise JointFrameError(f"Cannot correlate; missing columns: {', '.join(missing)}")

    matrix = pd.DataFrame(np.eye(len(columns)), index=columns, columns=columns, dtype=float)
    for index, left in enumerate(columns):
        for right in columns[index + 1:]:
            subset = frame[[left, right, weight]].apply(pd.to_numeric, errors="coerce")
            valid = subset.notna().all(axis=1) & subset[weight].gt(0) & np.isfinite(subset[weight])
            if int(valid.sum()) < 3:
                value = float("nan")
            else:
                w = subset.loc[valid, weight].to_numpy(dtype=float)
                x = subset.loc[valid, left].to_numpy(dtype=float)
                y = subset.loc[valid, right].to_numpy(dtype=float)
                mean_x = float(np.average(x, weights=w))
                mean_y = float(np.average(y, weights=w))
                var_x = float(np.average((x - mean_x) ** 2, weights=w))
                var_y = float(np.average((y - mean_y) ** 2, weights=w))
                covariance = float(np.average((x - mean_x) * (y - mean_y), weights=w))
                value = covariance / np.sqrt(var_x * var_y) if var_x > 0 and var_y > 0 else float("nan")
            matrix.loc[left, right] = value
            matrix.loc[right, left] = value
    return matrix


def weighted_cross_tab(
    frame: pd.DataFrame,
    row: str,
    column: str,
    weight: str = "weight_share",
) -> pd.DataFrame:
    """Row-percentage cross-tab (cells sum to ~100 across each row)."""

    for name in (row, column, weight):
        if name not in frame.columns:
            raise JointFrameError(f"Cannot cross-tabulate; missing column: {name}")
    usable = frame[[row, column, weight]].notna().all(axis=1) & frame[weight].gt(0)
    subset = frame.loc[usable]
    if subset.empty:
        return pd.DataFrame()
    table = subset.pivot_table(index=row, columns=column, values=weight, aggfunc="sum", fill_value=0.0)
    totals = table.sum(axis=1).replace(0, np.nan)
    return (table.div(totals, axis=0) * 100).round(1)


# -----------------------------------------------------------------------------
# Prediction: one model, five ways to test it
# -----------------------------------------------------------------------------
def _pipeline(seed: int) -> Pipeline:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return Pipeline([
        ("prep", ColumnTransformer([
            ("numeric", numeric, NUMERIC_FEATURES),
            ("categorical", categorical, CATEGORICAL_FEATURES),
        ])),
        # No class re-weighting: probabilities stay near the observed base rate, so
        # Brier and the predicted/observed columns mean what they say.
        ("classifier", LogisticRegression(max_iter=2000, random_state=seed)),
    ])


def _model_frame(
    frame: pd.DataFrame, target: str
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.Series]:
    """X, y, source weight, equal-source weight and source for a target."""

    if target not in TARGETS:
        raise KeyError(f"Unknown combined target: {target}")
    leaked = set(FEATURES) & TARGET_COMPONENTS[target]
    if leaked:
        raise ValueError(
            f"Leakage guard tripped: {', '.join(sorted(leaked))} define {target} and cannot be features"
        )
    missing = [column for column in [*FEATURES, target, "weight", "weight_share", "source"] if column not in frame.columns]
    if missing:
        raise JointFrameError(f"Cannot build the model frame; missing columns: {', '.join(missing)}")

    X = frame[list(FEATURES)].copy()
    for column in NUMERIC_FEATURES:
        X[column] = pd.to_numeric(X[column], errors="coerce")
    for column in CATEGORICAL_FEATURES:
        X[column] = X[column].astype("object").where(X[column].notna(), "Unknown")
    y = pd.to_numeric(frame[target], errors="coerce")
    weight = pd.to_numeric(frame["weight"], errors="coerce")
    usable = y.notna() & y.isin([0, 1]) & weight.notna() & weight.gt(0) & np.isfinite(weight)
    if not usable.any():
        raise JointFrameError(f"No usable records for target {target}")
    share = pd.to_numeric(frame["weight_share"], errors="coerce")
    return (
        X.loc[usable],
        y.loc[usable].astype(int),
        weight.loc[usable],
        share.loc[usable],
        frame.loc[usable, "source"],
    )


def _fit(X: pd.DataFrame, y: pd.Series, weight: pd.Series, seed: int) -> Pipeline:
    model = _pipeline(seed)
    model.fit(X, y, classifier__sample_weight=weight.to_numpy(dtype=float))
    return model


def _score_row(
    train_on: str,
    test_on: str,
    y_true: pd.Series,
    probability: np.ndarray,
    weight: pd.Series,
    note: str,
) -> dict[str, object]:
    weights = weight.to_numpy(dtype=float)
    both_classes = y_true.nunique() == 2
    observed = float(np.average(y_true, weights=weights))
    return {
        "Train on": train_on,
        "Test on": test_on,
        "Test records": int(len(y_true)),
        "Observed positive share": observed,
        "Mean predicted": float(np.average(probability, weights=weights)),
        "ROC-AUC": float(roc_auc_score(y_true, probability, sample_weight=weights)) if both_classes else float("nan"),
        "Brier": float(brier_score_loss(y_true, probability, sample_weight=weights)),
        # A constant predictor at the observed rate would score this Brier; lower is better.
        "Base-rate Brier": observed * (1 - observed),
        "Note": note,
    }


def _within_source_cv(
    X: pd.DataFrame,
    y: pd.Series,
    weight: pd.Series,
    seed: int,
    n_splits: int = N_SPLITS,
) -> tuple[np.ndarray, pd.Series, pd.Series]:
    """Out-of-fold probabilities for every record in one source."""

    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    probability = np.full(len(y), np.nan)
    for train_idx, test_idx in splitter.split(X, y):
        model = _fit(X.iloc[train_idx], y.iloc[train_idx], weight.iloc[train_idx], seed)
        probability[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
    return probability, y, weight


def evaluate_transport(
    frame: pd.DataFrame,
    target: str,
    seed: int = RANDOM_STATE,
    n_splits: int = N_SPLITS,
) -> pd.DataFrame:
    """Score the same non-leaking model within and across both sources.

    Rows: within-master CV, within-SPSS CV, master→SPSS, SPSS→master, and a
    pooled model tested separately on each source. AUC answers "does the
    ranking transport?"; Brier, its base-rate reference and the
    predicted/observed columns answer "does the probability level transport?".

    Both targets are highly prevalent in the asked population (about 90-96%),
    so accuracy or F1 at a fixed threshold would just restate the base rate;
    they are deliberately not reported as headline metrics.
    """

    X, y, weight, share, source = _model_frame(frame, target)
    rows: list[dict[str, object]] = []

    for label in ("master", "spss"):
        mask = source.eq(label)
        probability, y_true, test_weight = _within_source_cv(
            X.loc[mask], y.loc[mask], weight.loc[mask], seed, n_splits
        )
        rows.append(_score_row(
            f"{SOURCE_LABELS[label]} · {n_splits}-fold CV",
            SOURCE_LABELS[label],
            y_true, probability, test_weight,
            "out-of-fold predictions",
        ))

    for train_label, test_label in (("master", "spss"), ("spss", "master")):
        train_mask = source.eq(train_label)
        test_mask = source.eq(test_label)
        model = _fit(X.loc[train_mask], y.loc[train_mask], weight.loc[train_mask], seed)
        probability = model.predict_proba(X.loc[test_mask])[:, 1]
        rows.append(_score_row(
            SOURCE_LABELS[train_label], SOURCE_LABELS[test_label],
            y.loc[test_mask], probability, weight.loc[test_mask],
            "external test",
        ))

    for test_label in ("master", "spss"):
        model = _fit(X, y, share, seed)
        test_mask = source.eq(test_label)
        probability = model.predict_proba(X.loc[test_mask])[:, 1]
        rows.append(_score_row(
            "Both sources pooled", SOURCE_LABELS[test_label],
            y.loc[test_mask], probability, weight.loc[test_mask],
            "pooled fit, equal source weight",
        ))

    table = pd.DataFrame(rows)
    for column in ("ROC-AUC", "Brier", "Base-rate Brier"):
        table[column] = table[column].round(3)
    for column in ("Observed positive share", "Mean predicted"):
        table[column] = (table[column] * 100).round(1)
    return table


def wave_note() -> str:
    """One-sentence statement of what the supplied files do and do not date."""

    return (
        "The master Stata file is supplied as the FinScope 2024 wave (release name). The SPSS file is the "
        "FinScope 2020 wave: its release and file timestamp date it to 2020, and official documentation places "
        "the fieldwork in September-November 2019. Neither file carries an interview-date field, so year-on-year "
        "statements describe the two documented waves (2020 vs 2024) rather than measured months."
    )


def comparison_note() -> str:
    """What a pooled comparison of these two files may and may not claim."""

    return (
        "The two files answer the same FinScope question set, but they are different samples with "
        "different row units (household vs respondent) and different weights. A gap between them is "
        "a source-definition finding, not a measured change over time and not a causal effect."
    )
