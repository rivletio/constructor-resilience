---
name: constructor-resilience
description: >
  Agent coherence-cache: mint durable atoms with provenance, review them, build
  resilient packets, and eval packets on arbitrary queries. Use when caching
  research, handoff, interest intersection, atom review, minting claims, or
  measuring packet quality. Triggers on coherence cache, atoms, mint atoms,
  review atoms, packet eval, constructor resilience, interest intersection.
---

# Constructor Resilience (Grok skill)

Thin client of the open package at  
`/Users/danielgray/Work/Rivlet/products/constructor-resilience`.

**Product framing:** share *interest surfaces*, not everything. Resume from *packets*.  
**Atom law:** *how* we mint matters — every minted claim carries provenance and starts **pending review**.

## Setup

```bash
cd /Users/danielgray/Work/Rivlet/products/constructor-resilience
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,mlx]"
export COHERENCE_ROOT="${COHERENCE_ROOT:-$PWD/.coherence}"
# Optional Ikonic vault:
# export COHERENCE_ROOT="$HOME/.ikonic/vault/coherence"
export PATH="$PWD/.venv/bin:$PATH"
```

CLI: `coherence` (alias `knowledge_ops`).

Default local model: **`mlx-community/Qwen3-8B-4bit`** (Qwen3 8B MLX).  
Override: `COHERENCE_MLX_MODEL=…`

## Protocol

### Session start
1. `coherence cache "theme"` or `coherence use <topic-id>`
2. Load **packet** as privileged context
3. Continue; only durable net-new claims become atoms

### Mint (HOW we make atoms)
```bash
coherence ensure-model
coherence mint --file ./notes.md --theme "…" --auto-score
# atoms land as review.status=pending with model + source excerpt
```

### Critique (pre-human)
```bash
coherence critique --source-file ./notes.md --apply
```

### Review (slick UI)
```bash
coherence review --serve    # http://127.0.0.1:8765
```
Accept / edit / reject. Rejected atoms stay for audit but leave packets.

### Eval (arbitrary queries)
```bash
coherence eval \
  --query "What did we decide about X?" \
  --query "How does Y relate to Z?" \
  --ensure-model
# → eval_report.json (grounded + coverage scores)
```

### Packet / handoff
```bash
coherence search --greedy --max-size 6
coherence packet --rebuild
# Share topics/<id>/atoms.json + packet.json
```

## Circles
- Inner personal claims stay out of public topics unless intentional promote  
- Intersection only uses surfaces each party chose to expose  

## Docs
Upstream: `SPEC.md`, `docs/HOSTS.md`, `docs/USER_MANUAL.md`, `README.md`
