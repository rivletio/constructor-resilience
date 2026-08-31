"""Constructor resilience — durable claims, packets, and share files."""

from .intersection import (
    compare_overlap,
    intersection_packet,
    overlap_challenges,
    overlap_lookup,
    union_dataset,
)
from .search import (
    SAMPLE_METHODS,
    build_qubo,
    energy,
    find_resilient_constructors,
    greedy_resilient,
    metropolis,
    redundancy_map,
)

__version__ = "0.1.4"
__all__ = [
    "SAMPLE_METHODS",
    "build_qubo",
    "energy",
    "find_resilient_constructors",
    "greedy_resilient",
    "compare_overlap",
    "intersection_packet",
    "overlap_challenges",
    "overlap_lookup",
    "union_dataset",
    "metropolis",
    "redundancy_map",
    "__version__",
]
