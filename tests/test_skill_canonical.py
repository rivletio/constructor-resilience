"""Canonical skill lives next to the functions. Host packages must not fork it."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT / "skills" / "constructor-resilience" / "SKILL.md"


def test_canonical_skill_is_the_protocol():
    text = CANON.read_text(encoding="utf-8")
    assert "license: AGPL-3.0-or-later" in text
    assert "lookup" in text
    assert "JOIN" in text
    assert "<SENTENCE>" in text
    assert "JEPA" not in text
    assert "GLiNER" not in text


def test_skill_package_does_not_drift_when_present():
    sibling = ROOT.parent / "constructor-resilience-skill" / "skills" / "constructor-resilience" / "SKILL.md"
    if not sibling.exists():
        return
    assert sibling.read_text(encoding="utf-8") == CANON.read_text(encoding="utf-8")
