# Vault host

A **vault-style host** is a personal computer for intentional interest geometry
from **public** through **circles** to **inner secure**. This package stays
host-agnostic; the vault is one compatible layout.

## Mission alignment

| Layer | What lives there | Share unit |
|-------|------------------|------------|
| Public / classical web | Creator atom feeds, projections to RSS/URL | Published `atoms.json` / packet |
| Circles | Friends & collab interest surfaces | Intersection packets |
| Inner personal | Lifelog, mail, private memory | **Never ambient** — only intentional promote |

**Product law:** I do not share everything. I share what I am interested in. I browse the **intersection** of my surface with yours (or a public creator’s atoms) and reshape that overlap in realtime.

## Vault layout

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
  feeds/inbox_items/         # optional: local copies of cited URLs (ensure)
```

Env when running tools against a vault:

```bash
export COHERENCE_ROOT="$VAULT_ROOT/coherence"
coherence list
coherence intersect my-ai-interests following-lex-public --query consciousness
```

## First-run (seed a mind)

1. Optional: import a demo or creator packet instead of an empty store.
2. Or: create a first interest topic from one question + a few atoms.
3. Success metric: one packet-grounded question gets a non-empty answer **without** residual generation if the packet covers it.

## Product surfaces

| Surface | Behavior |
|---------|----------|
| **Interest Home / Overlap** | Live intersect dials (topics, seed query, max size) |
| **Follow creator** | Subscribe to public `atoms.json` like a feed |
| **Voice** | Overlap query → intersect packet → speak + open cited URL if any |
| **Explore** | Atoms as graph nodes; packet as current lens |
| **Share** | Export packet only to circle or public |

## Adapter sketch

```text
host coherence helpers
  - resolve COHERENCE_ROOT = {VAULT_ROOT}/coherence
  - import_public_surface(url|path) -> topic
  - intersect_api(mine, theirs, seed) -> packet JSON
  - inject active packet atoms as privileged context
  - optional ensure: POST {api}/api/voice/dispatch  {"text":"open <url>","execute":true}
```

Python dependency: `constructor-resilience` (this package) for search + intersect. A native host may later reimplement the energy model.

## Classical web compatibility

- Atom text may include URLs (episodes, papers).
- Publish path: packet → markdown / RSS items.
- Subscribe path: fetch remote `atoms.json` → local following topic.

New share primitive; old web as optional projection.
