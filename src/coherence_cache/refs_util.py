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


def arxiv_excerpt_fragment(excerpt: str | None) -> str:
    """``#:~:text=`` token from an excerpt. Commas split fragments, so use the first clause."""
    text = re.sub(r"\s+", " ", excerpt or "").strip()
    if not text:
        return ""
    start = text.split(",")[0].strip()
    if len(start) < 16:
        start = re.sub(r",", "", text)
        start = re.sub(r"\s+", " ", start).strip()
    start = start[:96].strip(" -")
    if not start:
        return ""
    from urllib.parse import quote

    return "#:~:text=" + quote(start, safe="")


def arxiv_passage_url(
    aid: str,
    *,
    page: int | None = None,
    excerpt: str | None = None,
    html_id: str | None = None,
) -> str:
    """Open the original article. PDF ``#page=N`` works for every paper."""
    aid = normalize_arxiv_id(aid)
    if page:
        return f"https://arxiv.org/pdf/{aid}#page={int(page)}"
    frag = arxiv_excerpt_fragment(excerpt)
    if frag:
        return f"https://arxiv.org/html/{aid}{frag}"
    if html_id:
        return f"https://arxiv.org/html/{aid}#{html_id.lstrip('#')}"
    return f"https://arxiv.org/abs/{aid}"


def make_arxiv_ref(
    aid: str,
    *,
    page: int | None = None,
    paragraph: int | None = None,
    section: str | None = None,
    excerpt: str | None = None,
    html_id: str | None = None,
) -> Dict[str, Any]:
    aid = normalize_arxiv_id(aid)
    hid = html_id.lstrip("#") if html_id else None
    quote = re.sub(r"\s+", " ", excerpt).strip() if excerpt else None
    loc = arxiv_passage_url(aid, page=page, excerpt=quote, html_id=hid)
    label = f"arXiv:{aid}"
    if page:
        label += f" p.{int(page)}"
    if paragraph:
        label += f" ¶{int(paragraph)}"
    if section:
        label += f" §{section}"
    html = f"https://arxiv.org/html/{aid}"
    frag = arxiv_excerpt_fragment(quote)
    if frag:
        html += frag
    elif hid:
        html += f"#{hid}"
    rec: Dict[str, Any] = {
        "kind": "arxiv",
        "id": aid,
        "label": label,
        "url": loc,
        "abs": f"https://arxiv.org/abs/{aid}",
        "pdf": f"https://arxiv.org/pdf/{aid}" + (f"#page={int(page)}" if page else ""),
        "html": html,
    }
    if page:
        rec["page"] = int(page)
    if paragraph:
        rec["paragraph"] = int(paragraph)
    if section:
        rec["section"] = str(section)
    if hid:
        rec["html_id"] = hid
    if quote:
        rec["excerpt"] = quote
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
    excerpt = None
    tm = re.search(r"#:~:text=([^&#]*)", url or "")
    if tm:
        from urllib.parse import unquote

        excerpt = unquote(tm.group(1).replace("+", " ")).strip() or None
    html_id = None
    if "/html/" in url and "#" in url and not pm:
        frag = url.split("#", 1)[1]
        if not frag.startswith(":~:"):
            frag = frag.split(":~:", 1)[0]
            if frag and not frag.lower().startswith("page="):
                html_id = frag
    return make_arxiv_ref(aid, page=page, html_id=html_id, excerpt=excerpt)


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

    def _locator_near(end: int) -> tuple[int | None, int | None]:
        """Parse `p.1 ¶3` / `p.1 para 3` / `page 1, paragraph 3` after an id."""
        tail = text[end : end + 64]
        pm = re.match(
            r"(?:v\d+)?"
            r"(?:\s*[,;:]?\s*(?:#page=|p(?:age)?\.?\s*))(\d+)"
            r"(?:\s*[,;:]?\s*(?:¶+|para(?:graph)?\.?\s*)(\d+))?",
            tail,
            re.I,
        )
        if not pm:
            return None, None
        page = int(pm.group(1))
        para = int(pm.group(2)) if pm.group(2) else None
        return page, para

    def _add_arxiv(
        aid: str,
        page: int | None,
        paragraph: int | None = None,
        html_id: str | None = None,
    ) -> None:
        aid = normalize_arxiv_id(aid)
        rec = make_arxiv_ref(aid, page=page, paragraph=paragraph, html_id=html_id)
        new_place = (rec.get("page"), rec.get("paragraph"), rec.get("html_id"))

        def _coarser(a, b) -> bool:
            return all(x is None or x == y for x, y in zip(a, b))

        for i, prev in enumerate(found):
            if prev.get("kind") != "arxiv" or prev.get("id") != aid:
                continue
            old_place = (prev.get("page"), prev.get("paragraph"), prev.get("html_id"))
            if old_place == new_place:
                return
            if _coarser(old_place, new_place):
                found[i] = rec
                return
            if _coarser(new_place, old_place):
                return
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
            _add_arxiv(ax["id"], ax.get("page"), ax.get("paragraph"), ax.get("html_id"))
            continue
        seen.add(url)
        found.append({"kind": "url", "id": url, "label": url, "url": url})

    for m in re.finditer(rf"arXiv[:\s]+{_ARXIV_CORE}", text, re.I):
        page, para = _locator_near(m.end())
        _add_arxiv(m.group(1), page, para)

    for m in re.finditer(rf"\b{_ARXIV_CORE}\b", text):
        aid = normalize_arxiv_id(m.group(1))
        try:
            yymm = int(aid.split(".")[0])
        except ValueError:
            continue
        if 1500 <= yymm <= 2999:
            page, para = _locator_near(m.end())
            _add_arxiv(aid, page, para)

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
            loc = (
                r"(?:\s*[,;:]?\s*(?:#page=|p(?:age)?\.?\s*)\d+"
                r"(?:\s*[,;:]?\s*(?:¶+|para(?:graph)?\.?\s*)\d+)?)?"
            )
            patterns = [
                rf"arXiv[:\s]+{re.escape(r['id'])}(?:v\d+)?{loc}",
                rf"\b{re.escape(r['id'])}(?:v\d+)?{loc}",
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
