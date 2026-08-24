"""Interest-surface overlap: intersection or union, plus belief challenges.

Given two topical stores (or pre-built packets), produce a resilient packet
over the union candidate pool. Intersection keeps only cross-linked atoms;
union keeps one-sided atoms too. Each selected atom is challenged against
the other surface: does it still hold given what they claimed?

This is host-agnostic. Hosts map surfaces to circle policy; this module
only computes the overlap packet.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .atoms import is_active
from .mentions import extract_mentions
from .search import as_text, greedy_resilient_indices, token_set

Pair = Tuple[int, int]

# Function words that inflate Jaccard without meaning a shared claim.
_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "to",
        "in",
        "is",
        "are",
        "was",
        "were",
        "for",
        "on",
        "with",
        "as",
        "by",
        "at",
        "from",
        "that",
        "this",
        "it",
        "be",
        "its",
        "into",
        "than",
        "then",
        "also",
        "about",
        "over",
        "under",
        "can",
        "may",
        "will",
        "we",
        "i",
        "you",
        "they",
        "he",
        "she",
        "does",
        "do",
        "did",
    }
)
_NEG = frozenset(
    {
        "not",
        "never",
        "no",
        "none",
        "neither",
        "impossible",
        "cannot",
        "cant",
        "false",
        "without",
    }
)


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


def _content_tokens(text) -> set[str]:
    return token_set(text) - _STOP


def _stem_tokens(text) -> set[str]:
    toks = _content_tokens(text)
    out = set(toks)
    for t in toks:
        if len(t) > 4 and t.endswith("s"):
            out.add(t[:-1])
    return out


def _core_polarity(text) -> Tuple[set[str], bool]:
    toks = _stem_tokens(text)
    negated = bool(_content_tokens(text) & _NEG) or "impossible" in as_text(text).lower()
    return toks - _NEG, negated


def claims_tension(a, b) -> bool:
    """True when two claims share a core but disagree in polarity."""
    ca, na = _core_polarity(a)
    cb, nb = _core_polarity(b)
    if not ca or not cb or na == nb:
        return False
    inter = ca & cb
    if not inter:
        return False
    jacc = len(inter) / len(ca | cb)
    return len(inter) >= 3 or jacc >= 0.4


def cross_affinity(a, b) -> float:
    """Lexical Jaccard, stem Jaccard, and shared mention names."""
    ta, tb = _content_tokens(a), _content_tokens(b)
    lex = (len(ta & tb) / len(ta | tb)) if ta and tb else 0.0
    sa, sb = _stem_tokens(a), _stem_tokens(b)
    stem = (len(sa & sb) / len(sa | sb)) if sa and sb else 0.0
    ma, mb = _mention_names(a), _mention_names(b)
    mention = 0.0
    if ma and mb:
        mention = len(ma & mb) / len(ma | mb)
        if ma & mb:
            mention = max(mention, 0.62)
    rare = {t for t in (ta & tb) if len(t) >= 8}
    rare_boost = 0.22 if rare else 0.0
    return max(lex, stem, mention, rare_boost)


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


def _atom_at(store: dict, idx) -> object:
    atoms = store.get("atoms") or []
    if isinstance(idx, int) and 0 <= idx < len(atoms):
        return atoms[idx]
    return None


def _active_view(store: dict) -> Tuple[list, Dict[Pair, float], List[int]]:
    """Active non-blank atoms, remapped consistency, original store indices."""
    atoms = list(store.get("atoms") or [])
    keep: List[int] = []
    for i, a in enumerate(atoms):
        if not is_active(a):
            continue
        if not as_text(a).strip():
            continue
        keep.append(i)
    remap = {old: new for new, old in enumerate(keep)}
    cons: Dict[Pair, float] = {}
    for (i, j), s in _parse_consistency(store).items():
        if i in remap and j in remap:
            a, b = remap[i], remap[j]
            if a > b:
                a, b = b, a
            if a != b:
                cons[(a, b)] = s
    return [atoms[i] for i in keep], cons, keep


def overlap_challenges(
    provenance: Sequence[dict],
    my_store: dict,
    their_store: dict,
    *,
    min_sim: float = 0.18,
) -> List[dict]:
    """One belief-challenge per selected atom against the other full surface.

    Prefers a polarity conflict over a paraphrase so the loop actually
    challenges whether the atom still holds.
    """
    out: List[dict] = []
    for p in provenance:
        text = as_text(p.get("text"))
        src = p.get("source")
        if src == "mine":
            others, other_src, self_store = (
                list(their_store.get("atoms") or []),
                "theirs",
                my_store,
            )
        elif src == "theirs":
            others, other_src, self_store = (
                list(my_store.get("atoms") or []),
                "mine",
                their_store,
            )
        else:
            continue
        self_atom = _atom_at(self_store, p.get("store_index")) or text
        best_support: Optional[Tuple[float, int, str]] = None
        best_tension: Optional[Tuple[float, int, str]] = None
        for j, o in enumerate(others):
            if not is_active(o) or not as_text(o).strip():
                continue
            s = cross_affinity(self_atom, o)
            if s < min_sim:
                continue
            hit = (s, j, as_text(o))
            if claims_tension(self_atom, o):
                if best_tension is None or s > best_tension[0]:
                    best_tension = hit
            elif best_support is None or s > best_support[0]:
                best_support = hit
        rec = {
            "source": src,
            "store_index": p.get("store_index"),
            "text": text,
            "other_source": other_src,
        }
        chosen = best_tension or best_support
        if chosen is not None:
            s, j, other_text = chosen
            rec["other"] = other_text
            rec["other_store_index"] = j
            rec["affinity"] = round(float(s), 3)
            rec["tension"] = best_tension is not None
            rec["prompt"] = (
                "These claims conflict — does this atom still hold?"
                if rec["tension"]
                else "Does this atom still hold given the other side?"
            )
        else:
            rec["other"] = None
            rec["other_store_index"] = None
            rec["affinity"] = 0.0
            rec["tension"] = False
            rec["prompt"] = (
                "No counterpart on the other surface — "
                "is this still true without them?"
            )
        out.append(rec)
    return out


def build_intersection_pool(
    my_store: dict,
    their_store: dict,
    *,
    min_cross_sim: float = 0.18,
    seed_query: Optional[str] = None,
) -> Tuple[List[str], Dict[Pair, float], List[dict], int]:
    """
    Build a candidate atom list + consistency map for intersection search.

    Pool layout:
      [0 .. n_mine)     = my atoms (tagged source=mine)
      [n_mine .. n)     = their atoms (tagged source=theirs)

    Cross edges use lexical alignment (and optional seed boost).
    """
    mine_raw, mine_cons, mine_orig = _active_view(my_store)
    theirs_raw, theirs_cons, theirs_orig = _active_view(their_store)
    mine = [as_text(a) for a in mine_raw]
    theirs = [as_text(a) for a in theirs_raw]
    pool: List[str] = mine + theirs
    n_mine = len(mine)
    cons: Dict[Pair, float] = {}

    # Internal edges, damped so dense hubs cannot drown the overlap.
    for (i, j), s in mine_cons.items():
        cons[(i, j)] = 0.4 * s
    for (i, j), s in theirs_cons.items():
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
        provenance.append(
            {
                "index": i,
                "source": "mine",
                "text": a,
                "store_index": mine_orig[i],
            }
        )
    for j, b in enumerate(theirs):
        provenance.append(
            {
                "index": j + n_mine,
                "source": "theirs",
                "text": b,
                "store_index": theirs_orig[j],
            }
        )

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
    kind: Optional[str] = None,
) -> dict:
    """
    Compute a resilient packet over my ∪ their interest surfaces.

    If ``require_cross`` is True, prefer packets that include at least one
    atom from each side when possible (true intersection flavor).
    Union sets ``require_cross=False`` and ``kind="interest_union"``.
    """
    kind = kind or (
        "interest_union" if not require_cross else "interest_intersection"
    )
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

    def _doc(atoms, energy, indices, prov) -> dict:
        return {
            "version": 1,
            "kind": kind,
            "method": "greedy",
            "energy": float(energy),
            "max_size": max_size,
            "seed_query": seed_query,
            "atom_indices": indices,
            "atoms": list(atoms),
            "provenance": prov,
            "challenges": overlap_challenges(
                prov, my_store, their_store, min_sim=min_cross_sim
            ),
            "atom_count_source": n_union,
            "n_mine": n_mine_orig,
            "n_theirs": n_theirs_orig,
            "require_cross": require_cross,
        }

    if not pool:
        return _doc([], 0.0, [], [])
    if require_cross and (n_mine_orig == 0 or n_theirs_orig == 0):
        return _doc([], 0.0, [], [])

    if require_cross and n_mine > 0 and len(pool) > n_mine:
        linked: set[int] = set()
        for (i, j) in cons:
            if (i < n_mine) != (j < n_mine):
                linked.add(i)
                linked.add(j)
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

    selected_idx, eng = greedy_resilient_indices(
        pool,
        cons,
        max_size=max_size,
        redundancy_scale=redundancy_scale,
    )

    if require_cross and n_mine > 0 and len(pool) > n_mine and selected_idx:
        sources = {"mine" if i < n_mine else "theirs" for i in selected_idx}
        if sources != {"mine", "theirs"} and (max_size or 0) >= 2:

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
            forced: List[int] = []
            if mine_idxs and cross_degree(mine_idxs[0]) > 0:
                forced.append(mine_idxs[0])
            if their_idxs and cross_degree(their_idxs[0]) > 0:
                forced.append(their_idxs[0])
            rest, eng2 = greedy_resilient_indices(
                pool,
                cons,
                max_size=max_size,
                redundancy_scale=redundancy_scale,
            )
            for i in rest:
                if i not in forced and len(forced) < max_size:
                    forced.append(i)
            if forced:
                selected_idx = forced[:max_size]
                eng = eng2

    selected = []
    indices = []
    prov_sel = []
    for i in selected_idx:
        if i < 0 or i >= len(pool):
            continue
        p = (
            provenance[i]
            if i < len(provenance)
            else {"index": i, "source": "?", "text": pool[i]}
        )
        selected.append(pool[i])
        indices.append(int(p.get("index", i)))
        prov_sel.append(p)
    return _doc(selected, eng, indices, prov_sel)
