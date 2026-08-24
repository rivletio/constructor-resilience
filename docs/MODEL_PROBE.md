# Constructor mint model probe (2026-08-24)

Live `coherence mint` + packet Q&A on Apple Silicon MLX. Did **not** load
Qwen 27B. Self-eval retries up to 3 times on too-few atoms, too many
dropped, meta/quoted-fragment form, or source coverage < 0.45.

Fixture: Ikonic OS law (guest LLM ban, GLiNER2 default, pack needs no
mint model, FREE is deterministic, 27B GPU blink).

Packet queries:

1. Where do LLM APIs run relative to the guest VM?
2. What is the default host NER family?
3. Does constructor pack require a mint model?

| Model | Load | Mint | Try | Atoms | Mint | Packet | Works |
|---|---|---|---|---|---|---|---|
| `mlx-community/Qwen3-8B-4bit` (default) | 4.1s | 5.9s | 1 | 10 / 0 dropped | pass | 3/3 grounded 1.0 | **yes** |
| `mlx-community/Qwen3-4B-4bit` | 115s first fetch, then ~4s | 4.0s | 1 | 11 / 0 | pass | 3/3 | **yes** |
| `mlx-community/Qwen3-1.7B-4bit` | 51s fetch | 1.8s | 1 | 7 / 0 | pass (cov 0.67) | 2/3 (missed mint-not-required; mixed two claims) | **partial** |
| `mlx-community/Llama-3.2-1B-Instruct-4bit` | 3–5s | 5–12s | 2 | 6–7 | pass after unwrap + retry | 0/3 (answers INSUFFICIENT or judge JSON fail) | **no** |

## What the self-eval actually did

- **8B / 4B:** one try. Stand-alone sentences, no retry needed.
- **1.7B:** cheap mint score passed; packet Q3 failed because it never
  minted "pack does not require a mint model" and fused mesh-peers with
  GLiNER. Retry would not fire (count/coverage looked fine).
- **1B:** try 1 was quoted `(paraphrasing…)` fragments or
  `Ikonic OS law:` collapse. Form + source-coverage gates forced try 2.
  Unwrap of `{atom, text}` JSON strings recovered real sentences. Packet
  Q&A still failed — 1B cannot use the packet as a judge.

Pack (no MLX) remains the any-machine path. Optional mint default stays
Qwen3-8B-4bit. 4B is a viable smaller SKU on this box. Do not ship 1B as
a constructor mint model.

Re-run: `PYTHONPATH=src python3 scripts/probe_constructor_models.py`
