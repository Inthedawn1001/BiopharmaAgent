"""Small in-memory metrics registry for local development."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InMemoryMetrics:
    counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    timings: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def increment(self, name: str, value: float = 1.0, **labels: str) -> None:
        self.counters[_metric_key(name, labels)] += value

    def observe(self, name: str, value: float, **labels: str) -> None:
        self.timings[_metric_key(name, labels)].append(value)

    def snapshot(self) -> dict[str, Any]:
        timing_summary = {}
        for key, values in self.timings.items():
            timing_summary[key] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
            }
        return {
            "counters": dict(self.counters),
            "timings": timing_summary,
        }


def _metric_key(name: str, labels: dict[str, str]) -> str:
    if not labels:
        return name
    suffix = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    return f"{name}{{{suffix}}}"

