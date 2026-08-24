"""HOW we make atoms — mint from source text with provenance.

All minted atoms start as ``review.status = pending`` so a human/agent
reviewer can accept, edit, or reject before they harden into the packet.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import mlx_backend
from .atoms import (
    ATOM_QUALITY_LAW,
    MINT_SYSTEM,
    atom_text,
    content_tokens,
    grounding_score,
    is_grounded,
    make_atom,
    mint_prompt,
    parse_minted_list,
)
from .config import CFG, CoherenceConfig

_META_CLAIM = re.compile(
    r"(?is)\(paraphras|\bas a (statement|claim|fact)\b"
    r"|\bthis (session|conversation|chat)\b"
    r"|^ok(ay)?[,.]?\s"
)


def atom_form_reason(text: str) -> str | None:
    """Cheap form gate so quoted-fragment / meta drafts retry."""
    t = (text or "").strip()
    if len(t) < 24:
        return "too-short"
    if _META_CLAIM.search(t):
        return "meta-not-claim"
    if t.lstrip().startswith(("{", "[")):
        return "not-a-sentence"
    if t.startswith('"') and t.count('"') >= 2:
        inner = t.split('"')[1].strip()
        if len(inner) < 40:
            return "quoted-fragment"
    head = t[:20].strip()
    if len(head) >= 8 and t.lower().count(head.lower()) >= 3:
        return "repetition"
    return None


def _norm_claim(text: str) -> str:
    t = re.sub(r"\(paraphras[^)]*\)", "", text or "", flags=re.I)
    t = t.strip().strip('"').strip()
    return re.sub(r"\s+", " ", t.lower())


def mint_from_text(
    source_text: str,
    *,
    theme: str | None = None,
    max_atoms: int | None = None,
    model: str | None = None,
    existing: list | None = None,
    min_grounding: float | None = None,
    extra_prompt: str | None = None,
    cfg: CoherenceConfig = CFG,
) -> dict[str, Any]:
    """Run local MLX mint; return {atoms, dropped, raw, model, prompt}.

    Post-filter drops invented claims that fail the grounding gate so
    review starts from source-faithful candidates.
    """
    max_atoms = cfg.mint_max_atoms if max_atoms is None else max_atoms
    min_grounding = (
        cfg.mint_min_grounding if min_grounding is None else min_grounding
    )
    prompt = mint_prompt(source_text, theme=theme, max_atoms=max_atoms)
    if extra_prompt:
        prompt += extra_prompt
    if existing:
        prior = "\n".join(f"- {atom_text(a)}" for a in existing[:40])
        prompt += f"\nAlready in the store (avoid duplicates):\n{prior}\n"

    out = mlx_backend.generate(
        prompt,
        system=MINT_SYSTEM,
        model=model or cfg.mlx_model,
        max_tokens=cfg.mint_max_tokens,
        temp=cfg.mint_temp,
    )
    texts = parse_minted_list(out["text"])
    seen = {atom_text(a).lower() for a in (existing or [])}
    records = []
    dropped = []
    for t in texts:
        key = t.lower()
        if key in seen or len(t) < 12:
            continue
        g = grounding_score(t, source_text)
        if not is_grounded(t, source_text, min_ratio=min_grounding):
            dropped.append({"text": t, "reason": "ungrounded", "grounding": round(g, 3)})
            continue
        form = atom_form_reason(t)
        if form:
            dropped.append({"text": t, "reason": form, "grounding": round(g, 3)})
            continue
        seen.add(key)
        rec = make_atom(
            t,
            method="mlx_mint",
            model=out["model"],
            source="source_text",
            source_excerpt=source_text[:400],
            prompt=prompt,
            extra={"grounding": round(g, 3)},
        )
        records.append(rec)
        if len(records) >= max_atoms:
            break
    return {
        "atoms": records,
        "dropped": dropped,
        "raw": out["text"],
        "model": out["model"],
        "prompt": prompt,
        "quality_law": ATOM_QUALITY_LAW.strip(),
        "min_grounding": min_grounding,
    }


def score_mint(
    result: dict[str, Any],
    *,
    min_atoms: int | None = None,
    max_drop_frac: float | None = None,
    source_text: str | None = None,
    min_source_cov: float | None = None,
    cfg: CoherenceConfig = CFG,
) -> dict[str, Any]:
    """Cheap self-eval (no extra generate). Smaller models retry on fail."""
    min_atoms = cfg.mint_min_atoms if min_atoms is None else min_atoms
    max_drop_frac = (
        cfg.mint_max_drop_frac if max_drop_frac is None else max_drop_frac
    )
    min_source_cov = (
        cfg.mint_min_source_cov if min_source_cov is None else min_source_cov
    )
    atoms = result.get("atoms") or []
    n = len(atoms)
    d = len(result.get("dropped") or [])
    total = n + d
    drop_frac = (d / total) if total else 1.0
    unique = {
        _norm_claim(atom_text(a) if not isinstance(a, str) else a) for a in atoms
    }
    unique.discard("")
    n_unique = len(unique)
    reasons: list[str] = []
    if n < min_atoms:
        reasons.append(f"too-few-atoms:{n}<{min_atoms}")
    elif n_unique < min_atoms:
        reasons.append(f"too-few-unique:{n_unique}<{min_atoms}")
    if drop_frac > max_drop_frac:
        reasons.append(f"too-many-dropped:{d}/{total}")
    source_cov = None
    if source_text:
        src = content_tokens(source_text)
        blob: set[str] = set()
        for a in atoms:
            blob |= content_tokens(atom_text(a) if not isinstance(a, str) else a)
        source_cov = round((len(src & blob) / len(src)) if src else 0.0, 3)
        if source_cov < min_source_cov:
            reasons.append(f"source-coverage:{source_cov}<{min_source_cov}")
    return {
        "ok": not reasons,
        "n_atoms": n,
        "n_dropped": d,
        "n_unique": n_unique,
        "drop_frac": round(drop_frac, 3),
        "source_cov": source_cov,
        "reasons": reasons,
    }


def mint_from_text_retry(
    source_text: str,
    *,
    theme: str | None = None,
    max_atoms: int | None = None,
    model: str | None = None,
    existing: list | None = None,
    min_grounding: float | None = None,
    attempts: int | None = None,
    cfg: CoherenceConfig = CFG,
) -> dict[str, Any]:
    """Mint, self-score, retry with dropped-claim feedback (few tries)."""
    attempts = cfg.mint_max_attempts if attempts is None else max(1, attempts)
    last: dict[str, Any] | None = None
    extra = ""
    for i in range(attempts):
        result = mint_from_text(
            source_text,
            theme=theme,
            max_atoms=max_atoms,
            model=model,
            existing=existing,
            min_grounding=min_grounding,
            extra_prompt=extra or None,
            cfg=cfg,
        )
        scored = score_mint(result, source_text=source_text, cfg=cfg)
        result["score"] = scored
        result["attempt"] = i + 1
        result["attempts"] = attempts
        last = result
        if scored["ok"]:
            return result
        drops = result.get("dropped") or []
        drop_lines = "\n".join(
            f"- {d.get('text','')[:160]} ({d.get('reason')} g={d.get('grounding')})"
            for d in drops[:8]
        )
        extra = (
            f"\nPrevious attempt {i + 1} failed self-eval: {', '.join(scored['reasons'])}.\n"
            f"Kept {scored['n_atoms']} grounded atoms; dropped {scored['n_dropped']}.\n"
            f"{drop_lines}\n"
            "Try again. Return ONLY a JSON array of strings. "
            "Every atom MUST be a stand-alone full sentence from the SOURCE. "
            "Do not wrap in quotes. Do not add (paraphrasing...). "
            "Do not invent. Prefer 3–8 durable constraints.\n"
        )
    return last or {}


def mint_from_file(path: Path, **kwargs) -> dict[str, Any]:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    return mint_from_text(text, **kwargs)
