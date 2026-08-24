"""Best-effort external reference extraction and markdown linkify."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_YT_ID = re.compile(
    r"(?:youtube\.com/watch\?(?:[^#]*?[&?])?v=|youtu\.be/)([\w-]{11})",
    re.I,
)
_YT_T = re.compile(r"[?&#]t=([\dhms:]+)", re.I)


def parse_timestamp(value: str | int | None) -> Optional[int]:
    """Seconds from an int, '90', '1h2m3s', or '1:02:03' / '50:33'."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    raw = str(value).strip().lower()
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    if ":" in raw:
        parts = [int(p) for p in raw.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return None
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", raw)
    if not m or not any(m.groups()):
        return None
    h, mm, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mm * 60 + s


def timestamp_label(seconds: int) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def youtube_watch_url(video_id: str, t: int | None = None) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}"
    if t is not None and t > 0:
        url += f"&t={int(t)}"
    return url


def parse_youtube_url(url: str) -> Optional[Dict[str, Any]]:
    m = _YT_ID.search(url or "")
    if not m:
        return None
    vid = m.group(1)
    tm = _YT_T.search(url or "")
    t = parse_timestamp(tm.group(1)) if tm else None
    rec: Dict[str, Any] = {
        "kind": "youtube_video",
        "id": vid,
        "youtube_video_id": vid,
        "url": youtube_watch_url(vid, t),
        "label": f"YouTube {vid}" + (f" @ {timestamp_label(t)}" if t else ""),
    }
    if t is not None:
        rec["t"] = t
        rec["t_label"] = timestamp_label(t)
    return rec


def extract_references(text: str) -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    seen = set()

    for m in re.finditer(r"arXiv[:\s]+(\d{4}\.\d{4,5})(?:v\d+)?", text, re.I):
        aid = m.group(1)
        if aid not in seen:
            seen.add(aid)
            found.append(
                {
                    "kind": "arxiv",
                    "id": aid,
                    "label": f"arXiv:{aid}",
                    "url": f"https://arxiv.org/abs/{aid}",
                }
            )

    for m in re.finditer(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", text):
        aid = m.group(1)
        if aid in seen:
            continue
        try:
            yymm = int(aid.split(".")[0])
        except ValueError:
            continue
        if 1500 <= yymm <= 2999:
            seen.add(aid)
            found.append(
                {
                    "kind": "arxiv",
                    "id": aid,
                    "label": f"arXiv:{aid}",
                    "url": f"https://arxiv.org/abs/{aid}",
                }
            )

    for m in re.finditer(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b", text):
        doi = m.group(1).rstrip(".")
        if doi not in seen:
            seen.add(doi)
            found.append(
                {
                    "kind": "doi",
                    "id": doi,
                    "label": f"doi:{doi}",
                    "url": f"https://doi.org/{doi}",
                }
            )

    for m in re.finditer(r"https?://[^\s<>)\]\"']+", text):
        url = m.group(0).rstrip(".,;:)")
        if url in seen:
            continue
        yt = parse_youtube_url(url)
        if yt:
            seen.add(url)
            seen.add(yt["youtube_video_id"])
            found.append(yt)
            continue
        seen.add(url)
        found.append({"kind": "url", "id": url, "label": url, "url": url})

    return found


def linkify_claim(text: str) -> str:
    refs = extract_references(text)
    out = text
    for r in sorted(refs, key=lambda x: -len(x["id"])):
        if r["kind"] == "arxiv":
            labeled = f"[{r['label']}]({r['url']})"
            patterns = [
                rf"arXiv[:\s]+{re.escape(r['id'])}(?:v\d+)?",
                rf"\b{re.escape(r['id'])}(?:v\d+)?\b",
            ]
            for pat in patterns:
                out2, n = re.subn(pat, labeled, out, count=1, flags=re.I)
                if n:
                    out = out2
                    break
        elif r["kind"] == "doi":
            labeled = f"[{r['label']}]({r['url']})"
            out = re.sub(re.escape(r["id"]), labeled, out, count=1)
        elif r["kind"] == "url":
            if f"]({r['url']})" not in out:
                out = out.replace(r["url"], f"[link]({r['url']})")
    return out
