"""Real predictive-analytics workflow for InsightRwanda.

Task: predict whether a household's derived resilience band is *Priority*
(versus Watch/Resilient) from features that do NOT define that band. Rows
labelled Unknown are excluded. This is a predictive association, not a causal
claim and not an official poverty measure.

Leakage policy
--------------
* The capability columns that DEFINE the target (emergency_fund, owns_money,
  saves_regularly, social_safety_net) plus the resilience_score itself are
  dropped from the feature set; a guard raises if one is re-introduced.
* Splitting is grouped by the respondent key (`key`) with stratification on
  the target, so a household never appears on both sides of a boundary.
* Survey weights (`hh_wt`) are passed to fitting and to every metric where
  scikit-learn supports sample_weight.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

TARGET_COLUMN = "resilience_band"
TARGET_LABEL = "Priority resilience band (vs Watch/Resilient)"

CATEGORICAL_FEATURES = ["province", "setting", "sex", "head_sex"]
NUMERIC_FEATURES = [
    "hh_size",   # household size
    "b2",        # respondent sex code
    "a6",        # urban/rural code
    "c14_5",     # internet access code
    "f3",        # phone ownership code
    "qf4_05",    # mobile money current-use code
    "e2d",       # shock outcome code
    "e2e",       # shock outcome code
    "e6",        # financial stress frequency code
    "e7",        # income coverage code
    "e9c",       # difficulty of raising emergency money
]
BLOCKED_FROM_FEATURES = (
    "resilience_band",     # the target itself
    "resilience_score",    # defines the target
    "emergency_fund",      # defines the target
    "owns_money",          # defines the target
    "saves_regularly",     # defines the target
    "social_safety_net",   # defines the target
)

RANDOM_STATE = 42
N_SPLITS = 5
THRESHOLD = 0.5
NA_FLAG = "n/a"

BASELINE_NAME = "Baseline (majority class)"
CANDIDATE_NAMES = (
    BASELINE_NAME,
    "Logistic regression",
    "Decision tree",
    "Hist gradient boosting",
)


def _onehot_preprocessor() -> ColumnTransformer:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("numeric", numeric, NUMERIC_FEATURES),
        ("categorical", categorical, CATEGORICAL_FEATURES),
    ])


def _tree_preprocessor() -> ColumnTransformer:
    """Trees and boosting take unstandardized codes; categorical strings become ordinals."""

    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("ordinal", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])
    return ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median"), NUMERIC_FEATURES),
        ("categorical", categorical, CATEGORICAL_FEATURES),
    ])


def make_candidate(name: str, seed: int = RANDOM_STATE):
    """Return (estimator, weight_param_key). weight key None = estimator ignores weights."""

    if name == BASELINE_NAME:
        return DummyClassifier(strategy="prior"), None
    if name == "Logistic regression":
        estimator = Pipeline([
            ("prep", _onehot_preprocessor()),
            ("classifier", LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced", random_state=seed)),
        ])
        return estimator, "classifier__sample_weight"
    if name == "Decision tree":
        estimator = Pipeline([
            ("prep", _tree_preprocessor()),
            ("classifier", DecisionTreeClassifier(
                max_depth=5, min_samples_leaf=60, class_weight="balanced", random_state=seed)),
        ])
        return estimator, "classifier__sample_weight"
    if name == "Hist gradient boosting":
        estimator = Pipeline([
            ("prep", _tree_preprocessor()),
            ("classifier", HistGradientBoostingClassifier(
                max_iter=200, max_depth=3, learning_rate=.08, l2_regularization=1.0,
                class_weight="balanced", random_state=seed)),
        ])
        return estimator, "classifier__sample_weight"
    raise ValueError(f"Unknown candidate: {name}")


def fit_candidate(name: str, X: pd.DataFrame, y: pd.Series, sample_weight: np.ndarray | None, seed: int = RANDOM_STATE):
    model, weight_key = make_candidate(name, seed=seed)
    if sample_weight is None or weight_key is None:
        model.fit(X, y)
    else:
        model.fit(X, y, **{weight_key: sample_weight})
    return model


@dataclass(frozen=True)
class CandidateResult:
    name: str
    fold_auc: tuple[float, ...]
    fold_f1: tuple[float, ...]
    mean_auc: float
    sd_auc: float
    mean_f1: float
    sd_f1: float
    fit_seconds: float


def build_model_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Assemble X, y, groups and survey weights with the leakage policy enforced.

    Raises loudly if a target-defining column is used as a feature, or if the
    prepared frame is missing required columns, so silent leakage is impossible.
    """

    if TARGET_COLUMN not in frame:
        raise ValueError(f"Target column missing: {TARGET_COLUMN}")
    for blocked in BLOCKED_FROM_FEATURES:
        if blocked in CATEGORICAL_FEATURES or blocked in NUMERIC_FEATURES:
            raise ValueError(f"Leakage guard tripped: {blocked} must not be a feature")

    features = [*CATEGORICAL_FEATURES, *NUMERIC_FEATURES]
    missing = [c for c in [*features, "key", "hh_wt"] if c not in frame.columns]
    if missing:
        raise ValueError(f"Required columns missing from prepared frame: {', '.join(missing)}")

    usable = frame.loc[~frame[TARGET_COLUMN].isin(["Unknown"])].copy()
    y = usable[TARGET_COLUMN].isin(["Priority"]).astype(int)
    groups = usable["key"].astype(str)
    weights = pd.to_numeric(usable["hh_wt"], errors="coerce")
    valid = weights.notna() & weights.gt(0) & np.isfinite(weights)
    # Only rows with a defined band (Priority/Watch/Resilient) participate.
    valid = valid & usable[TARGET_COLUMN].isin(["Priority", "Watch", "Resilient"])

    X = usable.loc[valid, features].copy()
    for column in NUMERIC_FEATURES:
        X[column] = pd.to_numeric(X[column], errors="coerce")
    X = X.astype({column: "category" for column in CATEGORICAL_FEATURES})
    return X, y.loc[valid], groups.loc[valid], weights.loc[valid].astype(float)


