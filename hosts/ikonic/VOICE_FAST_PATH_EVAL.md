# Constructor packets as voice/text FREE fast path — scorecard

**Date:** 2026-08-17  
**Question:** Can `constructor-resilience` (atoms → critique → packet → eval) sit on the **fast path** of Ikonic’s native voice/text inference engine, not only as offline research tooling?

**Verdict (narrow personal store only):** **Not good enough** for a product fast path. A few vault topics help research/handoff; they do not give every install the same FREE knowledge floor.

**Verdict (expanded — subsystem-shipped packets):** **Good enough as the Knowledge FREE layer** — same shape as today’s `utterance_seed.yaml` / `voice_session.yaml`: each installed subsystem brings a shared atom/packet surface; everyone with that subsystem shares that fast path. Personal topics remain overlays, not the sole store.

**Not a replacement for verb FREE** (patterns, working sets, NL→CLI). Packets answer durable claims; seeds already answer durable *commands*.

### Non‑negotiable: terminal DSL + mappings

The **terminal system stays required** — bash-like DSL, `registry.yaml` commands, pipes, variables, cost tiers, and the NL→CLI maps that hit them:

| Layer | Role | Must keep |
|-------|------|-----------|
| Command registry / handlers | `/discover`, `/open`, pipes, macros… | Yes — product surface + FREE execute target |
| `utterance_seed` / curated phrases / utterance cache | Spoken/typed language → those commands | Yes — primary verb FREE |
| Session control YAML | wake, goodbye, meeting, dictate | Yes |
| Constructor packets | Durable *claims* (law, howto, interest) | Additive Knowledge FREE |
| Teach / critique / review | May **propose** new NL→CLI seeds or packet atoms | Informs maps; does not delete the DSL |

**Law:** voice/text fast path *executes* through terminal (and peer FREE actions). Packets may *explain*, *gate residual*, or *suggest* a `/cmd` — they do not absorb the command layer.  
Same doctrine as today: curated arbiter can emit `run_terminal_command`; utterance teach pins CLI strings. Constructor resilience can later score “which phrasings belong in the seed” — the **commands and mappings still have to exist**.

---

## 0. Expanded scope: subsystem-preloaded packets

### Precedent (already shipping)

| Shared seed | Subsystem | What every install gets |
|-------------|-----------|-------------------------|
| `utterance_seed.yaml` | terminal | NL→CLI rows (conf 0.5) |
| `curated_phrases.yaml` | terminal | exact/prefix → CLI |
| `voice_session.yaml` | voice | wake/goodbye/dismiss patterns |
| prompt defaults | prompts/ | identity, compose, TTS seeds |

Load order is always: **package builtin → vault overlay → user teach**.  
Constructor packets should follow **exactly that law**.

### Proposed layout

```text
subsystems/<id>/
  coherence/                    # ships with the package
    topics/
      <id>-law/                 # product law for this subsystem
        atoms.json
        packet.json
      <id>-howto/               # optional operator knowledge
        atoms.json

{vault}/coherence/              # runtime merge root (COHERENCE_ROOT)
  topics/
    voice-law/                  # materialized from package on install/update
    feed-law/
    …                           # user / followed surfaces (overlays)
```

**Materialize on subsystem enable/update** (mirror utterance seed): copy or merge package topics into `{vault}/coherence/topics/` with `origin: package`, `subsystem: voice`. Vault overlays and user mint never overwrite package atoms in place — teach adds *new* atoms or user-topic forks (same as pinned teach beating seed conf 0.5).

### Who shares what

| Surface | Shared among | Mutability |
|---------|--------------|------------|
| Package `coherence/topics/*` | Everyone who installed that subsystem (all devices/vaults that pulled the package version) | Versioned with the package; changelog via release |
| Vault overlay topics | That vault’s users | Local |
| User mint / Daily Review atoms | That user (or intentional promote) | Pending → critique → accept |
| Followed public (Lex, etc.) | Opt-in subscribers | Import/subscribe |

Fast-path **read set** for a turn:

```text
union(
  packets of enabled subsystems' package topics,   # shared floor
  active / tagged user topics,                     # personal
  optional followed publics                        # later
)
```

Query-aware seed runs over that union (same `packet_for_query` we already eval).

### Why this answers “is it good enough?”

| Requirement | Personal-only | + Subsystem packages |
|-------------|----------------|----------------------|
| Cold install has useful Knowledge FREE | No | Yes — voice/feed/… law ships |
| Same answers across users for product behavior | Accidental | By construction |
| Fits existing seed doctrine | Weak | Strong (`utterance_seed` twin) |
| Scales as subsystems grow | One mega-topic | Per-package topics; install = load |
| Circles / privacy | Muddy | Package = public-to-install; user = inner |

