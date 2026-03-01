from __future__ import annotations

import argparse
from pathlib import Path

import joblib
from sklearn.ensemble import IsolationForest

from py_lab.data_pipeline import basic_clean, load_csv


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument(
      "--csv",
      required=True,
      help="Training CSV path")
  parser.add_argument(
      "--out",
      default="/models/iforest.pkl",
      help="Output model path")
  parser.add_argument(
      "--contamination",
      type=float,
      default=0.05)
  parser.add_argument(
    "--random-state",
    type=int,
    default=42)

  args = parser.parse_args()
  df = basic_clean(load_csv(Path(args.csv)))
  X = df.select_dtypes(include=["number"]).copy()

  if X.shape[1] == 0 or X.shape[0] < 5:
    raise ValueError("Not enough numeric data to train IsolationForest model")

  model = IsolationForest(
      n_estimators=300,
      contamination=args.contamination,
      random_state=args.random_state,
      n_jobs=-1)
  model.fit(X)

  out_path = Path(args.out)
  out_path.parent.mkdir(parents=True, exist_ok=True)
  joblib.dump(
    {"model": model, "features": list(X.columns)}
    , out_path)
  print(f"Saved model to: {out_path} with features: {list(X.columns)}")


if __name__ == "__main__":
  main()
