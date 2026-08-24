# Constructor Resilience — User Manual

Compress durable claims from a long thread into **atoms** and a **resilient packet**, so the same agent, a later session, or another agent can resume without the transcript.

This is machinery for multi-session and multi-agent work, not a general note-taking app.

**Shareable units:** `topics/<id>/atoms.json` + `packet.json`, or `coherence share` → `share.json`.

---

## Mental model

```
Session / source text
        │  ingest or add-atom (host model by default)
        ▼
┌───────────────────┐
│  Topic store      │  atoms + pairwise consistency
│  topics/<id>/     │  optional constraint, mentions, refs
└─────────┬─────────┘
          │ resilience search
          ▼
┌───────────────────┐
│  Resilient packet │  small, consistent, low-redundancy set
└─────────┬─────────┘
          │ share / import / intersect
          ▼
   Next session, other agent, or another surface
```

| Term | Meaning |
|------|---------|
| **Atom** | One durable claim. Constrains a possibility, impossibility, fact, or decision. |
| **Mentions / refs** | Joins onto the claim (names, citations). Not a second graph. |
| **Consistency** | Pairwise support/conflict in `[-1, 1]`. |
| **Packet** | Subset maximizing coverage + support − redundancy. |
| **Share** | Intentional envelope: packet + audience + forward grant. Never ambient. |

---

## Persistence

The cache is **file-backed** at `$COHERENCE_ROOT` or `$PWD/.coherence`.

| What | Survives a new chat? |
|------|----------------------|
| Topic files on disk | **Yes**, same workspace |
| Skill installation | **Yes** (`~/.grok/skills/`, `~/.claude/skills/`, …) |
| Chat transcript | **No** |

---

## Workflow

### Start of a session

```bash
coherence cache "your theme"
# or: coherence use <topic-id>
```

Load the **packet** first. Only chase what is not already claimed.

### Digest (default — no extra model)

The agent writes claims from *this conversation*:

```bash
coherence ingest --json ./claims.json --auto-score
# or one at a time:
coherence add-atom "Durable claim." --constraint fact --auto-score
```

`claims.json` shape:

```json
{
  "atoms": [
    {
      "text": "One stand-alone sentence worth injecting later.",
      "constraint": "fact",
      "mentions": [{"name": "JEPA", "kind": "concept"}]
    }
  ]
}
```

Minted/ingested atoms start `pending` unless `--accepted`. Review, then back out anything that does not actually constrain a possibility or impossibility.

### Packet / handoff

```bash
coherence search --greedy --max-size 6
coherence packet --rebuild
coherence share --to alice --audience circle --forward none
```

### Import a surface

```bash
coherence import ./their-atoms.json --title "Lex public" --use
coherence intersect my-ai-interests lex-public --query consciousness
```

### Optional local MLX (Apple Silicon)

`coherence mint` / `critique` / `eval` after `./install.sh --mlx`. Not required for the digest loop.

---

## Commands

Run `coherence --help`. Common:

| Command | Role |
|---------|------|
| `status` `list` `use` `create` | Topics |
| `cache` `find` | Route to a packet |
| `add-atom` `ingest` | Write claims |
| `review` `reject`/`backout` `set-review` | Review |
| `search` `packet` | Compress |
| `share` `import` `intersect` | Hand off / overlap |
| `export` | Obsidian/Roam markdown |

---

## What to store

Only atomize what you would want injected into a future model call on this topic.

Do not store greetings, UI state, near-duplicates, or invented elaboration.

---

## File map

```
$COHERENCE_ROOT/                 # default: ./.coherence
  meta.json
  active.json
  topics/<id>/
    atoms.json
    packet.json
    share.json                   # after `coherence share`
```
