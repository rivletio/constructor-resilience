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

from .atoms import (
    REVIEW_EDITED,
    REVIEW_PENDING,
    atom_review_status,
    is_active,
    query_overlap,
    traveling_atom,
)
from .mentions import (
    MENTION_GROUND_MIN,
    VALID_CONSTRAINT,
    extract_mentions,
    join_grounding,
    mention_attested_score,
)
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


def _canonical_join_names(names: Sequence[str]) -> list[str]:
    """Dedupe 'the Transformer' / 'Transformer' for JOIN display."""
    out: List[str] = []
    seen: set[str] = set()
    for n in names:
        n = str(n or "").strip().lower()
        if n.startswith("the "):
            n = n[4:].strip()
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
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


def _text_overlap(a, b) -> float:
    """Lexical/stem Jaccard only — no rare-token boost, no mention floor."""
    ta, tb = _content_tokens(a), _content_tokens(b)
    lex = (len(ta & tb) / len(ta | tb)) if ta and tb else 0.0
    sa, sb = _stem_tokens(a), _stem_tokens(b)
    stem = (len(sa & sb) / len(sa | sb)) if sa and sb else 0.0
    return max(lex, stem)


def content_affinity(a, b) -> float:
    """Claim-text overlap only (no mention floor)."""
    ta, tb = _content_tokens(a), _content_tokens(b)
    rare = {t for t in (ta & tb) if len(t) >= 8}
    rare_boost = 0.22 if rare else 0.0
    return max(_text_overlap(a, b), rare_boost)


def _grounded_mention_names(atom) -> set[str]:
    """Names attested in the claim text, or filling an anaphor on this atom."""
    return {
        n
        for n in _mention_names(atom)
        if mention_attested_score(n, atom) >= MENTION_GROUND_MIN
    }


# Shared grounded names link two surfaces. They are not paraphrases.
# Must stay below search.redundancy_map high_consistency (0.85):
#   pool edge = min(0.95, 0.4 + 0.7 * 0.62) = 0.834
MENTION_JOIN_AFFINITY = 0.62


def cross_affinity(a, b) -> float:
    """Lexical/stem overlap, plus a capped join for grounded shared names.

    A shared attested name is a join of fixed strength (not 1.0).
    Claim-text overlap can still be 1.0 when the sentences themselves match.
    """
    mention = MENTION_JOIN_AFFINITY if (
        _grounded_mention_names(a) & _grounded_mention_names(b)
    ) else 0.0
    return max(content_affinity(a, b), mention)


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


_PROMPTS = {
    "tension": "These claims conflict — does this atom still hold?",
    "support": "Does this atom still hold given the other side?",
    "join": (
        "Shared name, different facts — not a conflict. "
        "Does this atom still stand alone?"
    ),
    "garbage": (
        "Shared mention is not attested in both claims "
        f"(grounding < {MENTION_GROUND_MIN}) — drop the unearned join"
    ),
    "none": (
        "No counterpart on the other surface — "
        "is this still true without them?"
    ),
}


def _challenge_rec(
    *,
    src,
    store_index,
    text,
    other_src,
    other=None,
    other_store_index=None,
    affinity=0.0,
    kind="none",
    grounding=0.0,
    shared=None,
    n_other=None,
) -> dict:
    rec = {
        "source": src,
        "store_index": store_index,
        "text": text,
        "other_source": other_src,
        "other": other,
        "other_store_index": other_store_index,
        "affinity": round(float(affinity), 3),
        "grounding": round(float(grounding), 3),
        "kind": kind,
        "tension": kind == "tension",
        "prompt": _PROMPTS[kind],
    }
    if shared:
        rec["shared"] = list(shared)
    if n_other is not None:
        rec["n_other"] = int(n_other)
    return rec


