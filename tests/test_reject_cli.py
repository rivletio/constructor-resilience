"""Headless back-out: agents can reject an atom without the review UI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence_cache import paths
from coherence_cache.cli import main


@pytest.fixture(autouse=True)
def _reset_root():
    paths._ROOT = None
    yield
    paths._ROOT = None


def _run(root: Path, *argv: str) -> None:
    main(["--root", str(root), *argv])


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _topic(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / ".coherence"
    _run(root, "create", "--title", "Constructor claims", "--use")
    return root, root / "topics" / "constructor-claims"


def test_cli_reject_backs_out_accepted_atom_and_rebuilds_packet(tmp_path, capsys):
    root, topic = _topic(tmp_path)
    _run(root, "add-atom", "Constructors exist for compiling a resilient packet.", "--accepted")
    _run(
        root,
        "add-atom",
        "Perpetual motion of the second kind is possible in a closed cycle.",
        "--accepted",
    )
    _run(root, "search", "--greedy", "--max-size", "6")
    packet_before = _load(topic / "packet.json")
    assert any("Perpetual motion" in a for a in packet_before["atoms"])

    capsys.readouterr()
    _run(
        root,
        "reject",
        "1",
        "--reason",
        "claimed possibility does not hold; the task is impossible",
    )
    out = capsys.readouterr().out
    assert "rejected" in out.lower() or "backed out" in out.lower()

    store = _load(topic / "atoms.json")
    assert len(store["atoms"]) == 2
    bad = store["atoms"][1]
    assert bad["review"]["status"] == "rejected"
    assert bad["review"]["previous_status"] == "accepted"
    assert bad["review"]["backed_out"] is True
    assert "does not hold" in bad["review"]["notes"]
    assert "Perpetual motion" in bad["text"]

    packet = _load(topic / "packet.json")
    assert not any("Perpetual motion" in a for a in packet["atoms"])
    assert any("resilient packet" in a for a in packet["atoms"])
    # Indices in the store stay put; packet atom_indices must not point at the rejected row.
    assert 1 not in (packet.get("atom_indices") or [])


def test_cli_backout_alias_and_text_guard(tmp_path):
    root, topic = _topic(tmp_path)
    _run(root, "add-atom", "Task T is possible under protocol P.", "--accepted")
    with pytest.raises(SystemExit):
        _run(
            root,
            "backout",
            "0",
            "--text",
            "some other claim",
            "--reason",
            "ill-defined",
        )
    _run(
        root,
        "backout",
        "0",
        "--text",
        "Task T is possible under protocol P.",
        "--reason",
        "atom was not defined correctly",
    )
    store = _load(topic / "atoms.json")
    assert store["atoms"][0]["review"]["status"] == "rejected"


def test_cli_reject_requires_reason(tmp_path):
    root, _topic_dir = _topic(tmp_path)
    _run(root, "add-atom", "A durable claim.", "--accepted")
    with pytest.raises(SystemExit):
        _run(root, "reject", "0")


def test_cli_set_review_can_restore_backed_out_atom(tmp_path):
    root, topic = _topic(tmp_path)
    _run(root, "add-atom", "Task T is possible.", "--accepted")
    _run(root, "reject", "0", "--reason", "need to recheck the constructor")
    _run(root, "set-review", "0", "--status", "accepted", "--notes", "constructor confirmed")
    store = _load(topic / "atoms.json")
    assert store["atoms"][0]["review"]["status"] == "accepted"
    assert "Task T is possible." in store["atoms"][0]["text"]
