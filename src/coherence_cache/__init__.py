"""Constructor resilience — durable claims, packets, and share files."""

from .intersection import intersection_packet
from .search import (
    SAMPLE_METHODS,
    build_qubo,
    energy,
    find_resilient_constructors,
    greedy_resilient,
    metropolis,
    redundancy_map,
)

__version__ = "0.1.2"
__all__ = [
    "SAMPLE_METHODS",
    "build_qubo",
    "energy",
    "find_resilient_constructors",
    "greedy_resilient",
    "intersection_packet",
    "metropolis",
    "redundancy_map",
    "__version__",
]
