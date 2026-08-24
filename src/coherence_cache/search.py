#!/usr/bin/env python3
"""
Dependency-free constructor-resilience search (classical simulated annealing).

Energy model:
  E = Σ_i h x_i  +  Σ_{i<j} J_ij x_i x_j

  h  = select_penalty          (negative → prefer selecting)
  J  = -α · consistency(i,j)   (support lowers energy when both on)
     + ρ · redundancy(i,j)     (near-duplicates raise energy when both on)

Redundancy is lexical Jaccard similarity above a threshold (or 0).
This stops compressed packets from retaining near-duplicate atoms.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

Pair = Tuple[int, int]


def as_text(atom) -> str:
    """Claims may be strings or {text: ...} records."""
    if isinstance(atom, dict):
        return str(atom.get("text") or "").strip()
    return str(atom).strip()


def token_set(s) -> set:
    return set(re.findall(r"[a-z0-9]+", as_text(s).lower()))


def lexical_similarity(a, b) -> float:
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def redundancy_map(
    atoms: Sequence[str],
    consistency: Optional[Dict[Pair, float]] = None,
    threshold: float = 0.22,
    high_consistency: float = 0.85,
) -> Dict[Pair, float]:
    """
    Sparse redundancy weights.
    - Lexical Jaccard >= threshold contributes directly
    - Very high consistency (likely near-paraphrase) contributes a soft penalty
      even when wording differs, scaled by lexical overlap floor
    """
    n = len(atoms)
    out: Dict[Pair, float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            sim = lexical_similarity(atoms[i], atoms[j])
            weight = 0.0
            if sim >= threshold:
                weight = sim
            if consistency is not None:
                c = consistency.get((i, j), consistency.get((j, i), 0.0))
                if c >= high_consistency:
                    # paraphrase-style support: penalize co-selection softly
                    weight = max(weight, 0.45 * float(c) + 0.25 * sim)
            if weight > 0:
                out[(i, j)] = weight
    return out


def build_qubo(
    n: int,
    consistency: Dict[Pair, float],
    select_penalty: float = -1.0,
    coupling_scale: float = 1.5,
    redundancy: Optional[Dict[Pair, float]] = None,
    redundancy_scale: float = 2.0,
) -> Dict[Pair, float]:
    """
    Upper-triangular QUBO (i,j) with i <= j.

    Support:   J_ij += -coupling_scale * consistency
    Redundancy: J_ij += +redundancy_scale * sim   (penalize co-selecting near-duplicates)
    """
    Q: Dict[Pair, float] = {}
    for i in range(n):
        Q[(i, i)] = select_penalty
    for (i, j), score in consistency.items():
        a, b = (i, j) if i <= j else (j, i)
        if a == b:
            continue
        Q[(a, b)] = Q.get((a, b), 0.0) + (-coupling_scale * score)
    if redundancy and redundancy_scale:
        for (i, j), sim in redundancy.items():
            a, b = (i, j) if i <= j else (j, i)
            if a == b:
                continue
            Q[(a, b)] = Q.get((a, b), 0.0) + (redundancy_scale * sim)
    return Q


def energy(x: List[int], Q: Dict[Pair, float]) -> float:
    e = 0.0
    for (i, j), q in Q.items():
        if i == j:
            e += q * x[i]
        else:
            e += q * x[i] * x[j]
    return e


def _ising_tables(n: int, Q: Dict[Pair, float]):
    neighbors: List[List[Tuple[int, float]]] = [[] for _ in range(n)]
    linear = [0.0] * n
    for (i, j), q in Q.items():
        if i == j:
            linear[i] = q
        else:
            neighbors[i].append((j, q))
            neighbors[j].append((i, q))
    return linear, neighbors


def _delta_flip(x: List[int], k: int, linear, neighbors) -> float:
    coupling = sum(q * x[j] for j, q in neighbors[k])
    if x[k] == 0:
        return linear[k] + coupling
    return -(linear[k] + coupling)


def _geometric_temps(num_sweeps: int, t0: float, t1: float) -> List[float]:
    if num_sweeps <= 1:
        return [t1]
    log_ratio = math.log(t1 / t0) if t0 > 0 and t1 > 0 else -5.0
    return [t0 * math.exp(log_ratio * s / (num_sweeps - 1)) for s in range(num_sweeps)]


def _metropolis_run(
    n: int,
    Q: Dict[Pair, float],
    temps: Sequence[float],
    flips_per_temp: int,
    rng: random.Random,
    max_size: Optional[int] = None,
) -> Tuple[List[int], float]:
    linear, neighbors = _ising_tables(n, Q)
    x = [rng.randint(0, 1) for _ in range(n)]
    if max_size is not None:
        # Random start may exceed the packet cap; drop extras.
        ones = [i for i, b in enumerate(x) if b]
        rng.shuffle(ones)
        for i in ones[max_size:]:
            x[i] = 0
    e = energy(x, Q)
    n_flips = n if flips_per_temp < 0 else max(1, flips_per_temp)
    for t in temps:
        t = max(float(t), 1e-12)
        for _ in range(n_flips):
            k = rng.randrange(n)
            if x[k] == 0 and max_size is not None and sum(x) >= max_size:
                continue
            d = _delta_flip(x, k, linear, neighbors)
            if d <= 0 or rng.random() < math.exp(-d / t):
                x[k] = 1 - x[k]
                e += d
    return x, e


def simulated_annealing(
    n: int,
    Q: Dict[Pair, float],
    num_reads: int = 50,
    num_sweeps: int = 800,
    t0: float = 2.0,
    t1: float = 0.01,
    seed: int = 42,
    flips_per_temp: int = 1,
    max_size: Optional[int] = None,
) -> List[Tuple[List[int], float]]:
    """Independent Metropolis chains with a geometric temperature schedule.

    ``flips_per_temp=1`` is one proposal per T (legacy). ``-1`` does n
    proposals per T (a sweep).
    """
    rng = random.Random(seed)
    temps = _geometric_temps(num_sweeps, t0, t1)
    results: List[Tuple[List[int], float]] = []
    for i in range(num_reads):
        chain_rng = random.Random(rng.randrange(1 << 30) + i)
        x, e = _metropolis_run(
            n, Q, temps, flips_per_temp, chain_rng, max_size=max_size
        )
        results.append((x, e))
    results.sort(key=lambda p: p[1])
    return results


def metropolis(
    n: int,
    Q: Dict[Pair, float],
    num_reads: int = 50,
    steps: int | None = None,
    t: float = 0.2,
    seed: int = 42,
    max_size: Optional[int] = None,
) -> List[Tuple[List[int], float]]:
    """Independent chains at fixed temperature (no annealing)."""
    rng = random.Random(seed)
    n_steps = steps if steps is not None else max(n * 200, 200)
    temps = [t] * n_steps
    results: List[Tuple[List[int], float]] = []
    for i in range(num_reads):
        chain_rng = random.Random(rng.randrange(1 << 30) + i)
        x, e = _metropolis_run(
            n, Q, temps, 1, chain_rng, max_size=max_size
        )
        results.append((x, e))
    results.sort(key=lambda p: p[1])
    return results


SAMPLE_METHODS = ("sa-geo", "sa-sweep", "metropolis")


def _normalize_consistency(
    consistency: Dict,
    n: int,
) -> Dict[Pair, float]:
    norm: Dict[Pair, float] = {}
    for key, score in consistency.items():
        if isinstance(key, str):
            i, j = map(int, key.split(","))
        else:
            i, j = int(key[0]), int(key[1])
        a, b = (i, j) if i <= j else (j, i)
        if 0 <= a < n and 0 <= b < n and a != b:
            norm[(a, b)] = float(score)
    return norm


def find_resilient_constructors(
    atoms: Sequence[str],
    consistency: Dict,
    select_penalty: float = -1.0,
    num_reads: int = 50,
    num_sweeps: int = 800,
    seed: int = 42,
    coupling_scale: float = 1.5,
    redundancy_scale: float = 2.0,
    redundancy_threshold: float = 0.22,
    method: str = "sa-sweep",
    max_size: Optional[int] = None,
) -> List[Tuple[List[str], float]]:
    n = len(atoms)
    if n == 0:
        return [([], 0.0)]
    norm = _normalize_consistency(consistency, n)
    red = redundancy_map(atoms, consistency=norm, threshold=redundancy_threshold) if redundancy_scale else {}
    Q = build_qubo(
        n,
        norm,
        select_penalty=select_penalty,
        coupling_scale=coupling_scale,
        redundancy=red,
        redundancy_scale=redundancy_scale,
    )
    method = (method or "sa-sweep").lower().replace("_", "-")
    if method == "sa-geo":
        runs = simulated_annealing(
            n,
            Q,
            num_reads=num_reads,
            num_sweeps=num_sweeps,
            seed=seed,
            flips_per_temp=1,
            max_size=max_size,
        )
    elif method == "sa-sweep":
        runs = simulated_annealing(
            n,
            Q,
            num_reads=num_reads,
            num_sweeps=num_sweeps,
            seed=seed,
            flips_per_temp=-1,
            max_size=max_size,
        )
    elif method == "metropolis":
        runs = metropolis(
            n,
            Q,
            num_reads=num_reads,
            steps=max(n * num_sweeps, n),
            seed=seed,
            max_size=max_size,
        )
    else:
        raise ValueError(f"unknown sample method {method!r}; use one of {SAMPLE_METHODS}")
    unique: List[Tuple[List[str], float]] = []
    seen = set()
    texts = [as_text(a) for a in atoms]
    for bits, eng in runs:
        key = tuple(i for i, v in enumerate(bits) if v == 1)
        if key not in seen:
            seen.add(key)
            unique.append(([texts[i] for i in key], float(eng)))
    return unique


def greedy_resilient_indices(
    atoms: Sequence[str],
    consistency: Dict,
    max_size: Optional[int] = None,
    select_penalty: float = -1.0,
    coupling_scale: float = 1.5,
    redundancy_scale: float = 2.0,
    redundancy_threshold: float = 0.22,
) -> Tuple[List[int], float]:
    """Like ``greedy_resilient`` but returns pool indices (stable for duplicate text)."""
    n = len(atoms)
    if n == 0:
        return [], 0.0
    norm = _normalize_consistency(consistency, n)
    red = redundancy_map(atoms, consistency=norm, threshold=redundancy_threshold) if redundancy_scale else {}
    Q = build_qubo(
        n,
        norm,
        select_penalty=select_penalty,
        coupling_scale=coupling_scale,
        redundancy=red,
        redundancy_scale=redundancy_scale,
    )
    selected: set = set()
    best_e = 0.0
    limit = max_size if max_size is not None else n
    if limit <= 0:
        return [], 0.0
    while len(selected) < limit:
        best_k, best_delta = None, 0.0
        for k in range(n):
            if k in selected:
                continue
            d = Q.get((k, k), 0.0)
            for j in selected:
                a, b = (k, j) if k <= j else (j, k)
                d += Q.get((a, b), 0.0)
            if d < best_delta:
                best_delta, best_k = d, k
        if best_k is None or best_delta >= -1e-12:
            break
        selected.add(best_k)
        best_e += best_delta
    return sorted(selected), float(best_e)


def greedy_resilient(
    atoms: Sequence[str],
    consistency: Dict,
    max_size: Optional[int] = None,
    select_penalty: float = -1.0,
    coupling_scale: float = 1.5,
    redundancy_scale: float = 2.0,
    redundancy_threshold: float = 0.22,
) -> Tuple[List[str], float]:
    """Constructive baseline with the same energy model (incl. redundancy)."""
    idx, eng = greedy_resilient_indices(
        atoms,
        consistency,
        max_size=max_size,
        select_penalty=select_penalty,
        coupling_scale=coupling_scale,
        redundancy_scale=redundancy_scale,
        redundancy_threshold=redundancy_threshold,
    )
    texts = [as_text(a) for a in atoms]
    return [texts[i] for i in idx], eng


def load_store(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def consistency_from_store(store: dict) -> Dict[Pair, float]:
    return _normalize_consistency(store.get("consistency") or {}, len(store.get("atoms") or []))


def main():
    parser = argparse.ArgumentParser(description="Run resilience search on an atoms.json store")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--num-reads", type=int, default=40)
    parser.add_argument("--num-sweeps", type=int, default=600)
    parser.add_argument("--select-penalty", type=float, default=-1.0)
    parser.add_argument("--redundancy-scale", type=float, default=2.0)
    parser.add_argument("--redundancy-threshold", type=float, default=0.22)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--greedy", action="store_true")
    parser.add_argument(
        "--method",
        choices=["greedy", "sa-geo", "sa-sweep", "metropolis"],
        default="sa-sweep",
    )
    parser.add_argument("--max-size", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    store = load_store(args.store)
    atoms = store.get("atoms", [])
    consistency = consistency_from_store(store)

    method = "greedy" if args.greedy else args.method
    if method == "greedy":
        selected, eng = greedy_resilient(
            atoms,
            consistency,
            max_size=args.max_size,
            select_penalty=args.select_penalty,
            redundancy_scale=args.redundancy_scale,
            redundancy_threshold=args.redundancy_threshold,
        )
        print(f"greedy  E={eng:.4f}  size={len(selected)}  red_scale={args.redundancy_scale}")
        for a in selected:
            print(f"  • {a[:110]}{'...' if len(a) > 110 else ''}")
        return

    packets = find_resilient_constructors(
        atoms,
        consistency,
        select_penalty=args.select_penalty,
        num_reads=args.num_reads,
        num_sweeps=args.num_sweeps,
        seed=args.seed,
        redundancy_scale=args.redundancy_scale,
        redundancy_threshold=args.redundancy_threshold,
        method=method,
        max_size=args.max_size,
    )
    print(f"atoms={len(atoms)} edges={len(consistency)} unique_packets={len(packets)}")
    for rank, (selected, eng) in enumerate(packets[: args.top]):
        print(f"\n--- packet {rank}  energy={eng:.4f}  size={len(selected)} ---")
        for a in selected:
            print(f"  • {a[:110]}{'...' if len(a) > 110 else ''}")


if __name__ == "__main__":
    main()
