---
name: constructor-resilience
description: >
  Pack a session into durable claims and a small resume packet. Use when
  digesting research, handing off between agents, sharing what was decided
  (not the transcript), attaching names and citations to claims, checking
  whether a claim still holds, overlapping two interest surfaces
  (intersection or union), or looking up a question over a union
  (possible/impossible pairs, atoms still in question). Triggers: pack this
  session, digest this, handoff, share claims, coherence cache, atoms,
  ingest, mint, packet, constructor resilience, interest intersection,
  union, lookup, challenge atom.
license: AGPL-3.0-or-later
compatibility: Requires Python 3.10+. First `bin/coherence` next to this file installs the CLI if needed.
metadata:
  author: Rivlet
  version: "0.1.12"
  homepage: https://github.com/rivletio/constructor-resilience-skill
  upstream: https://github.com/rivletio/constructor-resilience
when-to-use: >
  pack this session, digest this into claims, handoff, share what we
  decided, cache this research, lookup over a union, intersect, challenge
  atoms in question
---

# Constructor Resilience

Turn this conversation into **atoms** (durable claims) and a **packet** (a small set to resume from). Share the packet, not the transcript.

An atom must constrain a possibility, an impossibility, a fact, or a decision. Names and citations hang on the claim; they are not a second graph.

## Setup

Use `coherence` on PATH. If missing, run `bin/coherence` next to this file (first run installs the CLI).

Store: `$COHERENCE_ROOT` or `$PWD/.coherence`. Do **not** run `coherence review --serve --browser` unless the user asks (it can open Chrome).

## Protocol

### Resume

`coherence cache "theme"` (or `use <topic-id>`). Read the **packet** before new work. Cache rewrites only the **top** topic's packet; other matches are listed, not overwritten.

If that misses, pack — do not stop at CACHE MISS.

### Pack (default)

Write stand-alone claims from **this session** (do not copy sample names or paths). You extract the names. Output **only** a labeled draft, then:

`coherence pack --draft -`  (pipe the draft)  or  `coherence pack --draft /tmp/pack.txt`

```
TITLE: <THEME>
CONSTRAINT: fact
CLAIM: <SENTENCE>
AT: <t=SECONDS or path:LINE>
MENTION: <NAME:kind>
AT: <where that name occurred>
ALIAS: <PHRASE THAT APPEARS IN THE CLAIM>
```

`AT` after `CLAIM` is **where the sentence occurred**. `AT` after `MENTION` is **where that name occurred** (can differ). Both travel on packet/share.

Replace every `<SLOT>`. If a slot is still in angle brackets, that claim FAILs — rewrite from the session.

`CONSTRAINT`: `possibility` | `impossibility` | `fact` | `decision`.

**Joins** (`person` | `org` | `work` | `place` | `concept` | `other`): names the claim is *about*. Attest the name in **this** CLAIM, then act on FAIL:

| FAIL | Experiment |
|------|------------|
| `not attested` | Put the name or `ALIAS:` in the sentence, **or drop the MENTION** |
| title-case expansion | Initials of a title-case phrase in the claim count as the name |
| locator only | Does not attest — still name-in-sentence or drop |

`It predicts…` + `MENTION: <NAME>` is attested: packet/share keep that mention **on that claim**. Prefer the name in the sentence when easy; do not FAIL the pronoun if the join travels.

Locators: `path:LINE`, `t=SECONDS`, `p.N ¶M`, `arxiv:YYYY.NNNNN` (becomes a **ref**, not a file path). Conversation-only concepts may omit mention AT. Compact variants count (hyphens/spaces dropped). Never Python, never invent a JSON file, never reuse leftover example sentences.

Shell flags still work (`--atom` / `--mention` / `--at`) if you can quote them. Draft is the small-model path. Numbered claims (`1 <SENTENCE>`) count as `CLAIM:` (tiny hosts often skip the label).

### Loop until quality

Same loop for **pack**, **intersect**, and **union**. Do not share while a check FAILs or an atom would be false if read alone. Internally (think it) and on disk.

**Pack**

