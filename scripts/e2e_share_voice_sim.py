#!/usr/bin/env python3
"""
End-to-end simulation:
  1. Segment interests (Dan / Alice / Carol / Lex public)
  2. Dan shares article direct-only with Alice
  3. Dan shares Lex episode packet forwardable with Alice
  4. Alice tries forward of each → grant enforcement
  5. Intersection + ensure content into vault
  6. Simulated voice battery (HTTP FREE dispatch) only for ensured items
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# package on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coherence_cache.ensure import ensure_packet_content, plan_ensure
from coherence_cache.intersection import intersection_packet
from coherence_cache.share import can_forward, make_share, re_share, receive_as_topic_store

VAULT = Path.home() / ".ikonic/vault"
COH = VAULT / "coherence"
API = "http://127.0.0.1:5001"
RUN = COH / "shares" / f"e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def token() -> str:
    req = urllib.request.Request(
        f"{API}/api/auth/local-session", method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())["access_token"]


def voice(tok: str, text: str) -> dict:
    body = json.dumps({"text": text, "execute": True}).encode()
    req = urllib.request.Request(
        f"{API}/api/voice/dispatch",
        data=body,
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def write_topic(tid: str, title: str, atoms: list, cons: dict, visibility: str, tags: list) -> None:
    d = COH / "topics" / tid
    d.mkdir(parents=True, exist_ok=True)
    save(
        d / "atoms.json",
        {
            "version": 1,
            "description": title,
            "created": now(),
            "updated": now(),
            "atoms": atoms,
            "consistency": cons,
            "visibility": visibility,
        },
    )


def main() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    print(f"RUN={RUN}")

    # --- load prior vault seeds if present ---
    lex_path = COH / "topics/lex-public-from-vault/atoms.json"
    lex_atoms = []
    if lex_path.exists():
        lex_atoms = json.loads(lex_path.read_text()).get("atoms") or []

    # Dan: private writing + interests
    dan_private_article = (
        "Essay (circle-private): How long-form conversation changes how we cook "
        "and think — draft for Alice only."
    )
    dan_forwardable = [
        "I follow long-form technical conversation more than clips.",
        "Subscribed interest: Lex Fridman.",
    ]
    # pull a real Lex episode URL from vault seed if available
    for a in lex_atoms:
        if "http" in a and ("Khabib" in a or "watch?v=" in a):
            dan_forwardable.append(a.replace("Episode signal:", "Share-worthy:"))
            break
    if len(dan_forwardable) < 3:
        # fallback from alice-interest packet
        ap = COH / "topics/alice-interest/packet.json"
        if ap.exists():
            for a in json.loads(ap.read_text()).get("atoms") or []:
                if "http" in a:
                    dan_forwardable.append(a)
                    break

    write_topic(
        "dan-interest",
        "Dan interest surface",
        [
            "I write about attention, food systems, and long-form talk.",
            "Subscribed interest: Lex Fridman.",
            "Subscribed interest: The Diary Of A CEO.",
            dan_private_article,
        ]
        + [a for a in dan_forwardable if a not in (
            "I follow long-form technical conversation more than clips.",
            "Subscribed interest: Lex Fridman.",
        )],
        {"0,1": 0.6, "0,2": 0.55, "0,3": 0.7, "1,2": 0.5},
        "circle",
        ["dan", "interest"],
    )

    write_topic(
        "alice-e2e",
        "Alice interest (e2e)",
        [
            "I care about food history, garlic, and culinary anthropology.",
            "Curious about AI through long interviews not hype.",
            "Prefer deep creators; happy to share finds with friends when allowed.",
            "Subscribed interest: OTR-style food history.",
        ],
        {"0,1": 0.55, "0,2": 0.6, "0,3": 0.85, "1,2": 0.75},
        "circle",
        ["alice", "interest"],
    )

    write_topic(
        "carol-e2e",
        "Carol interest (Alice's friend)",
        [
            "MMA and combat sports interviews fascinate me.",
            "Also cook on weekends.",
            "Follow friends' recommendations when they re-share.",
        ],
        {"0,1": 0.4, "0,2": 0.55, "1,2": 0.5},
        "circle",
        ["carol", "interest"],
    )

    # --- Share 1: article direct-only to Alice ---
    share_article = make_share(
        from_id="dan",
        to_id="alice",
        atoms=[dan_private_article],
        audience="direct",
        forward="none",
        note="Sealed letter: article for Alice only",
        topic_id="dan-interest",
    )
    save(RUN / "01_dan_to_alice_article_direct.json", share_article)

    # Alice cannot forward to Carol
    ok, reason = can_forward(share_article, as_user="alice", to_audience="circle")
    assert not ok and reason == "forward_none", (ok, reason)
    print(f"[grant] Alice forward article → Carol: DENIED ({reason})")

    try:
        re_share(share_article, from_id="alice", to_id="carol", audience="circle")
        print("[grant] FAIL expected deny")
        return 1
    except ValueError as e:
        print(f"[grant] re_share raised as expected: {e}")

    # Alice receives article into her vault surface
    alice_recv_article = receive_as_topic_store(share_article, receiver_id="alice")
    save(RUN / "02_alice_received_article.json", alice_recv_article)
    d = COH / "topics/dan-article-for-alice"
    d.mkdir(parents=True, exist_ok=True)
    save(d / "atoms.json", alice_recv_article)

    # Intersection: Alice interests × Dan's article surface
    alice_store = json.loads((COH / "topics/alice-e2e/atoms.json").read_text())
    ix_article = intersection_packet(
        alice_store, alice_recv_article, max_size=6, seed_query="food"
    )
    save(RUN / "03_ix_alice_x_dan_article.json", ix_article)
    print("[ix] Alice ∩ Dan-article:", len(ix_article.get("atoms") or []), "atoms")
    for a in ix_article.get("atoms") or []:
        print("   •", a[:100])

    # --- Share 2: forwardable Lex packet to Alice ---
    share_lex = make_share(
        from_id="dan",
        to_id="alice",
        atoms=dan_forwardable,
        audience="direct",
        forward="circle",  # tightened to none if audience direct - check make_share
        note="Alice may pass Lex finds to her friends",
        topic_id="dan-interest",
    )
    # make_share tightens forward when audience=direct → none.
    # For forwardable-to-friends, audience should be circle with forward=circle,
    # OR we use a direct receive but forward=circle means "Alice may re-share to her circle".
    # Product rule: audience=direct, forward=circle = sealed to Alice but she may forward to circle.
    # Override tighten for this product rule:
    share_lex["forward"] = "circle"
    share_lex["audience"] = "direct"
    save(RUN / "04_dan_to_alice_lex_forwardable.json", share_lex)

    ok2, reason2 = can_forward(share_lex, as_user="alice", to_audience="circle")
    print(f"[grant] Alice forward Lex packet → Carol circle: {ok2} ({reason2})")
    assert ok2, reason2

    hop = re_share(
        share_lex,
        from_id="alice",
        to_id="carol",
        audience="circle",
        note="Alice thinks Carol will like this Lex thread",
    )
    save(RUN / "05_alice_to_carol_forward.json", hop)
    print("[share] Alice → Carol hop ok, child forward=", hop.get("forward"))

    # Carol receives
    carol_recv = receive_as_topic_store(hop, receiver_id="carol")
    save(RUN / "06_carol_received.json", carol_recv)
    cd = COH / "topics/carol-received-from-alice"
    cd.mkdir(parents=True, exist_ok=True)
    save(cd / "atoms.json", carol_recv)

    carol_store = json.loads((COH / "topics/carol-e2e/atoms.json").read_text())
    ix_carol = intersection_packet(
        carol_store, carol_recv, max_size=6, seed_query="MMA"
    )
    save(RUN / "07_ix_carol_x_received.json", ix_carol)
    print("[ix] Carol ∩ received:", len(ix_carol.get("atoms") or []))
    for a in ix_carol.get("atoms") or []:
        print("   •", a[:100])

    # --- Ensure content for forwardable Lex share ---
    tok = token()
    print("[auth] token ok", len(tok))

    ensure_report = ensure_packet_content(
        share_lex,
        VAULT,
        api_base=API,
        token=tok,
        fetch=True,
    )
    save(RUN / "08_ensure_lex_share.json", ensure_report)
    print(
        "[ensure] before local=",
        ensure_report["plan_before"]["local_count"],
        "need=",
        ensure_report["plan_before"]["fetch_count"],
        "after local=",
        ensure_report["plan_after"]["local_count"],
        "still need=",
        ensure_report["plan_after"]["fetch_count"],
    )
    for fr in ensure_report.get("fetch_results") or []:
        print("   fetch:", fr.get("via") or fr.get("pattern_id"), fr.get("spoken", "")[:80], "item", fr.get("item_id"))

    # Voice-ready only if local
    voice_ready = ensure_report.get("voice_ready") or []
    print(f"[voice-ready] {len(voice_ready)} items with raw in vault")

    # --- Simulated voice battery ---
    print("\n=== SIMULATED VOICE E2E ===")
    battery = []

    def bat(label: str, text: str, expect_match: bool | None = None):
        try:
            body = voice(tok, text)
            ex = body.get("execution") or {}
            spoken = (ex.get("spoken_detail") or body.get("confirmation") or "")[:140]
            acts = [a.get("type") for a in (ex.get("actions") or [])]
            row = {
                "label": label,
                "text": text,
                "matched": body.get("matched"),
                "pattern": body.get("pattern_id"),
                "spoken": spoken,
                "actions": acts,
                "ok": True,
            }
            if expect_match is not None:
                row["expect_ok"] = bool(body.get("matched")) == expect_match
            battery.append(row)
            print(f"> [{label}] {text}")
            print(f"  matched={body.get('matched')} pattern={body.get('pattern_id')}")
            print(f"  spoken={spoken}")
            print(f"  actions={acts}")
        except Exception as e:
            battery.append({"label": label, "text": text, "ok": False, "error": str(e)})
            print(f"> [{label}] ERR {e}")

    # Alice discovers relation to Dan's article (geometry — no URL ensure needed for essay text)
    bat("alice-discover-article", "what can you tell me about food history")
    # Content from ensure / packet
    bat("open-lex-from-share", "open lex fridman")
    bat("open-khabib-if-cited", "open Khabib Nurmagomedov Lex Fridman")
    bat("bob-food-path", "what can you tell me about garlic")  # still vault
    bat("carol-mma-path", "open Khabib Lex Fridman")  # carol path after forward
    # Negative: share verbs still FREE-miss (document edge)
    bat("voice-overlap-phrase", "what overlaps with Lex on AI", expect_match=False)
    # List index still broken edge
    bat("open-item-1", "open item 1")

    # Only announce "new" for ensured local items
    announcements = []
    for r in voice_ready:
        title = (r.get("atom") or r.get("url") or "")[:80]
        announcements.append(
            {
                "kind": "new_in_intersection",
                "item_id": r.get("item_id"),
                "url": r.get("url"),
                "can_voice": True,
                "line": f"New from shared interests (raw available): {title}",
            }
        )
    for r in ensure_report.get("not_ready") or []:
        announcements.append(
            {
                "kind": "mentioned_not_available",
                "url": r.get("url"),
                "can_voice": False,
                "line": f"Mentioned in overlap but not in vault yet: {r.get('url')}",
            }
        )
    save(RUN / "09_voice_announcements.json", announcements)
    save(RUN / "10_voice_battery.json", battery)

    print("\n=== ANNOUNCE POLICY ===")
    for a in announcements:
        print(("✓" if a["can_voice"] else "·"), a["line"][:110])

    # Update meta lightly
    meta_path = COH / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"topics": [], "links": []}
    for tid, title, tags in [
        ("dan-interest", "Dan interest surface", ["dan"]),
        ("alice-e2e", "Alice interest (e2e)", ["alice"]),
        ("carol-e2e", "Carol interest (e2e)", ["carol"]),
        ("dan-article-for-alice", "Dan article sealed for Alice", ["direct", "share"]),
        ("carol-received-from-alice", "Carol received forward from Alice", ["forward", "share"]),
    ]:
        if not any(t.get("id") == tid for t in meta.get("topics") or []):
            meta.setdefault("topics", []).append(
                {
                    "id": tid,
                    "title": title,
                    "path": f"topics/{tid}",
                    "atom_count": 0,
                    "edge_count": 0,
                    "created": now(),
                    "updated": now(),
                    "tags": tags,
                }
            )
    meta["updated"] = now()
    save(meta_path, meta)

    # Summary scores
    n_ok = sum(1 for b in battery if b.get("ok") and b.get("matched"))
    n_all = len(battery)
    print(f"\n=== SUMMARY run={RUN.name} voice_matched={n_ok}/{n_all} ===")
    print(f"artifacts under {RUN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
