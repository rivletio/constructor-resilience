# Host adapter contract

A **host** is any product that stores topics and/or injects packets.
The **compression method** is open; **circle policy and UX** belong to the host.

## MUST

1. Resolve store root via `--root`, `COHERENCE_ROOT`, or host default (`$PWD/.coherence`).
2. Treat `atoms.json` + `packet.json` (or `share.json`) as the share unit — not full transcripts.
3. Load **packet atoms** before generating when resuming a theme.
4. Write only **durable** claims as atoms (net-new).
5. Never ambient-export **inner personal** data into public/circle surfaces.

## SHOULD

1. Support **interest surfaces**: topics tagged with what the user is willing to show.
2. Support **`intersect` / `union`**: recompute overlap when the user changes browse dials or ∩ vs ∪. Run challenges: does an atom still hold given the other surface?
3. Project packets to classical web (markdown, RSS item, URL cite) when useful.
4. Separate **published** (public figures, open projects) from **private** stores.

## MAY

- Voice / TUI over packets
- Graph visualization
- Multi-agent handoff of `atoms.json` / `share.json`
- Embeddings *in addition to* (not instead of) the graph packet

---

## Host matrix

| Host | Depth | Notes |
|------|--------|------|
| **CLI (`coherence`)** | Full | Reference implementation |
| **Agent skill (Claude / Grok / Codex / Cursor)** | Medium | Session digest + handoff — [`rivletio/constructor-resilience-skill`](https://github.com/rivletio/constructor-resilience-skill) |
| **Obsidian** | Export | Human inspect via `export` |
| **Editors** | Inject | Packet as rules/context |

---

## Host duties (policy)

| Duty | Behavior |
|------|----------|
| Store path | `$COHERENCE_ROOT` or `$PWD/.coherence` |
| Inner circle | Private material never auto-atoms into public topics |
| Interest surface | User-curated topics = “what I’m into” |
| Public follow | Import/subscribe creator `atoms.json` like a feed |
| Browse | Live `intersect` / `union` (seed?) + belief challenges |
| Share | Intentional `share.json` envelope (`coherence share` / `import`) — never ambient |

Formats are the same at every circle. **Hosts enforce policy.**
Other tools can speak the same packets. Circle policy belongs to the host.
