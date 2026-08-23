# Host adapter contract

A **host** is any product that stores topics and/or injects packets.  
The **compression method** is open; **circle policy and UX** belong to the host.

## MUST

1. Resolve store root via `--root`, `COHERENCE_ROOT`, or host default.  
2. Treat `atoms.json` + `packet.json` as the share unit (not full transcripts).  
3. Inject **packet atoms** as privileged context before generation when resuming a theme.  
4. Write only **durable** claims as atoms (net-new).  
5. Never ambient-export **inner personal** data into public/circle surfaces.

## SHOULD

1. Support **interest surfaces**: topics tagged with what the user is willing to show.  
2. Support **`intersect`**: recompute overlap when the user changes browse dials.  
3. Project packets to classical web (markdown, RSS item, URL cite) when useful.  
4. Separate **published** (public figures, open projects) from **private** stores.

## MAY

- Voice / TUI / glass UI over packets  
- Graph visualization  
- Multi-agent handoff of `atoms.json`  
- Embeddings *in addition to* (not instead of) the graph packet  

---

## Host matrix

| Host | Depth | Notes |
|------|--------|------|
| **CLI (`coherence`)** | Full | Reference implementation |
| **Agent skill (Claude / Grok / Codex / Cursor)** | Medium | Session cache + handoff — [`rivletio/constructor-resilience-skill`](https://github.com/rivletio/constructor-resilience-skill) |
| **Vault / personal computer** | Full product | `{VAULT_ROOT}/coherence/` — see [`hosts/vault/`](../hosts/vault/) |
| **Obsidian** | Export | Human inspect via `export` |
| **Cursor / editors** | Inject | Packet as rules/context |

---

## Host duties (policy)

| Duty | Behavior |
|------|----------|
| Store path | `$COHERENCE_ROOT`, or `{VAULT_ROOT}/coherence/` for a vault-style host |
| Inner circle | Private/lifelog material never auto-atoms into public topics |
| Interest surface | User-curated topics = “what I’m into” |
| Public follow | Import/subscribe creator `atoms.json` like a feed |
| Browse | Live `intersect(my_surface, their_surface, seed?)` |
| Voice | Packet first; residual generation only for frontier |
| Share | Intentional packet out — reinvent *what* we share |
| Ensure | Cited URLs exist locally (`feeds/inbox_items`) before speaking overlap |

Formats are the same at every circle. **Hosts enforce policy.**
Vault-style hosts are first-class: same wire formats, same packets, no special fork of this package.
