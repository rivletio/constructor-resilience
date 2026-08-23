# constructor-resilience

**Open method for what we share.**  
Compress durable knowledge into **atoms** and **resilient packets**. Browse **interest intersections** — without dumping whole vaults or lives.

Compatible with the classical web (URLs, markdown, RSS projections).

> We are reinventing *what* we share — a new share primitive with optional bridges to the old internet.

## Core ideas

| Concept | Meaning |
|---------|---------|
| **Atom** | A durable claim worth carrying forward |
| **Consistency** | Support / conflict edges between atoms ∈ [-1, 1] |
| **Packet** | Small set maximizing coverage + support − redundancy |
| **Interest surface** | Topics you *choose* to show (not everything you know) |
| **Intersection** | Live overlap of two surfaces — browse with dials |

**Use case:** You don’t share everything. You share what you’re interested in.  
You browse the **intersection** of your surface with a friend’s — or a public creator’s published atoms (e.g. Lex Fridman-style public atom feed) — and reshape that overlap in realtime.

## Install

```bash
cd constructor-resilience
pip install -e ".[dev]"
# optional graph PNG:
pip install -e ".[viz]"
```

## Quick start

```bash
export COHERENCE_ROOT=./.coherence   # or pass --root
coherence status                     # creates empty meta-store on first run
coherence create --title "My AI interests" --use
coherence add-atom "I care about world models and non-generative prediction." --auto-score --accepted
coherence add-atom "JEPA predicts in latent space rather than tokens." --auto-score --accepted
coherence search --greedy --max-size 6
coherence packet
```

### Mint → review → eval (local MLX)

Default model: **`mlx-community/Qwen3-8B-4bit`** (Qwen3 8B on Apple Silicon).

```bash
# one-time download / warm
coherence ensure-model

# HOW we make atoms: local mint with provenance (status=pending)
coherence mint --file ./notes.md --theme "world models" --ensure-model --auto-score

# Pre-human critique (proposals; --apply auto-accept/reject on confidence+grounding)
coherence critique --source-file ./notes.md --apply

# Slick HTML reviewer — accept / edit / reject (shows critique chips)
coherence review --serve   # http://127.0.0.1:8765

# How well can the store answer arbitrary questions? (query-aware packets)
coherence eval \
  --query "What is JEPA?" \
  --query "How do we share interest without vault dumps?" \
  --ensure-model
# → topics/<id>/eval_report.json
# Expect: on-topic ✓, off-topic INSUFFICIENT. Use --fixed-packet to stress one global packet.
```

### Interest intersection

```bash
coherence create --title "My physics" --use
# ... add atoms ...
coherence create --title "Lex public"   # their published surface
# ... import or add their public atoms ...
coherence intersect my-physics lex-public --query consciousness --max-size 8
```

### Library API

```python
from coherence_cache.search import greedy_resilient
from coherence_cache.intersection import intersection_packet

selected, energy = greedy_resilient(atoms, consistency, max_size=6)
packet = intersection_packet(my_store, their_store, max_size=8, seed_query="AI")
```

## Layout

```
$COHERENCE_ROOT/
  meta.json
  active.json
  topics/<id>/atoms.json
  topics/<id>/packet.json
```

See [SPEC.md](./SPEC.md) for wire formats.  
See [docs/HOSTS.md](./docs/HOSTS.md) for adapters.  
See [docs/qubo-formulation.md](./docs/qubo-formulation.md) for the energy model.

## Hosts

| Host | Role |
|------|------|
| **CLI** | Reference |
| **Agent skill** | Claude, Grok, Codex, Cursor — [`rivletio/constructor-resilience-skill`](https://github.com/rivletio/constructor-resilience-skill) (`hosts/grok-skill/` is a pointer) |

## License

MIT — see [LICENSE](./LICENSE).
