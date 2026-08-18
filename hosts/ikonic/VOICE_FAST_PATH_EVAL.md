# Constructor packets as voice/text FREE fast path — scorecard

**Date:** 2026-08-17  
**Question:** Can `constructor-resilience` (atoms → critique → packet → eval) sit on the **fast path** of Ikonic’s native voice/text inference engine, not only as offline research tooling?

**Verdict (now):** **Yes as a mid-ladder knowledge FREE tier** — between deterministic dispatch and residual LLM — **not** as a replacement for pattern/CLI FREE.  
**Verdict (ready to wire):** Packet **lookup + speak** is the first spike; mint/critique stay offline or post-turn.

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

### P0 — Prove the lane (1–2 days)

1. **Contract:** `GET`-shaped helper or in-process read:
   - input: `query`, optional `topic_id`
   - output: `{ sufficient, atoms[], method, topic_id }`
2. **Native session:** after curated arbiter miss / before soft feed, call helper on `vault/coherence`.
3. **Emit:** `pattern_id=knowledge_packet`, speak joined atoms (TTS phrases already short), `turn_audit` path=`command` submodule=`knowledge_packet`.
4. **Offline eval harness:** replay N voice transcripts through helper; report sufficient rate + latency; no WS required.

**Exit:** “hello computer / first-run / interest” questions from existing packets answer FREE; Mars-like queries fall through.

### P1 — Ground residual (same week)

5. When packet insufficient but non-empty overlap, pass atoms into `native_llm` prompt as `<coherence_packet>`.
6. Daily Review teach `deep` stays force-residual; teach `fast`+CLI stays utterance_cache; add teach **`packet`** → mint atom (pending → critique).

### P2 — Product surfaces

7. Voice: “where do my interests meet Lex on X” → `intersect` → speak + glass list.
8. Unify vault layout: `coherence/` only; deprecate parallel `constructor/` or symlink.
9. Optional: Rust port of greedy + query seed for zero-Python desktop.

### Non-goals (P0)

- Mint/critique on STT hot path  
- Replacing pattern FREE or media tools  
- Auto-promoting lifelog into packets  

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

**Adopt packets as Knowledge FREE** on the inference ladder:

1. Keep verb FREE as-is (patterns, cache, working sets).  
2. Add packet lane for **durable belief / interest / product-law** questions.  
3. Use mint → critique → review **offline** to grow the store; use eval continuously as the regression suite for the lane.  
4. Feed residual with packet leftovers so the slow path still benefits.

That is the constructor-theoretic read of the engine: **explanatory constructors (packets) on the free path; generative residual only for the frontier.**

---

## 9. Next concrete spike (when you say go)

Single PR on `feat/constructor-fastpath` (or stacked branch):

- `ikonic_voice`: `knowledge_packet` match (question-shaped + topic keywords) → load `COHERENCE_ROOT` / `{vault}/coherence` → speak  
- Tests: packet hit / miss / audit path  
- Script: `scripts/eval_voice_packet_lane.py` wrapping `coherence eval` against vault topics  

No MLX on the turn; optional later for sufficiency only.
