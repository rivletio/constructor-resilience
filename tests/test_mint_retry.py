"""Mint self-eval + retry (no live MLX)."""

from coherence_cache.config import CoherenceConfig
from coherence_cache.mint import mint_from_text_retry, score_mint


SOURCE = """
LLM APIs never run in the guest VM. Inference uses host native Metal or CUDA,
then approved mesh peers, then user-gated cloud.
GLiNER2 large-v1 (340M) is the host NER default; heuristic NER is tests only.
Constructor pack writes durable claims without an extra mint model.
"""

CFG = CoherenceConfig(mint_min_atoms=3, mint_max_attempts=3, mint_max_drop_frac=0.5)


def test_score_mint_too_few():
    s = score_mint({"atoms": [{"text": "a"}], "dropped": []}, cfg=CFG)
    assert s["ok"] is False
    assert "too-few-atoms" in s["reasons"][0]


def test_score_mint_ok():
    atoms = [{"text": f"claim {i} " + SOURCE[10:40]} for i in range(3)]
    s = score_mint({"atoms": atoms, "dropped": []}, cfg=CFG)
    assert s["ok"] is True
    assert s["n_atoms"] == 3


def test_score_mint_rejects_duplicates():
    one = "LLM APIs never run in the guest VM."
    s = score_mint({"atoms": [{"text": one}] * 4, "dropped": []}, cfg=CFG)
    assert s["ok"] is False
    assert "too-few-unique" in s["reasons"][0]


def test_atom_form_rejects_paraphrase_meta():
    from coherence_cache.mint import atom_form_reason

    assert atom_form_reason(
        '"Inference uses host native Metal or CUDA" (paraphrasing a statement about inference)'
    ) == "meta-not-claim"
    assert atom_form_reason("LLM APIs never run in the guest VM.") is None
    assert (
        atom_form_reason("Ikonic OS law: " * 6 + "LLM APIs never run in the guest VM.")
        == "repetition"
    )


def test_score_mint_source_coverage():
    s = score_mint(
        {"atoms": [{"text": "LLM APIs never run in the guest VM."}], "dropped": []},
        source_text=SOURCE,
        cfg=CFG,
    )
    assert s["ok"] is False
    assert any("source-coverage" in r for r in s["reasons"])


def test_retry_succeeds_on_second_attempt(monkeypatch):
    calls = {"n": 0}

    def fake_generate(prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # invention + one grounded
            return {
                "text": '["Mars encrypts every vault automatically overnight.", '
                '"LLM APIs never run in the guest VM."]',
                "model": "fake",
                "backend": "test",
            }
        return {
            "text": json_atoms(),
            "model": "fake",
            "backend": "test",
        }

    def json_atoms():
        return (
            '["LLM APIs never run in the guest VM.",'
            ' "Inference uses host native Metal or CUDA then approved mesh peers.",'
            ' "GLiNER2 large-v1 is the host NER default.",'
            ' "Constructor pack writes durable claims without an extra mint model."]'
        )

    import coherence_cache.mlx_backend as mlx

    monkeypatch.setattr(mlx, "generate", fake_generate)
    result = mint_from_text_retry(SOURCE, attempts=3, cfg=CFG, model="fake")
    assert result["attempt"] == 2
    assert result["score"]["ok"] is True
    assert len(result["atoms"]) >= 3
    assert calls["n"] == 2
    assert "Previous attempt" in result["prompt"]


def test_retry_exhausted_still_returns_last(monkeypatch):
    import coherence_cache.mlx_backend as mlx

    monkeypatch.setattr(
        mlx,
        "generate",
        lambda *a, **k: {
            "text": '["Invented claim about quantum bananas on Mars."]',
            "model": "fake",
            "backend": "test",
        },
    )
    result = mint_from_text_retry(SOURCE, attempts=2, cfg=CFG, model="fake")
    assert result["attempt"] == 2
    assert result["score"]["ok"] is False
    assert result["atoms"] == []
