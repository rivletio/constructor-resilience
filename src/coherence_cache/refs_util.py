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


_ARXIV_CORE = r"(\d{4}\.\d{4,5})(?:v\d+)?"


def normalize_arxiv_id(aid: str) -> str:
    aid = (aid or "").strip()
    return re.sub(r"v\d+$", "", aid, flags=re.I)


def arxiv_passage_url(
    aid: str,
    *,
    page: int | None = None,
    html_id: str | None = None,
) -> str:
    """Open the original arXiv artifact. PDF #page= works for every paper."""
    aid = normalize_arxiv_id(aid)
    if page:
        return f"https://arxiv.org/pdf/{aid}#page={int(page)}"
    if html_id:
        return f"https://arxiv.org/html/{aid}#{html_id.lstrip('#')}"
    return f"https://arxiv.org/abs/{aid}"


def make_arxiv_ref(
    aid: str,
    *,
    page: int | None = None,
    section: str | None = None,
    excerpt: str | None = None,
    html_id: str | None = None,
) -> Dict[str, Any]:
    aid = normalize_arxiv_id(aid)
    loc = arxiv_passage_url(aid, page=page, html_id=html_id)
    label = f"arXiv:{aid}"
    if page:
        label += f" p.{int(page)}"
    if section:
        label += f" §{section}"
    rec: Dict[str, Any] = {
        "kind": "arxiv",
        "id": aid,
        "label": label,
        "url": loc,
        "abs": f"https://arxiv.org/abs/{aid}",
        "pdf": f"https://arxiv.org/pdf/{aid}",
        "html": f"https://arxiv.org/html/{aid}",
    }
    if page:
        rec["page"] = int(page)
    if section:
        rec["section"] = str(section)
    if html_id:
        rec["html_id"] = html_id.lstrip("#")
    if excerpt:
        rec["excerpt"] = re.sub(r"\s+", " ", excerpt).strip()
    return rec


def parse_arxiv_url(url: str) -> Optional[Dict[str, Any]]:
    m = re.search(
        rf"arxiv\.org/(?:abs|pdf|html)/{_ARXIV_CORE}",
        url or "",
        re.I,
    )
    if not m:
        return None
    aid = normalize_arxiv_id(m.group(1))
    page = None
    pm = re.search(r"#page=(\d+)", url or "", re.I)
    if pm:
        page = int(pm.group(1))
    html_id = None
    if "/html/" in url and "#" in url and not pm:
        frag = url.split("#", 1)[1]
        if frag and not frag.lower().startswith("page="):
            html_id = frag
    return make_arxiv_ref(aid, page=page, html_id=html_id)


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

    def _page_near(end: int) -> int | None:
        tail = text[end : end + 48]
        pm = re.match(
            r"(?:v\d+)?(?:\s*[,;:]?\s*(?:#page=|p(?:age)?\.?\s*))(\d+)",
            tail,
            re.I,
        )
        return int(pm.group(1)) if pm else None

    def _add_arxiv(aid: str, page: int | None) -> None:
        aid = normalize_arxiv_id(aid)
        key = f"arxiv:{aid}"
        rec = make_arxiv_ref(aid, page=page)
        if key in seen:
            # Prefer a more specific locator (PDF page) if we already stored abs.
            for i, prev in enumerate(found):
                if prev.get("kind") == "arxiv" and prev.get("id") == aid:
                    if page and not prev.get("page"):
                        found[i] = rec
                    return
            return
        seen.add(key)
        found.append(rec)

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
        ax = parse_arxiv_url(url)
        if ax:
            seen.add(url)
            _add_arxiv(ax["id"], ax.get("page"))
            continue
        seen.add(url)
        found.append({"kind": "url", "id": url, "label": url, "url": url})

    for m in re.finditer(rf"arXiv[:\s]+{_ARXIV_CORE}", text, re.I):
        _add_arxiv(m.group(1), _page_near(m.end()))

    for m in re.finditer(rf"\b{_ARXIV_CORE}\b", text):
        aid = normalize_arxiv_id(m.group(1))
        try:
            yymm = int(aid.split(".")[0])
        except ValueError:
            continue
        if 1500 <= yymm <= 2999:
            _add_arxiv(aid, _page_near(m.end()))

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
        elif r["kind"] in ("url", "youtube_video"):
            if r.get("url") and f"]({r['url']})" not in out:
                out = out.replace(r["url"], f"[link]({r['url']})")
    return out
