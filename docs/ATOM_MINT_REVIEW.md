# Atom mint, review, and query eval

## Why HOW matters

Atoms are not notes. They become **privileged context** for future agents.
So every minted claim must answer:

1. **What** is the claim?  
2. **How** was it produced? (model, method, source excerpt)  
3. **Has a reviewer accepted it?**  

Unreviewed mint output is `pending`. Rejected claims stay on disk for audit
but leave packets and search.

## Pipeline

```
source text/file
    │  coherence mint  (MLX Qwen3-8B-4bit by default)
    ▼
atoms.json  [status=pending, provenance=…]
    │  coherence review --serve
    ▼
accepted / edited / rejected
    │  coherence search --greedy
    ▼
packet.json
    │  coherence eval --query …
    ▼
eval_report.json  (grounded + coverage on arbitrary questions)
```

## Model

| Env | Default |
|-----|---------|
| `COHERENCE_MLX_MODEL` | `mlx-community/Qwen3-8B-4bit` |

```bash
coherence ensure-model
```

## Quality law (mint prompt)

Only durable claims. No filler, no ambient UI state, no near-duplicates.
Prefer claims that can support or conflict with other claims.

## Grounding gate (anti-invention)

After MLX mint, claims that fail `is_grounded(claim, source)` are **dropped**
before they enter `atoms.json` (logged as `dropped (…) ungrounded`).

Tune with `--min-grounding` (default `0.55`). Near-quotes always pass.

## Eval interpretation

Default mode is **query-aware**: each query gets a seeded packet (top overlap
atoms ∪ greedy fill). That tests whether the *store* can support the question.

| Signal | Meaning |
|--------|---------|
| `INSUFFICIENT_PACKET` | Honest miss — store/packet lacks the answer |
| high `grounded` | Answer stayed inside the packet |
| high `coverage` | Query was addressed |
| Mars-style control query | Should be insufficient if store is on-topic |

Use `--fixed-packet` to lock one global greedy/saved packet (stresses
packet selection, not store coverage).

**Expected on a well-minted topical store:** on-topic queries ✓, off-topic ∅.

If on-topic queries are insufficient: mint missed the claim, review rejected
it, or (fixed mode) greedy packet dropped it — all are reviewable.
