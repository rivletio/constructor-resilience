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
  --mention "The Concept:concept" --at "src/mod.py:12" \
  --atom "Second durable claim." \
  --mention "A Person:person" --at "t=3033"
```

The packing agent hangs names on the claim (`--mention Name:kind` or a `TITLE`/`CLAIM`/`MENTION`/`AT` draft: `coherence pack --draft pack.txt`). After pack, loop: **observe** (`coherence check`), **reason**, **experiment** (`reject` + one replacement) until every atom PASSes and still looks true. The same loop runs on overlap (`coherence intersect` / `union`, including a topic with itself): check every challenge, reconstruct, compare with `--against` the previous packet. `TENSION` is a check FAIL (incompatible claims are not done). A mention is **garbage** when `grounding < 0.5`: the name is not attested in the claim (compact substring or name tokens). Check FAILs `mention 'JEPA' not grounded in claim (0.00)`. Grounded names (`JEPA` in the sentence, or `JEPA` in `V-JEPA`) still join; unearned tags do not. Atom JSON shape is in [SPEC.md](../SPEC.md).

**Handoff.** `pack` already wrote the packet.

```bash
coherence share --to alice --audience circle --forward none
```

**Import someone else’s surface.**

```bash
coherence import ./their-atoms.json --title "Lex public" --use
coherence intersect my-ai-interests lex-public --query consciousness --out /tmp/overlap.json
coherence union my-ai-interests lex-public --out /tmp/union.json
coherence check --packet /tmp/overlap.json
# after reject/revise:
coherence intersect my-ai-interests lex-public --out /tmp/overlap2.json --against /tmp/overlap.json
```

**Optional (Apple Silicon).** `coherence mint` / `critique` / `eval` after `./install.sh --mlx`. Not required.

## Commands

`coherence --help`. Common groups:

| Command | Role |
|---------|------|
| `status` `list` `use` `create` | Topics |
| `cache` `find` | Find a packet for a question |
| `pack` `ingest` `add-atom` `check` | Write claims, packet, and mechanical self-eval |
| `review` `reject`/`backout` `set-review` | Review |
| `search` `packet` | Compress |
| `share` `import` `intersect` `union` | Hand off / overlap (∩ or ∪) + belief challenges |
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
