"""Eval: how well does the resilient packet answer arbitrary queries?

For each query:
  1. Load packet (or rebuild greedy from accepted atoms)
  2. Ask local MLX to answer *only* from the packet
  3. Ask the same model to judge groundedness / coverage (0–1)
  4. Lexical overlap score as a cheap secondary signal

Output: eval report JSON + human table. This is the review loop for
"do our atoms actually help on questions people ask?"
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import mlx_backend
from .atoms import atom_text, atom_texts, is_active, query_overlap
from .consistency import parse_consistency
from .search import greedy_resilient


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _token_set(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def lexical_coverage(query: str, answer: str, packet: list[str]) -> float:
    """Fraction of contentful query tokens appearing in answer or packet."""
    q = {t for t in _token_set(query) if len(t) >= 4}
    if not q:
        return 0.0
    blob = _token_set(answer) | set().union(*(_token_set(p) for p in packet))
    return round(len(q & blob) / len(q), 3)


ANSWER_SYSTEM = """You answer using ONLY the provided knowledge packet.
If the packet does not contain enough to answer, say exactly: INSUFFICIENT_PACKET
Be concise (2–5 sentences). Do not invent facts outside the packet."""


JUDGE_SYSTEM = """You grade whether an answer is grounded in a knowledge packet.
Return ONLY JSON: {"grounded": 0.0-1.0, "coverage": 0.0-1.0, "notes": "short"}
- grounded: fraction of answer claims supported by the packet
- coverage: how much of the query the packet+answer addresses
If answer is INSUFFICIENT_PACKET, grounded=1.0 only if packet truly lacks the answer; else lower."""


def answer_from_packet(query: str, packet: list[str], *, model: str | None = None) -> dict:
    numbered = "\n".join(f"[{i}] {a}" for i, a in enumerate(packet))
    prompt = (
        f"PACKET:\n{numbered}\n\n"
        f"QUERY: {query}\n\n"
        f"Answer using only the packet."
    )
    out = mlx_backend.generate(
        prompt, system=ANSWER_SYSTEM, model=model, max_tokens=400, temp=0.1
    )
    return out


def judge_answer(
    query: str, packet: list[str], answer: str, *, model: str | None = None
) -> dict:
    numbered = "\n".join(f"[{i}] {a}" for i, a in enumerate(packet))
    prompt = (
        f"QUERY: {query}\n\nPACKET:\n{numbered}\n\nANSWER:\n{answer}\n\n"
        f"Grade groundedness and coverage."
    )
    out = mlx_backend.generate(
        prompt, system=JUDGE_SYSTEM, model=model, max_tokens=200, temp=0.0
    )
    raw = out["text"]
    if "</think>" in raw:
        raw = raw.split("</think>")[-1]
    start, end = raw.find("{"), raw.rfind("}")
    grade = {"grounded": None, "coverage": None, "notes": raw[:300], "raw": out["text"]}
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            grade["grounded"] = float(data.get("grounded"))
            grade["coverage"] = float(data.get("coverage"))
            grade["notes"] = str(data.get("notes") or "")[:400]
        except Exception:
            pass
    grade["model"] = out["model"]
    return grade


def _active_view(store: dict) -> tuple[list[str], dict]:
    full = store.get("atoms") or []
    active_idx = [i for i, a in enumerate(full) if is_active(a)]
    texts = [atom_text(full[i]) for i in active_idx]
    cons_full = parse_consistency(store)
    cons: dict = {}
    index_map = {old: new for new, old in enumerate(active_idx)}
    for (i, j), s in cons_full.items():
        if i in index_map and j in index_map:
            a, b = index_map[i], index_map[j]
            if a > b:
                a, b = b, a
            cons[(a, b)] = s
    return texts, cons


def resolve_packet(store: dict, *, max_size: int = 8) -> tuple[list[str], dict]:
    """Greedy packet from non-rejected atoms."""
    texts, cons = _active_view(store)
    if not texts:
        return [], {"method": "empty", "energy": 0.0}
    selected, energy = greedy_resilient(
        texts, cons, max_size=max_size, redundancy_scale=2.0
    )
    return list(selected), {
        "method": "greedy",
        "energy": float(energy),
        "max_size": max_size,
    }


def packet_for_query(
    store: dict,
    query: str,
    *,
    max_size: int = 8,
    seed_k: int = 3,
) -> tuple[list[str], dict]:
    """Query-aware packet: seed with top overlap atoms, then greedy-fill.

    Expectation: on-topic questions should see supporting atoms even when a
    global greedy packet dropped them for redundancy/coverage tradeoffs.
    """
    texts, cons = _active_view(store)
    if not texts:
        return [], {"method": "empty", "energy": 0.0, "query": query}
    ranked = sorted(
        range(len(texts)),
        key=lambda i: query_overlap(query, texts[i]),
        reverse=True,
    )
    seeds = []
    for i in ranked:
        if query_overlap(query, texts[i]) <= 0:
            break
        seeds.append(texts[i])
        if len(seeds) >= max(1, min(seed_k, max_size)):
            break
    # Greedy on full set, then union seeds (preserve order: seeds first)
    selected, energy = greedy_resilient(
        texts, cons, max_size=max_size, redundancy_scale=2.0
    )
    out: list[str] = []
    seen = set()
    for t in seeds + list(selected):
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_size:
            break
    return out, {
        "method": "query_seeded_greedy",
        "energy": float(energy),
        "max_size": max_size,
        "query": query,
        "seed_count": len(seeds),
        "seed_overlap": [round(query_overlap(query, t), 3) for t in seeds],
    }


def eval_queries(
    queries: list[str],
    store: dict,
    *,
    packet: list[str] | None = None,
    max_size: int = 8,
    model: str | None = None,
    query_aware: bool = True,
) -> dict[str, Any]:
    """Eval packet usefulness.

    Default ``query_aware=True`` builds a per-query seeded packet so we test
    whether the *store* can support the question — not only whether one global
    greedy packet happened to retain the right atom.
    Pass ``packet=`` (or ``query_aware=False``) to lock a fixed packet.
    """
    global_packet = packet
    global_meta = None
    if global_packet is not None:
        global_meta = {"method": "provided", "energy": None, "max_size": len(global_packet)}
    elif not query_aware:
        global_packet, global_meta = resolve_packet(store, max_size=max_size)

    rows = []
    for q in queries:
        q = q.strip()
        if not q:
            continue
        if global_packet is not None:
            pkt, meta = global_packet, global_meta or {}
        else:
            pkt, meta = packet_for_query(store, q, max_size=max_size)
        ans = answer_from_packet(q, pkt, model=model)
        answer_text = (ans.get("text") or "").strip()
        if "</think>" in answer_text:
            answer_text = answer_text.split("</think>")[-1].strip()
        grade = judge_answer(q, pkt, answer_text, model=model)
        lex = lexical_coverage(q, answer_text, pkt)
        insuff = "INSUFFICIENT_PACKET" in answer_text.upper()
        rows.append(
            {
                "query": q,
                "answer": answer_text,
                "insufficient": insuff,
                "grounded": grade.get("grounded"),
                "coverage": grade.get("coverage"),
                "lexical_coverage": lex,
                "judge_notes": grade.get("notes"),
                "model": ans.get("model"),
                "packet": pkt,
                "packet_meta": meta,
            }
        )

    def avg(key):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {
        "version": 1,
        "kind": "packet_query_eval",
        "created": _now(),
        "model": model or mlx_backend.model_id(),
        "query_aware": query_aware and global_packet is None,
        "packet": global_packet,
        "packet_meta": global_meta,
        "n_queries": len(rows),
        "mean_grounded": avg("grounded"),
        "mean_coverage": avg("coverage"),
        "mean_lexical": avg("lexical_coverage"),
        "n_insufficient": sum(1 for r in rows if r["insufficient"]),
        "results": rows,
    }


def load_queries(path: Path | None, inline: list[str] | None) -> list[str]:
    qs = list(inline or [])
    if path:
        text = Path(path).expanduser().read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip().lstrip("-•").strip()
            if line and not line.startswith("#"):
                qs.append(line)
    return qs
