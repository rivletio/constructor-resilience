---
name: constructor-resilience
description: Agent coherence-cache and interest packets. Compress durable claims into topical atoms; build resilient packets; intersect interest surfaces for handoff and multi-session continuity. Use when caching research, sharing intentional context (not whole vaults), browsing interest overlap, or preparing packets for Ikonic/other hosts.
---

# Constructor Resilience (Grok skill)

Thin client of the open **`constructor-resilience`** package.

**Product framing:** share *interest surfaces*, not everything. Resume from *packets*. Intersect surfaces to browse mutual curiosity. Ikonic is the full-stack host; this skill is the agent-side cache and handoff tool.

## Setup

```bash
pip install -e /path/to/constructor-resilience
export COHERENCE_ROOT="${COHERENCE_ROOT:-$PWD/.coherence}"
# Optional: Ikonic vault
# export COHERENCE_ROOT="$HOME/.ikonic/vault/coherence"
```

CLI entry: `coherence` (alias `knowledge_ops`).

## Protocol

### Session start
1. `coherence cache "theme or question"` or `coherence use <topic-id>`
2. Load **packet** as privileged context before new research
3. Continue; only durable net-new claims become atoms

### During work
1. `coherence add-atom "…"` (+ judgment scores when possible)
2. `coherence search --greedy --max-size 6` to refresh packet
3. Link related topics: `coherence link a b`

### Interest intersection (browse)
```bash
coherence intersect my-surface their-public --query "consciousness" --max-size 8
```

### Handoff
Share `topics/<id>/atoms.json` + `packet.json` — not the chat transcript.

## Circles (always)
- **Inner personal** claims stay out of public topics unless intentional promote  
- Intersection only uses surfaces each party chose to expose  

## Docs
Upstream: package `SPEC.md`, `docs/HOSTS.md`, `docs/USER_MANUAL.md`
