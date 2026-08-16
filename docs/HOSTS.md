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
| **Grok / Claude skill** | Medium | Session cache + handoff |
| **Obsidian** | Export | Human inspect via `export` |
| **Cursor / editors** | Inject | Packet as rules/context |
| **Ikonic** | Full product | Vault + voice + circles + glass — **where it shines** |

---

## Ikonic-specific duties

| Duty | Behavior |
|------|----------|
| Store path | `{VAULT_ROOT}/coherence/` (or `knowledge/`) |
| Inner circle | Lifelog/mail never auto-atoms into public topics |
| Interest surface | User-curated topics = “what I’m into” |
| Public follow | Import/subscribe creator `atoms.json` like a feed |
| Browse | Live `intersect(my_surface, their_surface, seed?)` |
| Voice | FREE/about over packet first; residual only for frontier |
| Share | Intentional packet out — reinvent *what* we share |

Ikonic is not “another notes app using this library.”  
It is the **computer for intentional interest geometry** from public web-compat surfaces through to super-secure personal vault.
