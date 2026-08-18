# Ikonic host — where constructor-resilience shines

Ikonic is the **flagship host**: personal computer for intentional interest geometry from **public** through **circles** to **inner secure**.

## Mission alignment

| Layer | What lives there | Share unit |
|-------|------------------|------------|
| Public / classical web | Creator atom feeds, projections to RSS/URL | Published `atoms.json` / packet |
| Circles | Friends & collab interest surfaces | Intersection packets |
| Inner personal | Lifelog, mail, private memory | **Never ambient** — only intentional promote |

**Product law:** I do not share everything. I share what I am interested in. I browse the **intersection** of my surface with yours (or Lex’s public atoms) and reshape that overlap in realtime.

## Vault layout (proposed)

```text
$VAULT_ROOT/
  coherence/                 # COHERENCE_ROOT for this vault
    meta.json
    active.json
    topics/
      my-ai-interests/
        atoms.json
        packet.json
      following/
        lex-public/          # imported or mirrored public surface
          atoms.json
```

Env when running tools against a vault:

```bash
export COHERENCE_ROOT="$VAULT_ROOT/coherence"
coherence list
coherence intersect my-ai-interests following-lex-public --query consciousness
```

## First-run (seed a mind)

1. Optional: import a demo or creator packet instead of empty feed hell.  
2. Or: create first interest topic from one question + a few atoms.  
3. Success metric: user can ask voice *one* packet-grounded question and get a non-empty answer **without** residual LLM if FREE/about hits packet.

See also Ikonic strategy: personal-circle intentional copy (same law as promote-to-surface).

## Product surfaces

| Surface | Behavior |
|---------|----------|
| **Interest Home / Overlap** | Live intersect dials (topics, seed query, max size) |
| **Follow creator** | Subscribe to public `atoms.json` like a feed |
| **Voice** | “Show where my interests meet Lex on X” → intersect packet → speak + open cited URL if any |
| **Explore** | Atoms as graph nodes; packet as current lens |
| **Share** | Export packet only to circle or public |

## Adapter sketch (future code in ikonic monorepo)

```text
subsystems/coherence/   # or vault helpers under core/storage
  - resolve COHERENCE_ROOT = vault/coherence
  - import_public_surface(url|path) -> topic
  - intersect_api(mine, theirs, seed) -> packet JSON
  - residual/FREE inject: active packet atoms into context
```

Python dependency: `constructor-resilience` (this package) for search + intersect; Rust may later reimplement the energy model for native FREE.

## Voice / text inference fast path

Scorecard + phased plan: **[VOICE_FAST_PATH_EVAL.md](./VOICE_FAST_PATH_EVAL.md)**.

**Short version:** packets are **Knowledge FREE** (mid-ladder), not verb FREE. Mint/critique stay offline; turn path is packet lookup → speak or fall through → residual grounded with packet leftovers.

## Classical web compatibility

- Atom text may include URLs (episodes, papers).  
- Publish path: packet → markdown / RSS items.  
- Subscribe path: fetch remote `atoms.json` → local following topic.  

New share primitive; old web as optional projection.