def overlap_challenges(
    provenance: Sequence[dict],
    my_store: dict,
    their_store: dict,
    *,
    min_sim: float = 0.18,
    max_support: int = 4,
) -> List[dict]:
    """Belief-challenges for each selected atom against the other full surface.

    Every polarity conflict is emitted (none are dropped). Content-overlap
    support is capped. Mention-only counterparts collapse to one ``join``
    per atom (a shared paper is not a cartesian of belief checks). The
    clone of an atom at the same store index is skipped so a topic can
    audit itself.
    """
    out: List[dict] = []
    for p in provenance:
        text = as_text(p.get("text"))
        src = p.get("source")
        store_index = p.get("store_index")
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
        self_atom = _atom_at(self_store, store_index) or text
        tensions: List[dict] = []
        supports: List[dict] = []
        joins: List[dict] = []
        garbage: List[dict] = []
        for j, o in enumerate(others):
            if not is_active(o) or not as_text(o).strip():
                continue
            other_text = as_text(o)
            if other_text.strip() == text.strip() and j == store_index:
                continue
            s = cross_affinity(self_atom, o)
            if s < min_sim:
                continue
            g = join_grounding(self_atom, o)
            # Rare-token boost (long shared names) is alignment, not support.
            text_hit = _text_overlap(self_atom, o) >= min_sim
            if claims_tension(self_atom, o):
                kind = "tension"
            elif text_hit:
                kind = "support"
            elif g >= MENTION_GROUND_MIN:
                kind = "join"
            else:
                kind = "garbage"
            rec = _challenge_rec(
                src=src,
                store_index=store_index,
                text=text,
                other_src=other_src,
                other=other_text,
                other_store_index=j,
                affinity=s,
                kind=kind,
                grounding=g,
                shared=(
                    _canonical_join_names(
                        _grounded_mention_names(self_atom)
                        & _grounded_mention_names(o)
                    )
                    if kind == "join"
                    else None
                ),
            )
            if kind == "tension":
                tensions.append(rec)
            elif kind == "support":
                supports.append(rec)
            elif kind == "join":
                joins.append(rec)
            else:
                garbage.append(rec)
        tensions.sort(key=lambda r: -r["affinity"])
        garbage.sort(key=lambda r: -r["affinity"])
        supports.sort(key=lambda r: -r["affinity"])
        join_hit: List[dict] = []
        if joins:
            joins.sort(key=lambda r: -r["affinity"])
            seen: set[str] = set()
            shared: List[str] = []
            for r in joins:
                for n in r.get("shared") or []:
                    if n not in seen:
                        seen.add(n)
                        shared.append(n)
            top = joins[0]
            top["shared"] = _canonical_join_names(shared)
            top["n_other"] = len(joins)
            join_hit = [top]
        hits = tensions + garbage + supports[: max(0, max_support)] + join_hit
        if hits:
            out.extend(hits)
        else:
            out.append(
                _challenge_rec(
                    src=src,
                    store_index=store_index,
                    text=text,
                    other_src=other_src,
                    kind="none",
                )
            )
    return out


def compare_overlap(old: dict, new: dict) -> dict:
    """Diff two overlap packets after a reconstruct step."""
    def _texts(doc: dict) -> list[str]:
        return [as_text(a) for a in doc.get("atoms") or []]

    before, after = _texts(old), _texts(new)
    old_set, new_set = set(before), set(after)
    n_ten = lambda d: sum(
        1
        for c in d.get("challenges") or []
        if c.get("tension") or c.get("kind") == "tension"
    )
    return {
        "kept": [t for t in after if t in old_set],
        "dropped": [t for t in before if t not in new_set],
        "added": [t for t in after if t not in old_set],
        "fixed_point": before == after,
        "tension_before": n_ten(old),
        "tension_after": n_ten(new),
        "size_before": len(before),
        "size_after": len(after),
    }


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
        src = p.get("source")
        store = (
            my_store
            if src == "mine"
            else their_store
            if src == "theirs"
            else {}
        )
        raw = _atom_at(store, p.get("store_index"))
        selected.append(traveling_atom(raw if raw is not None else p.get("text") or pool[i]))
        indices.append(int(p.get("index", i)))
        prov_sel.append(p)
    return _doc(selected, eng, indices, prov_sel)


def _constraint_of(atom) -> str:
    if isinstance(atom, dict):
        c = str(atom.get("constraint") or "").strip().lower()
        if c in VALID_CONSTRAINT:
            return c
    return ""


def union_dataset(my_store: dict, their_store: dict, *, min_sim: float = 0.18) -> dict:
    """Full ∪ of two stores — no greedy cut. Fast-path lookup dataset."""
    mine_raw, _, mine_orig = _active_view(my_store)
    theirs_raw, _, theirs_orig = _active_view(their_store)
    atoms: List[dict] = []
    provenance: List[dict] = []
    for i, a in enumerate(mine_raw):
        atoms.append(traveling_atom(a))
        provenance.append(
            {
                "index": i,
                "source": "mine",
                "text": as_text(a),
                "store_index": mine_orig[i],
            }
        )
    n_mine = len(mine_raw)
    for j, b in enumerate(theirs_raw):
        atoms.append(traveling_atom(b))
        provenance.append(
            {
                "index": n_mine + j,
                "source": "theirs",
                "text": as_text(b),
                "store_index": theirs_orig[j],
            }
        )
    return {
        "version": 1,
        "kind": "interest_union",
        "method": "union_dataset",
        "atoms": atoms,
        "provenance": provenance,
        "challenges": overlap_challenges(
            provenance, my_store, their_store, min_sim=min_sim
        ),
        "n_mine": n_mine,
        "n_theirs": len(theirs_raw),
        "require_cross": False,
        "max_size": len(atoms),
        "atom_count_source": len(atoms),
    }


