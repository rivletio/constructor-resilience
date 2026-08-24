"""Interest-surface intersection: what we share when we don't share everything.

Given two topical stores (or pre-built packets), produce a resilient packet
over the *union candidate pool* weighted toward mutual support — the live
"browse overlap with Lex" primitive.

This is host-agnostic. Hosts map surfaces to circle policy; this module
only computes the overlap packet.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .mentions import extract_mentions
from .search import as_text, greedy_resilient, lexical_similarity, token_set

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


def _mention_names(atom) -> set[str]:
    names: set[str] = set()
    if isinstance(atom, dict):
        for m in atom.get("mentions") or []:
            if isinstance(m, dict):
                n = str(m.get("name") or "").strip().lower()
            else:
                n = str(m).strip().lower()
            if n:
                names.add(n)
    for m in extract_mentions(as_text(atom)):
        names.add(str(m.get("name") or "").strip().lower())
    names.discard("")
    return names


def _stem_tokens(text) -> set[str]:
    toks = token_set(text)
    out = set(toks)
    for t in toks:
        if len(t) > 4 and t.endswith("s"):
            out.add(t[:-1])
    return out


def cross_affinity(a, b) -> float:
    """Lexical Jaccard, stem Jaccard, and shared mention names."""
    ta, tb = as_text(a), as_text(b)
    lex = lexical_similarity(ta, tb)
    sa, sb = _stem_tokens(ta), _stem_tokens(tb)
    stem = (len(sa & sb) / len(sa | sb)) if sa and sb else 0.0
    ma, mb = _mention_names(a), _mention_names(b)
    mention = 0.0
    if ma and mb:
        mention = len(ma & mb) / len(ma | mb)
        if ma & mb:
            mention = max(mention, 0.62)
    return max(lex, stem, mention)


def align_cross_atoms(
    mine: Sequence,
    theirs: Sequence,
    min_sim: float = 0.18,
) -> List[Tuple[int, int, float]]:
    """Soft alignment edges between my atom i and their atom j."""
    links: List[Tuple[int, int, float]] = []
    for i, a in enumerate(mine):
        for j, b in enumerate(theirs):
            s = cross_affinity(a, b)
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
    mine_raw = list(my_store.get("atoms") or [])
    theirs_raw = list(their_store.get("atoms") or [])
    mine = [as_text(a) for a in mine_raw]
    theirs = [as_text(a) for a in theirs_raw]
    pool: List[str] = mine + theirs
    n_mine = len(mine)
    cons: Dict[Pair, float] = {}

    # Internal edges, damped so dense hubs cannot drown the overlap.
    for (i, j), s in _parse_consistency(my_store).items():
        cons[(i, j)] = 0.4 * s
    for (i, j), s in _parse_consistency(their_store).items():
        cons[(i + n_mine, j + n_mine)] = 0.4 * s

    # Cross-surface affinity (lexical + stems + mention joins)
    for i, j, s in align_cross_atoms(mine_raw, theirs_raw, min_sim=min_cross_sim):
        a, b = (i, j + n_mine) if i < j + n_mine else (j + n_mine, i)
        cons[(a, b)] = max(cons.get((a, b), 0.0), min(0.95, 0.4 + 0.7 * s))

    # Seed query: boost atoms that mention query tokens via pairwise glue
    # to a virtual high-coverage hub (implemented as extra self-preference
    # through strong edges among seed-matching atoms).
    if seed_query:
        q = seed_query.lower()
        q_tokens = [t for t in q.split() if len(t) > 2]
        seed_hits = []
        for idx, atom in enumerate(pool):
            al = atom.lower()
            hit = sum(1 for t in q_tokens if t in al)
            if hit:
                seed_hits.append((idx, hit))
        # Link seed-matching atoms together with positive support so greedy
        # prefers them as a cluster (realtime dial sensitivity).
        for i in range(len(seed_hits)):
            for j in range(i + 1, len(seed_hits)):
                a, ha = seed_hits[i]
                b, hb = seed_hits[j]
                lo, hi = (a, b) if a < b else (b, a)
                boost = min(0.95, 0.45 + 0.15 * (ha + hb))
                cons[(lo, hi)] = max(cons.get((lo, hi), 0.0), boost)

    provenance = []
    for i, a in enumerate(mine):
        provenance.append({"index": i, "source": "mine", "text": a})
    for j, b in enumerate(theirs):
        provenance.append({"index": j + n_mine, "source": "theirs", "text": b})

    return pool, cons, provenance, n_mine


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
    built = build_intersection_pool(
        my_store,
        their_store,
        min_cross_sim=min_cross_sim,
        seed_query=seed_query,
    )
    pool, cons, provenance, n_mine = built
    n_mine_orig = n_mine
    n_theirs_orig = len(pool) - n_mine
    n_union = len(pool)
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

    if require_cross and n_mine > 0 and len(pool) > n_mine:
        linked: set[int] = set()
        for (i, j) in cons:
            if (i < n_mine) != (j < n_mine):
                linked.add(i)
                linked.add(j)
        if seed_query:
            q_tokens = [t for t in seed_query.lower().split() if len(t) > 2]
            for idx, atom in enumerate(pool):
                al = atom.lower()
                if any(t in al for t in q_tokens):
                    linked.add(idx)
        if not linked:
            pool, cons, provenance, n_mine = [], {}, [], 0
        elif linked:
            keep = sorted(linked)
            remap = {old: new for new, old in enumerate(keep)}
            sub_pool = [pool[i] for i in keep]
            sub_cons: Dict[Pair, float] = {}
            for (i, j), s in cons.items():
                if i in remap and j in remap:
                    a, b = remap[i], remap[j]
                    if a > b:
                        a, b = b, a
                    if a != b:
                        sub_cons[(a, b)] = s
            pool, cons, n_mine_sub = sub_pool, sub_cons, sum(1 for i in keep if i < n_mine)
            provenance = [provenance[i] for i in keep]
            n_mine = n_mine_sub

    selected, eng = greedy_resilient(
        pool,
        cons,
        max_size=max_size,
        redundancy_scale=redundancy_scale,
    )

    if require_cross and n_mine > 0 and len(pool) > n_mine and selected:
        sources = set()
        for s in selected:
            idx = pool.index(s)
            sources.add("mine" if idx < n_mine else "theirs")
        if sources != {"mine", "theirs"} and max_size >= 2:

            def cross_degree(i: int) -> float:
                total = 0.0
                for (a, b), s in cons.items():
                    if a != i and b != i:
                        continue
                    other = b if a == i else a
                    if (i < n_mine) != (other < n_mine):
                        total += abs(s)
                return total

            mine_idxs = sorted(range(n_mine), key=cross_degree, reverse=True)
            their_idxs = sorted(range(n_mine, len(pool)), key=cross_degree, reverse=True)
            forced: List[str] = []
            if mine_idxs and cross_degree(mine_idxs[0]) > 0:
                forced.append(pool[mine_idxs[0]])
            if their_idxs and cross_degree(their_idxs[0]) > 0:
                forced.append(pool[their_idxs[0]])
            rest, eng2 = greedy_resilient(
                pool,
                cons,
                max_size=max_size,
                redundancy_scale=redundancy_scale,
            )
            for a in rest:
                if a not in forced and len(forced) < max_size:
                    forced.append(a)
            if forced:
                selected = forced[:max_size]
                eng = eng2

    indices = []
    prov_sel = []
    for s in selected:
        try:
            i = pool.index(s)
        except ValueError:
            continue
        p = provenance[i] if i < len(provenance) else {"index": i, "source": "?", "text": s}
        indices.append(int(p.get("index", i)))
        prov_sel.append(p)
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
        "atom_count_source": n_union,
        "n_mine": n_mine_orig,
        "n_theirs": n_theirs_orig,
    }
