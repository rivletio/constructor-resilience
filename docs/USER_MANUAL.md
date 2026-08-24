# Constructor Resilience — User Manual

Pack a long thread into **atoms** (durable claims) and a **packet** (a small set to resume from), so the next session or another agent does not need the transcript.

This is for multi-session and multi-agent work, not a general notes app.

**What you hand off:** `topics/<id>/atoms.json` + `packet.json`, or `coherence share` → `share.json`.

| Word | Meaning |
|------|---------|
| **Atom** | One stand-alone claim. Constrains a possibility, impossibility, fact, or decision. |
| **Mention / ref** | A name or citation on that claim — not a second graph. |
| **Consistency** | Pairwise support or conflict, `[-1, 1]`. |
| **Packet** | A small subset: coverage + support − redundancy. |
| **Share** | An intentional file with audience and forward grant. Never ambient. |

The cache is files on disk: `$COHERENCE_ROOT` or `$PWD/.coherence`. The chat log is not.

## Workflow

**Resume.** Load what you already claimed:

```bash
coherence cache "your theme"
# or: coherence use <topic-id>
```

Read the packet first. If CACHE MISS, pack (next). Only chase what is not already there.

**Pack.** The agent writes claims from this conversation (no extra model):

```bash
coherence pack --title "your theme" --constraint fact \
  --atom "Durable claim." \
  --mention "The Concept:concept" \
  --atom "Second durable claim." \
  --mention "A Person:person"
```

The packing agent hangs names on the claim (`--mention Name:kind`). That is the extraction — not a second entity graph. Atom JSON shape is in [SPEC.md](../SPEC.md). `pack` keeps claims; MLX `mint` starts pending. Back out anything that does not actually constrain a possibility or impossibility.

**Handoff.** `pack` already wrote the packet.

```bash
coherence share --to alice --audience circle --forward none
```

**Import someone else’s surface.**

```bash
coherence import ./their-atoms.json --title "Lex public" --use
coherence intersect my-ai-interests lex-public --query consciousness
```

**Optional (Apple Silicon).** `coherence mint` / `critique` / `eval` after `./install.sh --mlx`. Not required.

## Commands

`coherence --help`. Common groups:

| Command | Role |
|---------|------|
| `status` `list` `use` `create` | Topics |
| `cache` `find` | Find a packet for a question |
| `pack` `ingest` `add-atom` | Write claims and a packet |
| `review` `reject`/`backout` `set-review` | Review |
| `search` `packet` | Compress |
| `share` `import` `intersect` | Hand off / overlap |
| `export` | Markdown for Obsidian / Roam |

## What to store

Only claims you would want injected into a future model call on this topic. Not greetings, UI state, near-duplicates, or invented elaboration.

```
$COHERENCE_ROOT/                 # default: ./.coherence
  meta.json
  active.json
  topics/<id>/
    atoms.json
    packet.json
    share.json                   # after `coherence share`
```