def polarity_pairs(
    atoms: Sequence,
    *,
    min_sim: float = 0.18,
    max_pairs: int = 8,
) -> List[dict]:
    """Interesting possible × impossible combinations (shared join or tension)."""
    poss = [(i, a) for i, a in enumerate(atoms) if _constraint_of(a) == "possibility"]
    imp = [(i, a) for i, a in enumerate(atoms) if _constraint_of(a) == "impossibility"]
    out: List[dict] = []
    for i, a in poss:
        for j, b in imp:
            s = cross_affinity(a, b)
            tense = claims_tension(a, b)
            if s < min_sim and not tense:
                continue
            shared = _canonical_join_names(
                _grounded_mention_names(a) & _grounded_mention_names(b)
            )
            out.append(
                {
                    "possible_index": i,
                    "impossible_index": j,
                    "possible": traveling_atom(a),
                    "impossible": traveling_atom(b),
                    "affinity": round(float(s), 3),
                    "tension": bool(tense),
                    "shared": shared,
                }
            )
    out.sort(key=lambda r: (-int(r["tension"]), -r["affinity"]))
    return out[: max(0, max_pairs)]


def question_atoms(
    atoms: Sequence,
    challenges: Sequence[dict] | None = None,
) -> List[dict]:
    """Atoms that still need evaluation: pending, tension, possibility, impossibility."""
    tension_texts = {
        as_text(c.get("text"))
        for c in (challenges or [])
        if c.get("tension") or c.get("kind") == "tension"
    }
    out: List[dict] = []
    for i, a in enumerate(atoms):
        why: List[str] = []
        st = atom_review_status(a)
        if st in {REVIEW_PENDING, REVIEW_EDITED}:
            why.append("pending" if st == REVIEW_PENDING else "edited")
        if as_text(a) in tension_texts:
            why.append("tension")
        c = _constraint_of(a)
        if c == "possibility":
            why.append("possibility")
        elif c == "impossibility":
            why.append("impossibility")
        if not why:
            continue
        out.append(
            {
                "index": i,
                "atom": traveling_atom(a),
                "why": why,
                "constraint": c or None,
            }
        )
    return out


def overlap_lookup(
    doc: dict,
    query: str,
    *,
    max_hits: int = 6,
    min_sim: float = 0.18,
) -> dict:
    """Fast NL lookup over a union/overlap packet. Lexical only — no model.

    Hits are query-ranked. Polarity lists possible/impossible combinations.
    Question lists atoms still to evaluate (pending, tension, constructors).
    """
    atoms = list(doc.get("atoms") or [])
    q = (query or "").strip()
    scored: List[tuple] = []
    for i, a in enumerate(atoms):
        s = query_overlap(q, a) if q else 0.0
        scored.append((s, i, a))
    scored.sort(key=lambda t: (-t[0], t[1]))
    hits_raw = [t for t in scored if t[0] > 0][: max(0, max_hits)]
    hits = [
        {
            "index": i,
            "score": round(float(s), 3),
            "atom": traveling_atom(a),
            "constraint": _constraint_of(a) or None,
        }
        for s, i, a in hits_raw
    ]
    polar = polarity_pairs(atoms, min_sim=min_sim)
    if q and polar and hits:
        hit_idx = {h["index"] for h in hits}
        hit_names: set[str] = set()
        for h in hits:
            hit_names |= _grounded_mention_names(h["atom"])
        related = [
            p
            for p in polar
            if p["possible_index"] in hit_idx
            or p["impossible_index"] in hit_idx
            or (hit_names & set(p.get("shared") or []))
        ]
        if related:
            polar = related
    quest = question_atoms(atoms, doc.get("challenges") or [])
    if q and quest and hits:
        hit_idx = {h["index"] for h in hits}
        related_q = [r for r in quest if r["index"] in hit_idx]
        # keep constructor/pending even if they missed the query tokens
        extra = [
            r
            for r in quest
            if r["index"] not in hit_idx
            and any(w in r["why"] for w in ("pending", "edited", "tension"))
        ]
        quest = related_q + extra
    return {
        "version": 1,
        "kind": "overlap_lookup",
        "query": q,
        "source_kind": doc.get("kind"),
        "hits": hits,
        "polarity": polar,
        "question": quest,
        "n_union": len(atoms),
        "n_hits": len(hits),
    }