**Good enough** means: the fast path is a **shared constructor floor per enabled subsystem**, plus personal overlays — not a single optional research folder.

---

## 1. What “fast path” means in Ikonic today

Native voice turn ladder (constructor-fastpath / Axum):

| Order | Tier | Cost character | Owns |
|-------|------|----------------|------|
| 0 | Control / session YAML | µs–ms, no LLM | wake, goodbye, meeting, dictate |
| 1 | Working set / screen | ms, vault list ops | “open the third”, count those |
| 2 | Pattern match → execute | ~ms–40ms vault | open, discover, what_is, media |
| 3 | Utterance cache + curated arbiter | SQLite + scores | taught NL→CLI |
| 4 | Soft feed resolve | vault search | bare titles |
| 5 | Room soft-hold | ambient bank | chatter, no residual |
| 6 | **Native LLM** (grounded library) | 100ms–few s | dialogue with feed snippets |
| 7 | Python residual | seconds, stalls under load | deep/agentic |

Doctrine already on the wall: *FREE is a cache of mutable mappings* (`control.rs`).  
Constructor packets are the same doctrine for **durable knowledge**, not for verbs.

---

## 2. Scorecard — fitness as inference fast path

Scoring: **Fit** to the voice/text engine · **Ready** now · **Risk** if forced into the wrong slot.

| Capability | Fit | Ready | Risk | Notes |
|------------|-----|-------|------|-------|
| Deterministic verbs (open, play, zoom) | Low | — | High if we try | Patterns + utterance cache already own this; packets are claims, not actions |
| “What do we believe about X?” | **High** | Medium | Low | Query-aware packet + speak is FREE knowledge |
| First-run / product law Q&A | **High** | **High** | Low | Live vault already has `voice-computer-first-run` packet (6 atoms) |
| Interest intersect (“me ∩ Lex on Y”) | **High** | Medium | Medium | Package `intersect` exists; no voice lane yet |
| Ground residual LLM | **High** | Medium | Low | Inject packet before native_llm / residual — fewer hallucinations |
| Teach from Daily Review → packet | Medium | Medium | Low | Review route teach → utterance_cache today; parallel path → atoms |
| Mint/critique on the hot path | Low | High offline | **High** | MLX mint is ~seconds; keep offline / post-turn |
| Latency vs pattern FREE | Medium | — | Medium | Packet load + lexical seed is ms; speak is TTS-bound |
| Latency vs native LLM | **High win** | — | Low | Skip chat completion when packet answers |
| Correctness / grounding | **High** | **High** | Low | Grounding gate + critique + eval already measure this |
| Circle / privacy | **High** | Spec only | Medium | Host must enforce visibility; engine must not dump lifelog |

**Bottom line:** Treat packets as **tier 2.5 / 3.5 — Knowledge FREE** (answer from durable claims), not tier 0–2 (do the thing).

---

## 3. Where it slots in the turn (target)

```
utterance
  → control / working-set / pattern FREE          # unchanged
  → utterance cache / curated CLI                 # unchanged
  → ★ PACKET LANE (new) ★
        cache(query) | packet_for_query(active|tagged topics)
        if sufficient → speak atoms (+ optional citations) → voice_done
        else fall through
  → soft feed / ambient hold
  → native_llm(grounding = feed ∪ packet leftovers)
  → python residual
```

**Sufficiency gate (same spirit as eval):**

- Lexical / query-overlap seed finds ≥1 atom above τ, **or**
- Small MLX/local classifier says `ANSWERABLE` vs `INSUFFICIENT` (optional; start with lexical)
- Off-topic / no overlap → honest fallthrough (like Mars control in eval)

Do **not** call full mint/critique on the turn.

---

## 4. Evidence we already have

### Package (constructor-resilience)

| Probe | Result |
|-------|--------|
| Mint + grounding | Source-faithful atoms; inventions dropped |
| Critique `--apply` | High-conf grounded accepts without UI |
| Eval query-aware | On-topic ✓ / off-topic ∅ |
| Model | `mlx-community/Qwen3-8B-4bit` local |

### Product vault (live)

`~/.ikonic/vault/coherence/topics/` already includes `voice-computer-first-run`, interest surfaces, Lex public — **the store is not empty**. Example packet answers first-run / HUD / “hello computer = presence only” without residual.

### Engine

- `what_is` / glossary / presentation_cache = proto–knowledge FREE (library + definitions), not interest atoms  
- `native_llm` grounds on **feed** keyword hits only — **packet not injected**  
- Utterance coherence job ≠ constructor packet (different graph: NL→CLI consistency)

---

## 5. Gaps (blockers for “it is the fast path”)

