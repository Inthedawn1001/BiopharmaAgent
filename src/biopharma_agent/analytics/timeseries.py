"""Small time-series helpers for market indicators."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass
class TimeSeriesAnalyzer:
    """Analyze trend and outliers without external dependencies."""

    outlier_zscore: float = 2.5

    def summarize(self, values: list[float]) -> dict[str, object]:
        if not values:
            return {"count": 0, "trend": "unknown", "mean": None, "outliers": []}

        first = values[0]
        last = values[-1]
        delta = last - first
        trend = "flat"
        if delta > 0:
            trend = "up"
        elif delta < 0:
            trend = "down"

        avg = mean(values)
        std = pstdev(values) if len(values) > 1 else 0.0
        outliers = []
        if std:
            for index, value in enumerate(values):
                zscore = (value - avg) / std
                if abs(zscore) >= self.outlier_zscore:
                    outliers.append({"index": index, "value": value, "zscore": round(zscore, 4)})

        return {
            "count": len(values),
            "trend": trend,
            "first": first,
            "last": last,
            "delta": delta,
            "mean": round(avg, 4),
            "std": round(std, 4),
            "outliers": outliers,
        }

