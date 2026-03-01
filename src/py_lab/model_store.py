from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
from sklearn.ensemble import IsolationForest


@dataclass(frozen=True)
class IsolationForestBundle:
  model: IsolationForest
  feature_columns: list[str]

_cache: IsolationForestBundle | None = None

def load_iforest(path:str | Path) -> IsolationForestBundle:
  global _cache
  if _cache is not None:
    return _cache

  p = Path(path)
  obj:dict[str, Any] = joblib.load(p)
  bundle = IsolationForestBundle(
    model=obj["model"],
    feature_columns=list(obj["features"])
  )
  _cache=bundle
  return bundle

def reload_iforest(path: str | Path) -> IsolationForestBundle:
  global _cache
  _cache = None
  return load_iforest(path)
