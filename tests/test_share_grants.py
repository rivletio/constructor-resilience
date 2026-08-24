"""Grant enforcement: sealed vs forwardable shares."""

from coherence_cache.share import can_forward, make_share, re_share


def test_direct_forward_none_blocks_reshare():
    s = make_share(
        from_id="dan",
        to_id="alice",
        atoms=["Private essay for Alice only."],
        audience="direct",
        forward="none",
    )
    # make_share may already force forward none for direct
    s["forward"] = "none"
    ok, reason = can_forward(s, as_user="alice", to_audience="circle")
    assert not ok
    assert reason == "forward_none"
    try:
        re_share(s, from_id="alice", to_id="carol", audience="circle")
        assert False, "should raise"
    except ValueError as e:
        assert "forward_none" in str(e)


def test_forwardable_allows_circle_hop_no_escalate():
    s = make_share(
        from_id="dan",
        to_id="alice",
        atoms=["Lex episode https://www.youtube.com/watch?v=l6USUAIKJls"],
        audience="direct",
        forward="circle",
    )
    # product rule: direct + forward=circle means Alice may re-share to circle
    s["forward"] = "circle"
    s["audience"] = "direct"
    ok, reason = can_forward(s, as_user="alice", to_audience="circle")
    assert ok, reason
    hop = re_share(s, from_id="alice", to_id="carol", audience="circle")
    assert hop["from"] == "alice"
    assert hop["to"] == "carol"
    # cannot escalate to public
    ok_pub, reason_pub = can_forward(s, as_user="alice", to_audience="public")
    assert not ok_pub
    assert "public" in reason_pub


def test_receive_does_not_prefix_claim_text():
    from coherence_cache.share import make_share, receive_as_topic_store

    s = make_share(
        from_id="dan",
        to_id="alice",
        atoms=["Packets are the share unit, not transcripts."],
        audience="circle",
        forward="none",
    )
    store = receive_as_topic_store(s, receiver_id="alice")
    assert store["atoms"]
    text = store["atoms"][0]["text"] if isinstance(store["atoms"][0], dict) else store["atoms"][0]
    assert text.startswith("Packets are the share unit")
    assert "[from:" not in text
    assert store["share"]["from"] == "dan"


def test_content_refs_extracted():
    s = make_share(
        from_id="dan",
        to_id="alice",
        atoms=["See https://www.youtube.com/watch?v=abcdefghijk for more"],
        audience="circle",
        forward="none",
    )
    refs = s.get("content_refs") or []
    assert len(refs) == 1
    assert refs[0].get("youtube_video_id") == "abcdefghijk"


def test_youtube_timestamp_parsed_from_url_and_atom_refs():
    from coherence_cache.refs_util import extract_references, parse_youtube_url
    from coherence_cache.share import extract_content_refs

    yt = parse_youtube_url("https://www.youtube.com/watch?v=qCbfTN-caFI&t=3033")
    assert yt["youtube_video_id"] == "qCbfTN-caFI"
    assert yt["t"] == 3033
    assert yt["t_label"] == "50:33"
    assert yt["url"].endswith("t=3033")

    found = extract_references("clip https://youtu.be/qCbfTN-caFI?t=48m24s")
    kinds = {r["kind"] for r in found}
    assert "youtube_video" in kinds
    vid = next(r for r in found if r["kind"] == "youtube_video")
    assert vid["t"] == 48 * 60 + 24

    atom = {
        "text": "A good conversation requires duration.",
        "refs": [
            {
                "kind": "youtube_video",
                "youtube_video_id": "qCbfTN-caFI",
                "t": 3033,
                "url": "https://www.youtube.com/watch?v=qCbfTN-caFI&t=3033",
            }
        ],
    }
    refs = extract_content_refs([atom])
    assert refs[0]["youtube_video_id"] == "qCbfTN-caFI"
    assert refs[0]["t"] == 3033
