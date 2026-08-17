"""Local MLX generation for atom mint + query eval.

Default model: ``mlx-community/Qwen3-8B-4bit`` (Qwen3 8B on Apple Silicon).

Env:
  COHERENCE_MLX_MODEL   — HF repo id (default above)
  COHERENCE_MLX_MAX_TOKENS — default 1024
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

DEFAULT_MODEL = os.environ.get(
    "COHERENCE_MLX_MODEL",
    "mlx-community/Qwen3-8B-4bit",
)


def model_id() -> str:
    return os.environ.get("COHERENCE_MLX_MODEL", DEFAULT_MODEL)


@lru_cache(maxsize=2)
def _load(model_name: str) -> tuple[Any, Any]:
    try:
        from mlx_lm import load
    except ImportError as e:
        raise RuntimeError(
            "mlx_lm not installed. On Apple Silicon: pip install mlx-lm"
        ) from e
    return load(model_name)


def available() -> bool:
    try:
        import mlx_lm  # noqa: F401

        return True
    except ImportError:
        return False


def generate(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int | None = None,
    temp: float = 0.2,
    model: str | None = None,
) -> dict:
    """Generate text; returns {text, model, backend}."""
    mid = model or model_id()
    max_tokens = max_tokens or int(os.environ.get("COHERENCE_MLX_MAX_TOKENS", "1024"))
    model_obj, tokenizer = _load(mid)

    from mlx_lm import generate as mlx_generate
    from mlx_lm.sample_utils import make_sampler

    # Prefer chat template when available (Qwen3)
    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            formatted = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                # Qwen3: disable long thinking for structured mint/eval
                enable_thinking=False,
            )
        except TypeError:
            formatted = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
    else:
        formatted = (f"{system}\n\n{prompt}" if system else prompt)

    text = mlx_generate(
        model_obj,
        tokenizer,
        prompt=formatted,
        max_tokens=max_tokens,
        verbose=False,
        sampler=make_sampler(temp=temp),
    )
    return {"text": text, "model": mid, "backend": "mlx_lm"}


def ensure_model(model: str | None = None) -> str:
    """Load (and download if needed) the configured model; return id."""
    mid = model or model_id()
    _load(mid)
    return mid
