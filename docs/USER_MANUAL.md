# Constructor Resilience — User Manual

**What it is:** an **agent coherence-cache** for Grok (and other agents).  
**What it does:** compresses durable claims from long threads into topical *atoms* and *resilient packets*, with a *meta-graph* across topics, so the same agent, a later session, or another agent can resume with shared high-signal context.

This is **not** positioned as a general human note-taking product (typewriter / word-processor class). Humans can inspect atoms and graphs; the design target is **better multi-session and multi-agent work**.

Subjects live only in **topic data**. The skill is domain-agnostic machinery.

**Shareable unit:** `topics/<id>/atoms.json` — hand this file (plus an optional packet listing) to another agent or collaborator as the compressed project context.

---

## 1. Mental model

```
Your questions over time
        │
        ▼
┌───────────────────┐
│  Meta-graph       │  topics + links between topics
│  meta.json        │
└─────────┬─────────┘
          │ zoom in
          ▼
┌───────────────────┐
│  Topic store      │  atoms + pairwise consistency
│  topics/<id>/     │
└─────────┬─────────┘
          │ resilience search
          ▼
┌───────────────────┐
│  Resilient packet │  small, consistent, low-redundancy set
└───────────────────┘
          │
          ▼
   Injected as context for the next answer
```

**Atoms** — short durable claims you would want in a future prompt.  
**Consistency** — score in `[-1, 1]`: support, neutral, or conflict.  
**Packet** — the subset search selects under coverage + support − redundancy.  
**Meta-graph** — how topics relate (your research program map).

---

## 2. Persistence (important)

| What | Survives a new Grok chat? |
|------|---------------------------|
| Topic files on disk | **Yes**, if the same project/workspace is used |
| Meta-graph links | **Yes**, same condition |
| Skill installation | **Yes** (under `.grok/skills/`) |
| Chat transcript itself | **No** |

The cache is **file-backed**, not chat-backed.

- Same project path (`/home/workdir/artifacts/knowledge/` in this environment) → topics **grow across sessions**.
- Ephemeral chat with no shared disk → empty cache.

**Practical rule:** treat this as a *project-local research brain*. Open the same project, invoke the skill, and prior atoms are available.

---

## 3. When to use it

Use the skill when you want to:

- Cache progress from a **long agent/human engagement** into durable atoms  
- Resume a theme in a **new session** without the full transcript  
- **Hand off** context to another agent or collaborator via `atoms.json`  
- Compress prior work into a **packet** before more tool use or generation  
- Keep topics focused and link related threads on the meta-graph  

Triggers (examples): “use the coherence cache”, “update atoms for handoff”, “cache this thread”, “shared context for this project”, “what’s in the topic store for X?”

---

## 4. Basic workflow

### A. Start of a session (fast-forward)

1. Ask Grok to use **constructor-resilience** on your question.  
2. Agent should run something like:
   ```bash
   knowledge_ops.py cache "your question or theme"
   ```
3. Read the **packet(s)** — that is prior durable knowledge.  
4. Only then do new web research or reasoning on the *frontier*.

### B. During research (expand)

1. **Zoom** into a topic (`use`) or **create** one if the theme is new.  
2. Extract **only durable** claims → `add-atom`.  
3. **Score** pairs (judgment preferred over pure keyword overlap).  
4. Optionally `search --greedy --max-size K` for an updated packet.  
5. If this theme relates to another topic → `link src dst`.

### C. End of a useful call

1. Packet stated clearly.  
2. What was **added** this turn (delta).  
3. Optional graph PNG embedded for the active topic.  
4. Open questions left explicit (so the next session can pick them up).

---

## 5. Commands (cheat sheet)

Default root: `/home/workdir/artifacts/knowledge/`

