from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.ensemble import IsolationForest

from py_lab.model_store import IsolationForestBundle


@dataclass(frozen=True)
class AnomalyResult:
  # top-k 异常行的索引（原 df index）
  indices: list[int]
  # 对应的 anomaly score（越大越异常，便于解释）
  scores: list[float]

def _select_numeric_features(df:pd.DataFrame) -> pd.DataFrame:
  numeric = df.select_dtypes(include=["number"]).copy()
  return numeric

def detect_anomalies(
  df:pd.DataFrame,
  top_k:int = 5,
  contamination:float=0.05,
  random_state:int=42) -> AnomalyResult | None:
  X = _select_numeric_features(df)
  if X.shape[1] == 0 or X.shape[0] < 5:
    return None

  # IsolationForest：decision_function 越大越正常；score_samples 越大越正常
  # 我们取 -score_samples 作为“越大越异常”的 score
  model = IsolationForest(
    n_estimators=200,
    contamination=contamination,
    random_state=random_state,
    n_jobs=-1)
  model.fit(X)

  # 越大越异常
  scores = (-model.score_samples(X)).astype(float)

  top_k = max(1, min(int(top_k), len(scores)))
  top_idx = pd.Series(scores, index=df.index).sort_values(ascending=False).head(top_k)

  return AnomalyResult(
    indices=[int(i) for i in top_idx.index],
    scores=[float(v) for v in top_idx.values]
    )

def score_anomalies_with_model(
  df: pd.DataFrame,
  bundle: IsolationForestBundle,
  top_k: int = 5
) -> AnomalyResult | None:
  X = df.reindex(columns=bundle.feature_columns)
  # 缺列或无数据，直接反馈None
  if X.shape[1] == 0 or X.shape[0] < 1:
    return None

  X = X.apply(pd.to_numeric, errors="coerce")

  scores = (-bundle.model.score_samples(X)).astype(float)
  top_k = max(1, min(int(top_k), len(scores)))
  top_idx = pd.Series(scores, index=df.index).sort_values(ascending=False).head(top_k)

  return AnomalyResult(
    indices=[int(i) for i in top_idx.index],
    scores=[float(v) for v in top_idx.values]
  )
