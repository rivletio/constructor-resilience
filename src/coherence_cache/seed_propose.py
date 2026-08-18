"""Propose utterance_seed / curated NL→CLI rows from accepted atoms.

Law: critique/mint may **propose** Verb FREE maps; humans or CI gate merge.
This module never writes package `utterance_seed.yaml` — only a proposals file.
Dispatch is table-driven (extractors + gates), not an if/else ladder.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from .atoms import REVIEW_ACCEPTED, atom_review_status, atom_text
from .config import CFG, CoherenceConfig

# "say X to /cmd" | "say X or Y to list" | "`/cmd`" near spoken phrasing
_SAY_TO_CMD = re.compile(
    r"(?i)\bsay\s+[\"']?([^\"';.]{3,60}?)[\"']?\s+(?:or\s+[\"']?[^\"';.]{2,40}?[\"']?\s+)?"
    r"(?:to|/)\s*(/[a-z][\w/\-]*(?:\s+[\w\-]+)*)",
)
_SLASH_CMD = re.compile(r"(?<![/\w])(/[a-z][\w/\-]*(?:\s+[\w\-]+){0,4})")


@dataclass(frozen=True)
class SeedProposal:
    phrasing: str
    tool: str
    confidence: float
    reason: str
    source_atom_i: int
    source_text: str
    kind: str = "utterance_seed"
    status: str = "proposed"  # proposed | accepted | rejected (human/CI)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


Extractor = Callable[[int, str, CoherenceConfig], list[SeedProposal]]


def _norm_phrase(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    s = s.strip(" .,;:\"'")
    return s


def _norm_tool(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    if not s.startswith("/"):
        s = "/" + s.lstrip("/")
    return s


def _extract_say_to_cmd(i: int, text: str, cfg: CoherenceConfig) -> list[SeedProposal]:
    out: list[SeedProposal] = []
    for m in _SAY_TO_CMD.finditer(text):
        phrasing = _norm_phrase(m.group(1))
        tool_m = _SLASH_CMD.search(m.group(0))
        if not tool_m:
            continue
        tool = _norm_tool(tool_m.group(1))
        if len(phrasing) < 3 or len(tool) < 2:
            continue
        out.append(
            SeedProposal(
                phrasing=phrasing,
                tool=tool,
                confidence=0.72,
                reason="say…to /cmd pattern in accepted atom",
                source_atom_i=i,
                source_text=text[:240],
            )
        )
    return out


def _extract_imperative_slash(i: int, text: str, cfg: CoherenceConfig) -> list[SeedProposal]:
    """Atoms like: 'list my tasks with /task list' or 'open via /nav home notes'."""
    out: list[SeedProposal] = []
    low = text.lower()
    for m in _SLASH_CMD.finditer(text):
        tool = _norm_tool(m.group(1))
        # take a short window before the slash as candidate phrasing
        start = max(0, m.start() - 48)
        window = _norm_phrase(text[start : m.start()])
        # strip trailing joiners
        window = re.sub(
            r"(?i)^(.*)(\bwith|\bvia|\busing|\bthrough|\brun|\bexecute)\s*$",
            r"\1",
            window,
        ).strip(" ,:-")
        if len(window) < 4 or len(window.split()) > 8:
            continue
        # Prefer windows that look spoken
        if not re.search(r"(?i)\b(show|list|open|focus|say|run|get|what|how)\b", window):
            if "say" not in low:
                continue
        out.append(
            SeedProposal(
                phrasing=window,
                tool=tool,
                confidence=0.55,
                reason="imperative window before slash command",
                source_atom_i=i,
                source_text=text[:240],
            )
        )
    return out


def _extract_calendar_agenda(i: int, text: str, cfg: CoherenceConfig) -> list[SeedProposal]:
    """Domain helper: calendar/agenda atoms → /calendar seeds."""
    low = text.lower()
    if "calendar" not in low and "agenda" not in low:
        return []
    if not re.search(r"(?i)\b(say|list|show|today|schedule)\b", low):
        return []
    proposals = [
        SeedProposal(
            phrasing="show my calendar",
            tool="/calendar",
            confidence=0.68,
            reason="calendar-law atom suggests Verb FREE map",
            source_atom_i=i,
            source_text=text[:240],
        ),
        SeedProposal(
            phrasing="today's agenda",
            tool="/calendar today",
            confidence=0.68,
            reason="calendar-law atom suggests Verb FREE map",
            source_atom_i=i,
            source_text=text[:240],
        ),
    ]
    return proposals


def _extract_task_board(i: int, text: str, cfg: CoherenceConfig) -> list[SeedProposal]:
    low = text.lower()
    if "task" not in low and "board" not in low and "kanban" not in low:
        return []
    if "task list" not in low and "/task" not in low and "board" not in low:
        return []
    return [
        SeedProposal(
            phrasing="show my tasks",
            tool="/task list",
            confidence=0.68,
            reason="tasks-law atom suggests Verb FREE map",
            source_atom_i=i,
            source_text=text[:240],
        ),
        SeedProposal(
            phrasing="list my tasks",
            tool="/task list",
            confidence=0.65,
            reason="tasks-law atom suggests Verb FREE map",
            source_atom_i=i,
            source_text=text[:240],
        ),
    ]


# Ordered extractors — first pass collects; dedupe later by (phrasing, tool).
EXTRACTORS: tuple[Extractor, ...] = (
    _extract_say_to_cmd,
    _extract_imperative_slash,
    _extract_calendar_agenda,
    _extract_task_board,
)


def _gate_seed(p: SeedProposal, cfg: CoherenceConfig) -> bool:
    if not cfg.seed_propose_enabled:
        return False
    if p.confidence < cfg.seed_propose_min_conf:
        return False
    if not p.phrasing or not p.tool.startswith("/"):
        return False
    if len(p.phrasing) > cfg.seed_propose_max_phrase_len:
        return False
    return True


def propose_seeds_from_store(
    store: dict,
    *,
    cfg: CoherenceConfig = CFG,
    accepted_only: bool = True,
) -> list[SeedProposal]:
    """Scan atoms and return gated SeedProposals (never mutates store)."""
    atoms = list(store.get("atoms") or [])
    raw: list[SeedProposal] = []
    for i, atom in enumerate(atoms):
        status = atom_review_status(atom)
        if accepted_only and status not in (REVIEW_ACCEPTED, "edited"):
            continue
        text = atom_text(atom)
        if not text:
            continue
        for extract in EXTRACTORS:
            raw.extend(extract(i, text, cfg))

    # Deduplicate by (phrasing, tool); keep highest confidence
    best: dict[tuple[str, str], SeedProposal] = {}
    for p in raw:
        if not _gate_seed(p, cfg):
            continue
        key = (p.phrasing, p.tool)
        prev = best.get(key)
        if prev is None or p.confidence > prev.confidence:
            best[key] = p
    return sorted(best.values(), key=lambda p: (-p.confidence, p.phrasing))


def proposals_document(
    proposals: list[SeedProposal],
    *,
    topic_id: str | None = None,
    cfg: CoherenceConfig = CFG,
) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "utterance_seed_proposals",
        "status": "pending_human_or_ci",
        "topic_id": topic_id,
        "law": "Proposals only — do not auto-merge into package utterance_seed.yaml",
        "min_conf": cfg.seed_propose_min_conf,
        "count": len(proposals),
        "proposals": [p.as_dict() for p in proposals],
    }
