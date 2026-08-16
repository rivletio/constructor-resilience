"""Interest-surface intersection: what we share when we don't share everything.

Given two topical stores (or pre-built packets), produce a resilient packet
over the *union candidate pool* weighted toward mutual support — the live
"browse overlap with Lex" primitive.

This is host-agnostic. Ikonic maps surfaces to circle policy; this module
only computes the overlap packet.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .search import greedy_resilient, lexical_similarity

Pair = Tuple[int, int]


def _parse_consistency(store: dict) -> Dict[Pair, float]:
    out: Dict[Pair, float] = {}
    n = len(store.get("atoms") or [])
    for key, score in (store.get("consistency") or {}).items():
        try:
            if isinstance(key, str) and "," in key:
                i, j = map(int, key.split(","))
            else:
                continue
            a, b = (i, j) if i < j else (j, i)
            if 0 <= a < n and 0 <= b < n and a != b:
                out[(a, b)] = float(score)
        except Exception:
            continue
    return out


def align_cross_atoms(
    mine: Sequence[str],
    theirs: Sequence[str],
    min_sim: float = 0.18,
) -> List[Tuple[int, int, float]]:
    """Soft alignment edges between my atom i and their atom j by lexical sim."""
    links: List[Tuple[int, int, float]] = []
    for i, a in enumerate(mine):
        for j, b in enumerate(theirs):
            s = lexical_similarity(a, b)
            if s >= min_sim:
                links.append((i, j, s))
    return links


def build_intersection_pool(
    my_store: dict,
    their_store: dict,
    *,
    min_cross_sim: float = 0.18,
    seed_query: Optional[str] = None,
) -> Tuple[List[str], Dict[Pair, float], List[dict]]:
    """
    Build a candidate atom list + consistency map for intersection search.

    Pool layout:
      [0 .. n_mine)     = my atoms (tagged source=mine)
      [n_mine .. n)     = their atoms (tagged source=theirs)

    Cross edges use lexical alignment (and optional seed boost).
    """
    mine = list(my_store.get("atoms") or [])
    theirs = list(their_store.get("atoms") or [])
    pool: List[str] = mine + theirs
    n_mine = len(mine)
    cons: Dict[Pair, float] = {}

    # Internal edges from each store, remapped for "theirs"
    for (i, j), s in _parse_consistency(my_store).items():
        cons[(i, j)] = s
    for (i, j), s in _parse_consistency(their_store).items():
        cons[(i + n_mine, j + n_mine)] = s

    # Cross-surface affinity
    for i, j, s in align_cross_atoms(mine, theirs, min_sim=min_cross_sim):
        a, b = (i, j + n_mine) if i < j + n_mine else (j + n_mine, i)
        # Soft positive support for related interests across people
        cons[(a, b)] = max(cons.get((a, b), 0.0), min(0.9, 0.35 + 0.7 * s))

    # Seed query: boost atoms that mention query tokens
    if seed_query:
        q = seed_query.lower()
        q_tokens = set(q.split())
        for idx, atom in enumerate(pool):
            al = atom.lower()
            hit = sum(1 for t in q_tokens if len(t) > 2 and t in al)
            if hit:
                # mild self-bias via coupling to a synthetic "seed" is hard in
                # pure QUBO without extra node; instead annotate provenance.
                pass

    provenance = []
    for i, a in enumerate(mine):
        provenance.append({"index": i, "source": "mine", "text": a})
    for j, b in enumerate(theirs):
        provenance.append({"index": j + n_mine, "source": "theirs", "text": b})

    return pool, cons, provenance


def intersection_packet(
    my_store: dict,
    their_store: dict,
    *,
    max_size: int = 8,
    min_cross_sim: float = 0.18,
    seed_query: Optional[str] = None,
    redundancy_scale: float = 2.0,
    require_cross: bool = True,
) -> dict:
    """
    Compute a resilient packet over my ∪ their interest surfaces.

    If ``require_cross`` is True, prefer packets that include at least one
    atom from each side when possible (true intersection flavor).
    """
    pool, cons, provenance = build_intersection_pool(
        my_store,
        their_store,
        min_cross_sim=min_cross_sim,
        seed_query=seed_query,
    )
    n_mine = len(my_store.get("atoms") or [])
    if not pool:
        return {
            "version": 1,
            "kind": "interest_intersection",
            "atoms": [],
            "atom_indices": [],
            "energy": 0.0,
            "method": "greedy",
            "max_size": max_size,
            "provenance": [],
        }

    selected, eng = greedy_resilient(
        pool,
        cons,
        max_size=max_size,
        redundancy_scale=redundancy_scale,
    )

    # If we got a one-sided packet and both sides non-empty, force a balanced try
    if require_cross and n_mine > 0 and len(pool) > n_mine:
        sources = set()
        for s in selected:
            idx = pool.index(s)
            sources.add("mine" if idx < n_mine else "theirs")
        if sources != {"mine", "theirs"} and max_size >= 2:
            # Greedy from each side: take best from mine and theirs by degree
            mine_idxs = list(range(n_mine))
            their_idxs = list(range(n_mine, len(pool)))

            def degree(i: int) -> float:
                return sum(abs(s) for (a, b), s in cons.items() if a == i or b == i)

            mine_idxs.sort(key=degree, reverse=True)
            their_idxs.sort(key=degree, reverse=True)
            forced: List[str] = []
            if mine_idxs:
                forced.append(pool[mine_idxs[0]])
            if their_idxs:
                forced.append(pool[their_idxs[0]])
            # Fill remainder with greedy on full pool, skipping already chosen
            rest, eng2 = greedy_resilient(
                pool,
                cons,
                max_size=max_size,
                redundancy_scale=redundancy_scale,
            )
            for a in rest:
                if a not in forced and len(forced) < max_size:
                    forced.append(a)
            selected = forced[:max_size]
            eng = eng2

    indices = []
    for s in selected:
        try:
            indices.append(pool.index(s))
        except ValueError:
            continue

    prov_sel = [provenance[i] for i in indices if i < len(provenance)]
    return {
        "version": 1,
        "kind": "interest_intersection",
        "method": "greedy",
        "energy": float(eng),
        "max_size": max_size,
        "seed_query": seed_query,
        "atom_indices": indices,
        "atoms": list(selected),
        "provenance": prov_sel,
        "atom_count_source": len(pool),
        "n_mine": n_mine,
        "n_theirs": len(pool) - n_mine,
    }