| Gap | Why it matters | Fix class |
|-----|----------------|-----------|
| No voice/session call into `COHERENCE_ROOT` | Packets never see the turn | Spike: Rust read `packet.json` or thin Python/CLI |
| No `pattern_id` / action type for packet answer | Can’t audit / teach / CTA | Add `knowledge_packet` FREE action |
| Sufficiency heuristic not in-engine | Risk of speaking weak packets | Port `packet_for_query` + τ; reuse eval harness offline |
| Topic routing | Which topic for this utterance? | Start: `active.json` + tags `voice`/`product`; later `cache` multi-topic |
| Dual roots (`coherence/` vs `constructor/`) | Vault constructor skill vs host README | **One law:** `{vault}/coherence` is product; skill may alias |
| Residual still feed-only | Missed FREE still ignores atoms | Inject packet into `native_llm` system/context |
| Circle policy not enforced in engine | Wrong atoms could surface | Filter `visibility` before speak |

---

## 6. Integration plan (phased)

### P0 — Shared floor + prove the lane

1. **Package shape:** `subsystems/<id>/coherence/topics/<id>-law/{atoms,packet}.json` (+ SPEC `origin`/`subsystem` fields).
2. **Materialize:** on enable/update, merge package topics → `{vault}/coherence/topics/` (utterance_seed load-order twin).
3. **Seed voice + terminal first:** product-law atoms (presence ≠ open terminal; FREE vs residual; discover tiers) — content already drafted in vault `voice-computer-first-run`.
4. **Turn helper:** input `query` → query-aware packet over **union of enabled subsystem topics** (+ optional active user topic) → `{ sufficient, atoms[], sources[] }`.
5. **Native session:** after curated miss / before soft feed → helper → `pattern_id=knowledge_packet` speak or fallthrough.
6. **Eval:** `coherence eval` against package topics as regression (on-topic ✓ / off-topic ∅).

**Exit:** Fresh vault with voice subsystem installed answers product-law questions FREE with **no** prior user mint; Mars falls through.

### P1 — Residual + teach

7. Inject overlapping atoms into `native_llm` when insufficient for full FREE speak.
8. Daily Review: teach `packet` → mint into user topic (pending → critique); never silent-edit package atoms.
9. Feed/explore package topics for domain law (what discover tiers mean, entity correction, etc.).

### P2 — Surfaces + optional network

10. Intersect UI/voice for user ∩ followed publics.
11. Rust port of query-seed greedy for desktop-native.
12. Optional: publish package packets as versioned HTTPS feeds for non-Ikonic hosts.

### Non-goals (P0–P1)

- Mint/critique on STT hot path  
- Replacing pattern FREE or media tools  
- Auto-promoting lifelog into package topics  
- One global mixed atom warehouse for all subsystems

---

## 7. Success metrics

| Metric | Target (P0) | How |
|--------|-------------|-----|
| Packet FREE hit latency | p50 < 20ms load+select (ex-TTS) | Instrument session |
| On-topic packet sufficiency | ≥ 70% on labeled set from vault topics | `coherence eval` + transcript suite |
| False speak (should have fallen through) | ≤ 5% | Human/label + Mars-style controls |
| Residual calls avoided | Track `knowledge_packet` vs `llm` in turn_audit | Daily Review path chips |
| Groundedness of spoken packet answers | mean ≥ 0.9 | Offline eval on spoken text |

---

## 8. Recommendation

**Expand scope before calling the fast path “done.”**

1. **Terminal DSL + NL→CLI maps are mandatory** — keep growing registry, seeds, curated maps; never replace with packets.  
2. **Verb FREE** = patterns / working sets / utterance seeds / curated → `/commands` (and peer FREE actions).  
3. **Knowledge FREE** = packets **shipped inside each subsystem package**, materialized like `utterance_seed`.  
4. Constructor critique/eval may **inform** which phrasings deserve seed rows — they do not become the command layer.  
5. Personal topics overlay; package atoms advance by release.  
6. Residual only for the frontier; optionally grounded on packet leftovers.

**Is it good enough today?** Method yes; we still need the full terminal map **and** subsystem-shipped packets. Packets alone are not the fast path.

---

## 9. Next concrete spike (when you say go)

Stacked work (terminal first-class throughout):

1. **Keep extending** utterance_seed / curated / registry coverage for real spoken commands.  
2. **Package seed:** `subsystems/voice/coherence/topics/voice-law/` (product-law atoms); materialize like utterance_seed.  
3. **Lane:** after curated miss → knowledge packet speak / miss → then soft feed → residual.  
4. **Eval CI:** `coherence eval` on `voice-law` (+ Mars); separately track FREE command hit-rate from turn_audit.  

No MLX on the turn.