def evaluate_candidates(
    frame: pd.DataFrame,
    n_splits: int = N_SPLITS,
    seed: int = RANDOM_STATE,
) -> tuple[list[CandidateResult], pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Group-stratified CV (households never straddle folds) for every candidate.

    Metrics are survey-weighted; results are deterministic per (seed, n_splits).
    """

    X, y, groups, weights = build_model_frame(frame)
    if y.nunique() < 2:
        raise ValueError("Filtered view does not contain both target classes")
    if len(X) < n_splits * 30:
        raise ValueError("Not enough usable rows for a meaningful cross-validation")

    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds = list(splitter.split(X, y, groups=groups))

    results: list[CandidateResult] = []
    for name in CANDIDATE_NAMES:
        fold_auc: list[float] = []
        fold_f1: list[float] = []
        start = time.perf_counter()
        for train_idx, test_idx in folds:
            model = fit_candidate(name, X.iloc[train_idx], y.iloc[train_idx],
                                  weights.iloc[train_idx].to_numpy(), seed=seed)
            proba = model.predict_proba(X.iloc[test_idx])[:, 1]
            wt = weights.iloc[test_idx].to_numpy()
            yt = y.iloc[test_idx].to_numpy()
            fold_auc.append(float(roc_auc_score(yt, proba, sample_weight=wt)))
            fold_f1.append(float(f1_score(yt, (proba >= THRESHOLD).astype(int),
                                          sample_weight=wt, zero_division=0)))
        elapsed = time.perf_counter() - start
        auc = np.asarray(fold_auc, dtype=float)
        f1 = np.asarray(fold_f1, dtype=float)
        results.append(CandidateResult(
            name=name,
            fold_auc=tuple(fold_auc),
            fold_f1=tuple(fold_f1),
            mean_auc=float(np.mean(auc)),
            sd_auc=float(np.std(auc, ddof=1)),
            mean_f1=float(np.mean(f1)),
            sd_f1=float(np.std(f1, ddof=1)),
            fit_seconds=elapsed,
        ))
    return results, X, y, groups, weights


def select_candidate(results: list[CandidateResult]) -> CandidateResult:
    """Best non-baseline candidate by mean weighted F1 (deterministic tie-break)."""

    contenders = [r for r in results if r.name != BASELINE_NAME]
    return sorted(contenders, key=lambda r: (-r.mean_f1, r.name))[0]


@dataclass(frozen=True)
class ModelRecord:
    """One trained model with an auditable reproducibility record."""

    model_name: str
    features: tuple[str, ...]
    target_definition: str
    n_train: int
    n_test: int
    households_train: int
    households_test: int
    positive_rate_train: float
    positive_rate_test: float
    metrics: dict[str, float]
    confusion: dict[str, int]
    calibration_table: pd.DataFrame
    permutation_importance: dict[str, float]
    fold_metrics_table: pd.DataFrame
    selection_rule: str
    config: dict[str, object]
    reference_values: dict[str, float | str] = field(default_factory=dict)
    model: object = field(compare=False, default=None)


def train_final_model(
    frame: pd.DataFrame,
    n_splits: int = N_SPLITS,
    seed: int = RANDOM_STATE,
) -> ModelRecord | None:
    """Evaluate every candidate, select by CV weighted F1, refit, evaluate once on a held-out fold."""

    results, X, y, groups, weights = evaluate_candidates(frame, n_splits=n_splits, seed=seed)
    chosen = select_candidate(results)
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds = list(splitter.split(X, y, groups=groups))
    train_idx, test_idx = folds[-1]  # held-out evaluation fold

    model = fit_candidate(chosen.name, X.iloc[train_idx], y.iloc[train_idx],
                          weights.iloc[train_idx].to_numpy(), seed=seed)
    proba = model.predict_proba(X.iloc[test_idx])[:, 1]
    wt = weights.iloc[test_idx].to_numpy()
    yt = y.iloc[test_idx].to_numpy()
    pred = (proba >= THRESHOLD).astype(int)

    cm = confusion_matrix(yt, pred, labels=[0, 1])
    tn, fp, fn, tp = (int(v) for v in cm.ravel())
    metrics = {
        "roc_auc": float(roc_auc_score(yt, proba, sample_weight=wt)),
        "weighted_f1": float(f1_score(yt, pred, sample_weight=wt, zero_division=0)),
        "weighted_precision": float(precision_score(yt, pred, sample_weight=wt, zero_division=0)),
        "weighted_recall": float(recall_score(yt, pred, sample_weight=wt, zero_division=0)),
        "weighted_accuracy": float(accuracy_score(yt, pred, sample_weight=wt)),
        "weighted_log_loss": float(log_loss(yt, np.clip(proba, 1e-6, 1 - 1e-6), sample_weight=wt, labels=[0, 1])),
        "brier": float(brier_score_loss(yt, proba, sample_weight=wt)),
        "base_rate": float(np.average(yt, weights=wt)),
    }

    prob_true, prob_pred = calibration_curve(yt, proba, n_bins=5, strategy="quantile")
    calibration_table = pd.DataFrame({
        "Predicted bin midpoint": (prob_pred * 100).round(1),
        "Observed Priority share (%)": (prob_true * 100).round(1),
    })

    importance = permutation_importance(
        model, X.iloc[test_idx], yt, scoring="roc_auc", n_repeats=8, random_state=seed,
    )
    imp = dict(sorted(zip(X.columns, importance.importances_mean), key=lambda kv: -abs(kv[1])))

    fold_table = pd.DataFrame({
        "Model": [r.name for r in results],
        "CV weighted F1": [f"{r.mean_f1:.3f} ± {r.sd_f1:.3f}" for r in results],
        "CV weighted ROC-AUC": [f"{r.mean_auc:.3f} ± {r.sd_auc:.3f}" for r in results],
        "CV fit seconds": [f"{r.fit_seconds:.1f}" for r in results],
    })

    return ModelRecord(
        model_name=chosen.name,
        features=tuple(X.columns),
        target_definition=TARGET_LABEL,
        n_train=int(len(train_idx)),
        n_test=int(len(test_idx)),
        households_train=int(groups.iloc[train_idx].nunique()),
        households_test=int(groups.iloc[test_idx].nunique()),
        positive_rate_train=float(np.average(y.iloc[train_idx], weights=weights.iloc[train_idx])),
        positive_rate_test=float(np.average(yt, weights=wt)),
        metrics=metrics,
        confusion={"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        calibration_table=calibration_table,
        permutation_importance=imp,
        fold_metrics_table=fold_table,
        selection_rule="Highest mean weighted F1 across the group-stratified folds (baseline excluded).",
        config={
            "candidates": CANDIDATE_NAMES,
            "n_splits": n_splits,
            "seed": seed,
            "positive_class": "Priority",
            "threshold": THRESHOLD,
            "split": "StratifiedGroupKFold on respondent key (a household never crosses folds)",
            "weights": "hh_wt household weight passed to fitting and all metrics where supported",
        },
        reference_values=_reference_values(X, CATEGORICAL_FEATURES, NUMERIC_FEATURES, X.index[train_idx]),
        model=model,
    )


def _reference_values(
    X: pd.DataFrame,
    categorical: list[str],
    numeric: list[str],
    index: pd.Index,
) -> dict[str, float | str]:
    """Typical-row values (train-fold median / most frequent) for prediction inputs."""

    reference: dict[str, float | str] = {}
    for column in numeric:
        reference[column] = float(pd.to_numeric(X.loc[index, column], errors="coerce").median())
    for column in categorical:
        mode = X.loc[index, column].astype("object").mode(dropna=True)
        reference[column] = str(mode.iloc[0]) if len(mode) else "Unknown"
    return reference


def predict_priority(record: ModelRecord, values: dict[str, float | str]) -> float:
    """Probability of the Priority band for one composed household.

    Missing features fall back to the training-fold reference values; unknown
    categorical labels are handled by the pipeline's ordinal/one-hot encoders.
    """

    if record.model is None:
        raise ValueError("This record has no fitted model attached")
    row = {}
    for feature in record.features:
        row[feature] = values.get(feature, record.reference_values.get(feature))
    return float(record.model.predict_proba(pd.DataFrame([row]))[0, 1])


def _rate(value: float) -> str:
    return NA_FLAG if pd.isna(value) else f"{value:.1%}"


def holdout_artifacts(frame: pd.DataFrame, record: ModelRecord) -> pd.DataFrame:
    """Rebuild the held-out fold deterministically and score it with a fitted record.

    The splitter is seeded exactly like the training run, so the returned rows
    are identical to the evaluation fold used by `train_final_model`. Returns
    per-record truth, probability, survey weight and subgroup columns.
    """

    if record.model is None:
        raise ValueError("This record has no fitted model attached")
    X, y, groups, weights = build_model_frame(frame)
    splitter = StratifiedGroupKFold(n_splits=record.config["n_splits"], shuffle=True,
                                    random_state=record.config["seed"])
    folds = list(splitter.split(X, y, groups=groups))
    train_idx, test_idx = folds[-1]
    proba = record.model.predict_proba(X.iloc[test_idx])[:, 1]
    return pd.DataFrame({
        "paid": y.iloc[test_idx].to_numpy(),
        "proba": proba,
        "hh_wt": weights.iloc[test_idx].to_numpy(),
        "province": X["province"].iloc[test_idx].astype(str).to_numpy(),
        "setting": X["setting"].iloc[test_idx].astype(str).to_numpy(),
        "sex": X["sex"].iloc[test_idx].astype(str).to_numpy(),
    })


def threshold_metrics(table: pd.DataFrame, thresholds=()) -> pd.DataFrame:
    """Weighted precision/recall/F1 and predicted-positive share at fixed thresholds."""

    thresholds = thresholds or (.3, .4, .5, .6, .7)
    rows = []
    for t in thresholds:
        pred = (table["proba"].to_numpy() >= t).astype(int)
        wt = table["hh_wt"].to_numpy()
        yt = table["paid"].to_numpy()
        rows.append({
            "Threshold": f"{t:.1f}",
            "Weighted precision": round(float(precision_score(yt, pred, sample_weight=wt, zero_division=0)), 3),
            "Weighted recall": round(float(recall_score(yt, pred, sample_weight=wt, zero_division=0)), 3),
            "Weighted F1": round(float(f1_score(yt, pred, sample_weight=wt, zero_division=0)), 3),
            "Predicted as Priority": f"{np.average(pred, weights=wt):.1%}",
        })
    return pd.DataFrame(rows)


def pr_curve(table: pd.DataFrame, steps: int = 19) -> pd.DataFrame:
    """Precision/recall pairs across a probability-threshold sweep (for charting)."""

    rows = []
    for t in np.linspace(.05, .95, steps):
        pred = (table["proba"].to_numpy() >= t).astype(int)
        wt = table["hh_wt"].to_numpy()
        yt = table["paid"].to_numpy()
        rows.append({
            "threshold": float(t),
            "precision": float(precision_score(yt, pred, sample_weight=wt, zero_division=0) or 0),
            "recall": float(recall_score(yt, pred, sample_weight=wt, zero_division=0) or 0),
        })
    return pd.DataFrame(rows)


def subgroup_performance(table: pd.DataFrame, by: str, min_n: int = 150) -> pd.DataFrame:
    """Held-out metrics per subgroup of `by`; AUC only where both classes exist.

    Subgroups below `min_n` records are flagged as low-evidence cells.
    """

    rows = []
    for level, chunk in table.groupby(table[by].astype(str), dropna=False):
        wt = chunk["hh_wt"].to_numpy()
        yt = chunk["paid"].to_numpy()
        both = len(set(yt.tolist())) == 2
        pred = (chunk["proba"].to_numpy() >= THRESHOLD).astype(int)
        rows.append({
            by: str(level),
            "Records": int(len(chunk)),
            "Base rate": _rate(float(np.average(yt, weights=wt))) if len(wt) else NA,
            "ROC-AUC": f"{roc_auc_score(yt, chunk['proba'].to_numpy(), sample_weight=wt):.3f}" if both else NA,
            "Weighted F1": round(float(f1_score(yt, pred, sample_weight=wt, zero_division=0)), 3),
            "Weighted recall": round(float(recall_score(yt, pred, sample_weight=wt, zero_division=0)), 3),
            "Low evidence": "yes" if len(chunk) < min_n else "",
        })
    return pd.DataFrame(rows).sort_values("Weighted F1", ascending=False)
