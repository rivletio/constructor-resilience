"""HOW we make atoms — mint from source text with provenance.

All minted atoms start as ``review.status = pending`` so a human/agent
reviewer can accept, edit, or reject before they harden into the packet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import mlx_backend
from .atoms import (
    ATOM_QUALITY_LAW,
    MINT_SYSTEM,
    atom_text,
    make_atom,
    mint_prompt,
    parse_minted_list,
)


def mint_from_text(
    source_text: str,
    *,
    theme: str | None = None,
    max_atoms: int = 12,
    model: str | None = None,
    existing: list | None = None,
) -> dict[str, Any]:
    """Run local MLX mint; return {atoms: [records], raw, model, prompt}."""
    prompt = mint_prompt(source_text, theme=theme, max_atoms=max_atoms)
    if existing:
        prior = "\n".join(f"- {atom_text(a)}" for a in existing[:40])
        prompt += f"\nAlready in the store (avoid duplicates):\n{prior}\n"

    out = mlx_backend.generate(
        prompt,
        system=MINT_SYSTEM,
        model=model,
        max_tokens=1200,
        temp=0.15,
    )
    texts = parse_minted_list(out["text"])
    # Dedup vs existing + self
    seen = {atom_text(a).lower() for a in (existing or [])}
    records = []
    for t in texts:
        key = t.lower()
        if key in seen or len(t) < 12:
            continue
        seen.add(key)
        records.append(
            make_atom(
                t,
                method="mlx_mint",
                model=out["model"],
                source="source_text",
                source_excerpt=source_text[:400],
                prompt=prompt,
            )
        )
        if len(records) >= max_atoms:
            break
    return {
        "atoms": records,
        "raw": out["text"],
        "model": out["model"],
        "prompt": prompt,
        "quality_law": ATOM_QUALITY_LAW.strip(),
    }


def mint_from_file(path: Path, **kwargs) -> dict[str, Any]:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    return mint_from_text(text, **kwargs)