```bash
# Orientation
python3 scripts/knowledge_ops.py status
python3 scripts/knowledge_ops.py list
python3 scripts/knowledge_ops.py meta

# Routing / cache layer
python3 scripts/knowledge_ops.py find "query text"
python3 scripts/knowledge_ops.py cache "query text" --topics 2 --max-size 6

# Topics
python3 scripts/knowledge_ops.py use <topic-id>
python3 scripts/knowledge_ops.py create --title "My theme" --use

# Expand
python3 scripts/knowledge_ops.py add-atom "Durable claim..." [--auto-score]
python3 scripts/knowledge_ops.py set-consistency i j 0.8
python3 scripts/knowledge_ops.py apply-scores --json '{"scores":[{"i":0,"j":1,"score":0.7}]}'

# Compress
python3 scripts/knowledge_ops.py search --greedy --max-size 8
python3 scripts/knowledge_ops.py search --reads 40 --sweeps 400

# Meta-graph
python3 scripts/knowledge_ops.py link topic-a topic-b --score 0.6 --relation "shared-mechanism"

# Visual
python3 scripts/knowledge_ops.py render   # → topics/<id>/atoms_graph.png
```

In chat you usually do **not** type these yourself; you ask Grok to run the skill. The commands are what the agent uses under the hood.

---

## 6. Scoring guide

| Score | Meaning |
|------:|---------|
| +1.0 | Strong mutual support |
| +0.5 | Compatible / mild support |
|  0.0 | Orthogonal for this topic (usually omit the edge) |
| −0.5 | Tension; both true only with qualification |
| −1.0 | Direct conflict |

Keep the graph **sparse**. Keyword overlap alone is a weak reason to add an edge.

Redundancy is handled in search (near-paraphrases are penalized when co-selected), so packets stay diverse.

---

## 7. How research gets better over time

| Session | Without cache | With cache |
|--------|----------------|------------|
| 1 | Explore, take notes | Create topic, atomize durable claims |
| 2 | Re-read / re-search | `cache` → packet → only chase gaps |
| 3+ | Notes sprawl | Meta-graph + packets = program memory |

Improvements:

1. **Less rediscovery** — packets skip settled ground.  
2. **Sharper frontier** — effort goes to unresolved edges.  
3. **Honest structure** — conflicts and links are explicit.  
4. **Compounding value** — the 10th session is richer than the 1st *if* you kept writing durable atoms.

**Filter for what to store:**  
> Only atomize what you would want injected into a future model call on this topic.

---

## 8. Realistic expectations in Grok chat

**Works well when:**

- You use a stable project/workspace where `knowledge/` persists  
- You (or the agent) invoke the skill at the start of research turns  
- Topics stay focused; new themes get new stores + links  

**Does not work when:**

- The filesystem is wiped between chats  
- Nobody runs `cache` / `use` and everything stays in free-form chat  
- One mixed topic absorbs unrelated domains (weak graph)

The skill does **not** auto-inject into every Grok reply. It becomes a fast layer when invoked.

---


## Export to Obsidian / Roam

```bash
python3 scripts/knowledge_ops.py export              # active topic
python3 scripts/knowledge_ops.py export --topic <id> --out /path/to/vault/folder
```

Writes:

- `00-<topic>-index.md` — map of content with `[[wiki-links]]`
- one markdown note per atom, linked by consistency edges
- `<topic>-roam-outline.md` — single hierarchical outline for Roam-style import

Open the export folder as (or inside) an Obsidian vault to browse the graph. Share the same folder or `atoms.json` for agent handoff; export is the human-readable view.

## 9. File map

```
~/.grok/skills/constructor-resilience/
├── SKILL.md                 # agent protocol
├── docs/
│   ├── USER_MANUAL.md       # this file
│   ├── README.md            # architecture notes
│   └── qubo-formulation.md  # energy model
└── scripts/
    ├── knowledge_ops.py     # CLI
    ├── resilience_search.py # SA + greedy + redundancy
    ├── consistency.py       # scoring helpers
    └── render_graph_png.py  # graph image

/home/workdir/artifacts/knowledge/     # your data (not the skill)
├── meta.json
├── active.json
└── topics/<id>/
    ├── atoms.json
    └── atoms_graph.png
```

---

## 10. Quick start (first time)

1. In a Grok project chat, say you want to use **constructor-resilience** for theme *X*.  
2. Agent creates a topic and initializes the store if needed.  
3. Do a bit of real research; ask it to save durable claims as atoms and score them.  
4. Ask for a resilient packet and (optionally) the graph PNG.  
5. Next session: “Use the coherence cache for *X*” → you should see prior packets first.

That is the whole loop: **route → expand → compress → reuse**, across sessions, on disk.
