# Wire formats — constructor-resilience

Version **1**. Hosts MUST accept these shapes. Extra fields are allowed and ignored if unknown.

## Philosophy

We do not share **everything**. We share **interest surfaces** — intentional sets of durable claims (*atoms*) — and compute **intersections** so two people (or a person and a public figure) can browse overlap without dumping whole stores.

Classical web compatibility: an atom MAY cite a URL; hosts MAY project packets to markdown/RSS. The **source of truth for meaning** is the atom graph + packet, not the HTML page.

## Circles (policy, not format)

| Circle | What may leave |
|--------|----------------|
| **Inner personal** | Nothing ambient; only intentional promote → interest surface |
| **Circle / friends** | Shared interest surfaces + intersection packets |
| **Public** | Published atom feeds (e.g. creator like Lex Fridman) |

Formats are the same at every layer. **Hosts enforce policy.**

---

## `meta.json` (store root)

```json
{
  "version": 1,
  "description": "Meta-store for topical knowledge stores",
  "created": "2026-08-16T00:00:00Z",
  "updated": "2026-08-16T00:00:00Z",
  "topics": [
    {
      "id": "demo-interest",
      "title": "Demo interest surface",
      "path": "topics/demo-interest",
      "description": "…",
      "atom_count": 0,
      "edge_count": 0,
      "created": "…",
      "updated": "…",
      "tags": ["public", "interest"],
      "visibility": "public"
    }
  ],
  "links": [
    { "src": "topic-a", "dst": "topic-b", "score": 0.5, "relation": "related" }
  ]
}
```

Optional topic field **`visibility`**: `inner` | `circle` | `public` (host-interpreted).

---

## `topics/<id>/atoms.json`

```json
{
  "version": 1,
  "description": "…",
  "created": "…",
  "updated": "…",
  "atoms": [
    "Durable claim one.",
    {
      "text": "Durable claim two with optional https://example.com/ref",
      "constraint": "fact",
      "mentions": [{"name": "Example Corp", "kind": "org"}],
      "refs": [{"kind": "url", "id": "https://example.com/ref", "url": "https://example.com/ref"}],
      "provenance": {
        "method": "mlx_mint",
        "model": "mlx-community/Qwen3-8B-4bit",
        "source": "source_text",
        "source_excerpt": "…",
        "created": "2026-08-17T00:00:00Z",
        "prompt_sha256": "abc123"
      },
      "review": {
        "status": "pending",
        "reviewed_at": null,
        "notes": ""
      }
    }
  ],
  "consistency": {
    "0,1": 0.8,
    "0,2": -0.3
  }
}
```

| Field | Rule |
|-------|------|
| `atoms` | Ordered list of **strings or objects**; index is stable for edges |
| `atoms[].text` | When object: the claim string (search/packet use this) |
| `atoms[].constraint` | Optional constructor kind: `possibility` \| `impossibility` \| `fact` \| `decision` |
| `atoms[].mentions` | Optional joins: `[{name, kind}]` where kind is `concept` \| `person` \| `org` \| `work` \| `place` \| `other`. **Not** a second graph. |
| `atoms[].refs` | Optional citations: arXiv / DOI / URL / **youtube_video** (`youtube_video_id`, `t` seconds, `t_label`, `url` with `&t=`) |
| `atoms[].provenance` | **HOW it was made** — method, model, source, excerpt (required for mint) |
| `atoms[].review.status` | `pending` \| `accepted` \| `edited` \| `rejected` |
| `consistency` | Keys `"i,j"` with `i < j`; scores in **[-1, 1]** |
| Sparse edges | Omit near-zero; prefer judgment over pure keywords |

**Mentions law:** a mention is a *join* from a claim to a named thing. Hosts MAY project mentions into their own entity store. This format does not merge entities and atoms.

**Atom quality law:** only claims worth carrying forward — not ambient chat, not fixture junk.

**Review law:** minted atoms start `pending`. Rejected atoms stay for audit but are excluded from packets/search. Plain strings are treated as `accepted` (legacy).

**Back-out law:** if an atom was ill-defined, or later found not to create the possibility or impossibility it claimed, mark it `rejected` in place (`coherence reject INDEX --reason "…"`). Do not delete — indices stay stable. Optional fields on `review`: `backed_out` (bool), `previous_status`. Packet rebuild drops the atom automatically.

---

## `topics/<id>/packet.json` (resilient packet)

Output of `search` / `cache` / `packet --rebuild`.

```json
{
  "version": 1,
  "kind": "resilient_packet",
  "topic_id": "demo-interest",
  "created": "2026-08-16T19:16:44Z",
  "method": "greedy",
  "energy": -12.5,
  "max_size": 6,
  "redundancy_scale": 2.0,
  "query": null,
  "atom_indices": [0, 3, 5],
  "atoms": ["…ordered working set…"],
  "atom_count_source": 12
}
```

Energy model: coverage + support − redundancy (see `docs/qubo-formulation.md`).

---

## Interest intersection packet

Output of `intersect mine theirs` — **browse primitive**.

```json
{
  "version": 1,
  "kind": "interest_intersection",
  "method": "greedy",
  "energy": -8.1,
  "max_size": 8,
  "seed_query": "consciousness",
  "atoms": ["…"],
  "atom_indices": [0, 5, 7],
  "provenance": [
    { "index": 0, "source": "mine", "text": "…" },
    { "index": 5, "source": "theirs", "text": "…" }
  ],
  "n_mine": 10,
  "n_theirs": 14,
  "atom_count_source": 24
}
```

Hosts SHOULD re-run intersect when the user changes topic dials, seed query, or max size (**realtime browse**).

Cross-surface edges use lexical/stem overlap and shared mention names. Internal consistency is damped. If `require_cross` (default) and there are no cross-edges, the packet is empty — no filling from dense hubs on one side.

---

## `intentional_share` (share envelope)

Output of `coherence share`. Wraps a packet with audience + forward grants. Share is never ambient.

```json
{
  "version": 1,
  "kind": "intentional_share",
  "share_id": "…uuid…",
  "from": "local",
  "to": "alice",
  "audience": "circle",
  "forward": "none",
  "shared_at": "2026-08-23T00:00:00Z",
  "note": "",
  "topic_id": "demo-interest",
  "atoms": ["…packet texts…"],
  "mentions": [{"name": "JEPA", "kind": "concept"}],
  "content_refs": [{"kind": "url", "url": "https://…"}],
  "packet": { "atom_indices": [0, 3, 5], "method": "greedy" }
}
```

| Field | Rule |
|-------|------|
| `audience` | `direct` \| `circle` \| `public` |
| `forward` | `none` \| `circle` \| `public` — **never escalates** past audience |
| `atoms` | Packet texts (strings) |
| `mentions` / `content_refs` | Joins + citations copied from the packet |
| Import | `coherence import share.json` materializes a topic; claim text stays clean; grant metadata lives on `store.share` |

---

## `active.json` (optional session pointer)

```json
{
  "topic_id": "demo-interest",
  "path": "topics/demo-interest",
  "title": "Demo",
  "atoms_path": "/abs/path/to/atoms.json",
  "set_at": "…"
}
```

---

## Public creator feeds (classical web bridge)

A **published interest surface** is a topic (or zip of topics) with `visibility: public`. Hosts MAY:

- serve `atoms.json` / `packet.json` over HTTPS  
- mirror a packet into RSS as titles + atom text + extracted URLs  
- subscribe like a feed, then `intersect` with the local surface  

Example product line: *Lex Fridman publishes public atoms; you browse `my_ai ∩ lex_public`.*