1. **Observe** — `coherence check` (also printed by `pack`). Note FAIL indices *and* any quote, template, chat, or claim not from this session.
2. **Reason** — one sentence: missing join, bad locator, copied `<SLOT>`, quoted fragment, mention not attested, or does not constrain a possibility / impossibility / fact / decision.
3. **Experiment** — do what the FAIL line says (rewrite with the name, add `ALIAS:`, or drop the join). `coherence reject N --reason "…"` then pack **one** replacement.

**Overlap** (`intersect` ∩ or `union` ∪ — including a topic with itself)

```
coherence intersect <mine> <theirs> --out /tmp/o1.json
coherence check --packet /tmp/o1.json
# after reject / pack a replacement:
coherence intersect <mine> <theirs> --out /tmp/o2.json --against /tmp/o1.json
```

`intersect a a` is an audit: each atom vs the rest of the set (not vs its clone).

1. **Observe** — **every** challenge on **every** atom (all contradictors are listed; none are dropped).
2. **Reason** — does this atom still hold given each counterpart? `TENSION` = incompatible (check FAILs until resolved). `GARBAGE JOIN` = shared name with `grounding < 0.5` (name not in the claim) — drop the tag. Support = claim-text overlap. `JOIN` = grounded shared name with thin content (one per atom; a common paper is not a cartesian of belief checks).
3. **Experiment** — `use` the originating topic, `reject` the falsified `store_index` (or pack a revised claim). Re-run overlap. **Compare** `--against` the previous packet: dropped / added / tension before→after.

Repeat. Stop when check has no FAIL and no TENSION **and** `--against` reports the reconstructed set matches the previous one (fixed point). Same FAIL twice → simpler experiment (one CLAIM).

FAIL is mechanical: too short, chat, copied template, quoted fragment, missing constraint/mentions, mention not attested (name/ALIAS in the sentence or drop), file mention without a line, YouTube mention without `t=`, citation in the sentence without `refs`. Overlap packets carry traveling claims (text plus mentions/refs/constraint). `check --packet` on ∩/∪ uses text FAILs plus challenges, not missing-constraint. Packet/share atoms carry mentions on each claim.

Duplicates are skipped. `pack` / `ingest` / `add-atom` keep claims. MLX `mint` starts `pending`. `--pending` queues review.

### Back out

```bash
coherence reject 3 --reason "claimed impossibility does not hold"
```

Rejected atoms stay on disk, drop out of packets. Indices stay stable.

### Handoff

```bash
coherence share --to <id> --audience circle --forward none
```

Give `topics/<id>/atoms.json` + `packet.json`, or `share.json`.

### Import / overlap

```bash
coherence import ./their-atoms.json --title "Their surface" --use
coherence intersect <mine> <theirs> --query "…" --max-size 8 --out /tmp/o1.json
coherence check --packet /tmp/o1.json
coherence intersect <mine> <theirs> --out /tmp/o2.json --against /tmp/o1.json
```

`intersect --union` is the same as `union`. Self-audit: `intersect <id> <id>`. Then the loop above.

**Lookup (fast, no model)** over the full ∪ of two topics, or an overlap file:

```
coherence lookup "<QUESTION>" --mine <id> --theirs <id>
coherence lookup "<QUESTION>" --packet /tmp/o1.json
```

Hits are query-ranked atoms. `polarity` is possible × impossible on a shared join. `question` is pending, tension, or a constructor (possibility/impossibility) still to evaluate.

### Optional local MLX (Apple Silicon)

`./install.sh --mlx`, then `coherence mint` / `critique` / `eval`. Skip if unavailable.
Default mint model: `mlx-community/Qwen3-8B-4bit` (`COHERENCE_MLX_MODEL`).

**Self-evaluation (built in):** `coherence mint` retries up to 3 times if the draft
keeps too few grounded atoms, drops too many as ungrounded, or emits meta /
quoted-fragment atoms (`(paraphrasing…)`). The next try sees the dropped claims
and is told to write stand-alone sentences. A smaller model can still land a
packet in a few tries. `--attempts N` overrides. Pack (no MLX) remains the
any-machine path.

## Circles

Keep private claims off public topics. Share only with `coherence share`.

## Docs

[SPEC.md](https://github.com/rivletio/constructor-resilience/blob/main/SPEC.md) ·
[USER_MANUAL.md](https://github.com/rivletio/constructor-resilience/blob/main/docs/USER_MANUAL.md) ·
[README.md](https://github.com/rivletio/constructor-resilience/blob/main/README.md)
