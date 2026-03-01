from __future__ import annotations

import pandas as pd

from py_lab.anomaly import detect_anomalies


def test_detect_anomalies_finds_outliers() -> None:
    df = pd.DataFrame(
        {
            "age": [30, 31, 29, 32, 28, 99],
            "height": [168, 170, 169, 171, 167, 220],
            "name": ["a", "b", "c", "d", "e", "out"],
        }
    )
    res = detect_anomalies(df, top_k=2, contamination=0.2, random_state=42)
    assert res is not None
    # 期望 outlier 行（index=5）出现在 top_k 中
    assert 5 in res.indices
