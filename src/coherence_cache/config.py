"""Central knobs — env overrides, no magic numbers scattered in call sites."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields
from typing import Any


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_str(key: str, default: str) -> str:
    return os.environ.get(key) or default


@dataclass(frozen=True)
class CoherenceConfig:
    """Single source for mint / critique / eval / MLX defaults."""

    mlx_model: str = "mlx-community/Qwen3-8B-4bit"
    mlx_max_tokens: int = 1024
    mint_temp: float = 0.1
    mint_max_tokens: int = 1200
    mint_min_grounding: float = 0.55
    mint_max_atoms: int = 12
    mint_min_atoms: int = 3
    mint_max_attempts: int = 3
    mint_max_drop_frac: float = 0.5
    mint_min_source_cov: float = 0.45
    critique_temp: float = 0.05
    critique_max_tokens: int = 1500
    critique_accept_min_conf: float = 0.80
    critique_reject_min_conf: float = 0.75
    critique_edit_min_conf: float = 0.85
    critique_min_grounding: float = 0.55
    critique_fallback_conf: float = 0.40
    critique_force_reject_conf: float = 0.70
    eval_temp: float = 0.1
    eval_judge_temp: float = 0.0
    eval_max_tokens: int = 400
    eval_judge_max_tokens: int = 200
    eval_packet_size: int = 8
    eval_seed_k: int = 3
    review_host: str = "127.0.0.1"
    review_port: int = 8765
    source_excerpt_chars: int = 800
    reason_max_chars: int = 400

    @classmethod
    def from_env(cls) -> CoherenceConfig:
        return cls(
            mlx_model=_env_str("COHERENCE_MLX_MODEL", cls.mlx_model),
            mlx_max_tokens=_env_int("COHERENCE_MLX_MAX_TOKENS", cls.mlx_max_tokens),
            mint_temp=_env_float("COHERENCE_MINT_TEMP", cls.mint_temp),
            mint_max_tokens=_env_int("COHERENCE_MINT_MAX_TOKENS", cls.mint_max_tokens),
            mint_min_grounding=_env_float(
                "COHERENCE_MINT_MIN_GROUNDING", cls.mint_min_grounding
            ),
            mint_max_atoms=_env_int("COHERENCE_MINT_MAX_ATOMS", cls.mint_max_atoms),
            mint_min_atoms=_env_int("COHERENCE_MINT_MIN_ATOMS", cls.mint_min_atoms),
            mint_max_attempts=_env_int(
                "COHERENCE_MINT_MAX_ATTEMPTS", cls.mint_max_attempts
            ),
            mint_max_drop_frac=_env_float(
                "COHERENCE_MINT_MAX_DROP_FRAC", cls.mint_max_drop_frac
            ),
            mint_min_source_cov=_env_float(
                "COHERENCE_MINT_MIN_SOURCE_COV", cls.mint_min_source_cov
            ),
            critique_temp=_env_float("COHERENCE_CRITIQUE_TEMP", cls.critique_temp),
            critique_max_tokens=_env_int(
                "COHERENCE_CRITIQUE_MAX_TOKENS", cls.critique_max_tokens
            ),
            critique_accept_min_conf=_env_float(
                "COHERENCE_CRITIQUE_ACCEPT_MIN_CONF", cls.critique_accept_min_conf
            ),
            critique_reject_min_conf=_env_float(
                "COHERENCE_CRITIQUE_REJECT_MIN_CONF", cls.critique_reject_min_conf
            ),
            critique_edit_min_conf=_env_float(
                "COHERENCE_CRITIQUE_EDIT_MIN_CONF", cls.critique_edit_min_conf
            ),
            critique_min_grounding=_env_float(
                "COHERENCE_CRITIQUE_MIN_GROUNDING", cls.critique_min_grounding
            ),
            eval_packet_size=_env_int(
                "COHERENCE_EVAL_PACKET_SIZE", cls.eval_packet_size
            ),
            eval_seed_k=_env_int("COHERENCE_EVAL_SEED_K", cls.eval_seed_k),
            review_host=_env_str("COHERENCE_REVIEW_HOST", cls.review_host),
            review_port=_env_int("COHERENCE_REVIEW_PORT", cls.review_port),
        )

    def replace(self, **kwargs: Any) -> CoherenceConfig:
        base = asdict(self)
        base.update({k: v for k, v in kwargs.items() if v is not None})
        allowed = {f.name for f in fields(self)}
        return CoherenceConfig(**{k: base[k] for k in allowed})


# Process-wide default (tests may replace via monkeypatch / explicit cfg args).
CFG = CoherenceConfig.from_env()
