#!/usr/bin/env python3
"""Live mint+self-eval probe for constructor-resilience models.

Does not load 27B. Writes a JSON report. Optional --models.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from coherence_cache.atoms import atom_text
from coherence_cache.eval_queries import (
    answer_from_packet,
    judge_answer,
    lexical_coverage,
)
from coherence_cache.mint import mint_from_text_retry
from coherence_cache.mlx_backend import ensure_model

FIXTURE = """
Constructor-resilience packs durable claims (atoms) into a small resume packet.
The share unit is the packet, not the transcript. Mentions are joins on a claim,
not a second graph. Pack does not require a mint model — the packing agent
extracts names. Optional MLX mint defaults to Qwen3-8B-4bit on Apple Silicon.
A mention is garbage when it is not attested in the claim. Overlap of two
interest surfaces is intersection or union; a shared name is a join, not a paraphrase.
"""

QUERIES = [
    "What is the share unit?",
    "Does pack require a mint model?",
    "When is a mention garbage?",
]

DEFAULT_MODELS = [
    "mlx-community/Qwen3-8B-4bit",
    "mlx-community/Qwen3-4B-4bit",
    "mlx-community/Qwen3-1.7B-4bit",
    "mlx-community/Llama-3.2-1B-Instruct-4bit",
]


def probe_one(model: str) -> dict:
    t0 = time.perf_counter()
    ensure_model(model)
    load_s = round(time.perf_counter() - t0, 2)
    t1 = time.perf_counter()
    mint = mint_from_text_retry(FIXTURE, model=model, theme="constructor-resilience")
    mint_s = round(time.perf_counter() - t1, 2)
    texts = [atom_text(a) for a in mint.get("atoms") or []]
    evals = []
    for q in QUERIES:
        ans = answer_from_packet(q, texts, model=model)
        grade = judge_answer(q, texts, ans["text"], model=model)
        evals.append(
            {
                "query": q,
                "answer": (ans["text"] or "")[:400],
                "lex": lexical_coverage(q, ans["text"], texts),
                "grounded": grade.get("grounded"),
                "coverage": grade.get("coverage"),
                "notes": grade.get("notes"),
            }
        )
    mint_ok = bool((mint.get("score") or {}).get("ok"))
    packet_hits = sum(1 for ev in evals if (ev.get("grounded") or 0) >= 0.7)
    packet_ok = packet_hits >= len(QUERIES)
    return {
        "model": model,
        "load_s": load_s,
        "mint_s": mint_s,
        "attempt": mint.get("attempt"),
        "score": mint.get("score"),
        "n_atoms": len(texts),
        "atoms": texts,
        "dropped": mint.get("dropped"),
        "eval": evals,
        "mint_ok": mint_ok,
        "packet_ok": packet_ok,
        "packet_hits": packet_hits,
        "ok": mint_ok and packet_ok,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    ap.add_argument("--out", default="/tmp/constructor-model-probe.json")
    args = ap.parse_args()
    rows = []
    for mid in args.models:
        print(f"\n==== {mid} ====", flush=True)
        try:
            rec = probe_one(mid)
        except Exception as e:
            rec = {"model": mid, "ok": False, "error": str(e)}
            print("ERROR", e)
        rows.append(rec)
        sc = rec.get("score") or {}
        print(
            f"  load={rec.get('load_s')}s mint={rec.get('mint_s')}s "
            f"attempt={rec.get('attempt')} mint_ok={rec.get('mint_ok')} "
            f"packet={rec.get('packet_hits')}/{len(QUERIES)} "
            f"packet_ok={rec.get('packet_ok')} ok={rec.get('ok')} "
            f"atoms={rec.get('n_atoms')} dropped={len(rec.get('dropped') or [])} "
            f"reasons={sc.get('reasons')}",
            flush=True,
        )
        for a in rec.get("atoms") or []:
            print("   -", a[:110], flush=True)
        for ev in rec.get("eval") or []:
            print(
                f"   Q {ev['query'][:50]} lex={ev['lex']} g={ev['grounded']} c={ev['coverage']}",
                flush=True,
            )
    Path(args.out).write_text(json.dumps(rows, indent=2))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
