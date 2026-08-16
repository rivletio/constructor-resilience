#!/usr/bin/env python3
"""
Consistency scoring helpers for constructor-resilience.

Provides:
  - lexical heuristic (fast, weak)
  - pair enumeration for LLM-as-judge / human scoring
  - apply scored pairs back into a store
  - score-new-atom against existing set

Scores are in [-1, 1]:
  +1 strong mutual support
   0 neutral / unrelated
  -1 direct conflict
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

Pair = Tuple[int, int]
ScoreMap = Dict[Pair, float]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_store(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_store(path: Path, store: dict) -> None:
    store["updated"] = now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)
        f.write("\n")


def parse_consistency(store: dict) -> ScoreMap:
    out: ScoreMap = {}
    for key, score in (store.get("consistency") or {}).items():
        try:
            if isinstance(key, str) and "," in key:
                i, j = map(int, key.split(","))
            else:
                continue
            a, b = (i, j) if i < j else (j, i)
            out[(a, b)] = float(score)
        except Exception:
            continue
    return out


def dump_consistency(cons: ScoreMap) -> dict:
    return {f"{i},{j}": round(float(s), 4) for (i, j), s in sorted(cons.items())}


def token_set(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def heuristic_pair_score(a: str, b: str) -> float:
    """Lexical Jaccard-based score in ~[0, 0.85]. Never strongly negative."""
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    jacc = inter / union if union else 0.0
    return round(min(0.85, max(0.0, jacc * 1.25 - 0.05)), 4)


def norm_pair(i: int, j: int) -> Pair:
    return (i, j) if i < j else (j, i)


def pairs_for_new_atom(n_existing: int, new_idx: int) -> List[Pair]:
    return [norm_pair(i, new_idx) for i in range(n_existing)]


def all_pairs(n: int) -> List[Pair]:
    return [(i, j) for i in range(n) for j in range(i + 1, n)]


def apply_scores(store: dict, scores: ScoreMap, min_abs: float = 0.0) -> int:
    cons = parse_consistency(store)
    written = 0
    for (i, j), s in scores.items():
        if abs(s) < min_abs:
            # remove near-zero edges to keep graph sparse
            cons.pop(norm_pair(i, j), None)
            continue
        cons[norm_pair(i, j)] = float(s)
        written += 1
    store["consistency"] = dump_consistency(cons)
    return written


def heuristic_score_new(store: dict, min_abs: float = 0.05) -> ScoreMap:
    atoms = store.get("atoms", [])
    if len(atoms) < 2:
        return {}
    new_idx = len(atoms) - 1
    scores: ScoreMap = {}
    for i in range(new_idx):
        s = heuristic_pair_score(atoms[i], atoms[new_idx])
        if abs(s) >= min_abs:
            scores[(i, new_idx)] = s
    return scores


def heuristic_rescore_all(store: dict, min_abs: float = 0.05) -> ScoreMap:
    atoms = store.get("atoms", [])
    scores: ScoreMap = {}
    for i, j in all_pairs(len(atoms)):
        s = heuristic_pair_score(atoms[i], atoms[j])
        if abs(s) >= min_abs:
            scores[(i, j)] = s
    return scores


# --- LLM-as-judge prompt material (for the agent, not auto-executed) ---

JUDGE_RUBRIC = """
Score pairwise consistency of two knowledge atoms for a coherence cache.

Score in [-1.0, 1.0]:
  1.0  mutually supporting; one strengthens the other
  0.5  related and compatible, mild support
  0.0  unrelated or orthogonal for this topic
 -0.5  tension; hard to hold both without qualification
 -1.0  direct contradiction

Rules:
- Judge only on the text given, within the active topic.
- Prefer sparse graphs: use 0.0 when the link is weak or incidental.
- Do not reward mere shared keywords if the claims are about different points.
""".strip()


def format_judge_batch(
    atoms: Sequence[str],
    pairs: Sequence[Pair],
    max_pairs: int = 30,
) -> str:
    """Produce a prompt block the agent can answer with JSON scores."""
    lines = [JUDGE_RUBRIC, "", "Atoms:", ""]
    indices = sorted({i for p in pairs[:max_pairs] for i in p})
    for i in indices:
        if 0 <= i < len(atoms):
            lines.append(f"[{i}] {atoms[i]}")
    lines.append("")
    lines.append("Score these pairs. Reply with JSON only:")
    lines.append('{ "scores": [ {"i": 0, "j": 1, "score": 0.7}, ... ] }')
    lines.append("")
    for i, j in pairs[:max_pairs]:
        lines.append(f"- ({i},{j})")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Consistency scoring utilities")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("heuristic-new", help="Heuristic-score newest atom vs prior")
    p_new.add_argument("--store", type=Path, required=True)
    p_new.add_argument("--min-abs", type=float, default=0.05)
    p_new.add_argument("--apply", action="store_true")

    p_all = sub.add_parser("heuristic-all", help="Heuristic rescore all pairs")
    p_all.add_argument("--store", type=Path, required=True)
    p_all.add_argument("--min-abs", type=float, default=0.05)
    p_all.add_argument("--apply", action="store_true")

    p_prompt = sub.add_parser("judge-prompt", help="Emit LLM-as-judge prompt for pairs")
    p_prompt.add_argument("--store", type=Path, required=True)
    p_prompt.add_argument("--new-only", action="store_true", help="Only pairs involving newest atom")
    p_prompt.add_argument("--max-pairs", type=int, default=30)

    p_apply = sub.add_parser("apply-json", help="Apply scores JSON file to store")
    p_apply.add_argument("--store", type=Path, required=True)
    p_apply.add_argument("--scores", type=Path, required=True, help="JSON with scores: [{i,j,score}]")
    p_apply.add_argument("--min-abs", type=float, default=0.0)

    args = parser.parse_args()
    store = load_store(args.store)
    atoms = store.get("atoms", [])

    if args.cmd == "heuristic-new":
        scores = heuristic_score_new(store, min_abs=args.min_abs)
        for (i, j), s in sorted(scores.items()):
            print(f"{i},{j}\t{s:+.3f}")
        if args.apply:
            n = apply_scores(store, scores, min_abs=args.min_abs)
            save_store(args.store, store)
            print(f"applied {n} edges")

    elif args.cmd == "heuristic-all":
        scores = heuristic_rescore_all(store, min_abs=args.min_abs)
        print(f"pairs={len(scores)}")
        if args.apply:
            # replace consistency
            store["consistency"] = dump_consistency(scores)
            save_store(args.store, store)
            print("store updated")

    elif args.cmd == "judge-prompt":
        if args.new_only:
            if len(atoms) < 2:
                raise SystemExit("need at least 2 atoms")
            pairs = pairs_for_new_atom(len(atoms) - 1, len(atoms) - 1)
        else:
            pairs = all_pairs(len(atoms))
        print(format_judge_batch(atoms, pairs, max_pairs=args.max_pairs))

    elif args.cmd == "apply-json":
        payload = json.loads(args.scores.read_text())
        items = payload.get("scores", payload if isinstance(payload, list) else [])
        scores: ScoreMap = {}
        for item in items:
            i, j, s = int(item["i"]), int(item["j"]), float(item["score"])
            scores[norm_pair(i, j)] = s
        n = apply_scores(store, scores, min_abs=args.min_abs)
        save_store(args.store, store)
        print(f"applied {n} edges → {args.store}")


if __name__ == "__main__":
    main()
