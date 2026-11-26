"""Core metrics: Hit@k, MRR, mean, std, citation checks."""
from __future__ import annotations
import math
import statistics
from typing import Iterable, Sequence


def reciprocal_rank(retrieved: Sequence[str], expected: set[str]) -> float:
    for rank, path in enumerate(retrieved, start=1):
        if path in expected:
            return 1.0 / rank
    return 0.0


def hit_at_k(retrieved: Sequence[str], expected: set[str], k: int = 5) -> float:
    return 1.0 if any(p in expected for p in retrieved[:k]) else 0.0


def mean_std(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return float(values[0]), 0.0
    return statistics.mean(values), statistics.stdev(values)


def citation_support_rate(
    cited_paths: Iterable[str],
    retrieved_paths: Sequence[str],
) -> float:
    """Fraction of cited files that appear in the retrieved set."""
    cited = list(cited_paths)
    if not cited:
        return 0.0
    retrieved = set(retrieved_paths)
    supported = sum(1 for c in cited if c in retrieved)
    return supported / len(cited)


def contains_any(text: str, needles: Sequence[str]) -> bool:
    lower = text.lower()
    return any(n.lower() in lower for n in needles)
