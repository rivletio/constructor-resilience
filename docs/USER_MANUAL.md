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

The packing agent hangs names on the claim (`--mention Name:kind` or a `TITLE`/`CLAIM`/`MENTION`/`AT` draft: `coherence pack --draft pack.txt`). After pack, loop: **observe** (`coherence check`), **reason**, **experiment** (`reject` + one replacement) until every atom PASSes and still looks true. The same loop runs on overlap (`coherence intersect` / `union`, including a topic with itself): check every challenge, reconstruct, compare with `--against` the previous packet. `TENSION` is a check FAIL (incompatible claims are not done). Packet, share, and overlap keep **mentions on each claim**, so `It predicts…` + `MENTION: JEPA` stays bound after handoff. Import an ∩ file and the joins come with it. `AT` after `CLAIM` is where the sentence occurred; `AT` after `MENTION` is where that name occurred. A mention is **garbage** when `grounding < 0.5` and it does not fill an anaphor on that atom. A shared attested name is a **join** (affinity 0.62), not a paraphrase — two facts about the same paper both stay in the overlap packet. Mention-only counterparts collapse to one `JOIN` challenge per atom (not a cartesian of “does this still hold?”). Check: `not attested` → put the name/`ALIAS` in the sentence or drop the join. Atom JSON shape is in [SPEC.md](../SPEC.md).

**Handoff.** `pack` already wrote the packet.

```bash
coherence share --to alice --audience circle --forward none
```

**Lookup.** After a union (or two topic ids), ask in natural language. Lexical, no extra model. Hits, possible × impossible pairs, and atoms still in question:

```bash
coherence lookup "positional encodings" --mine arxiv-transformer --theirs attention-notes
coherence lookup "positional encodings" --packet /tmp/union.json
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
| `cache` `find` `lookup` | Find a packet, or fast NL lookup over a union |
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
