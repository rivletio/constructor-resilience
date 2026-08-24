"""Constructor resilience — open coherence cache (atoms + resilient packets)."""

from .intersection import intersection_packet
from .search import (
    build_qubo,
    energy,
    find_resilient_constructors,
    greedy_resilient,
    redundancy_map,
)

__version__ = "0.1.2"
__all__ = [
    "build_qubo",
    "energy",
    "find_resilient_constructors",
    "greedy_resilient",
    "intersection_packet",
    "redundancy_map",
    "__version__",
]
