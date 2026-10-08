import re
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from sitemap_gazer.models import Site

# ISO 639-1. Two-letter path segments outside this set, such as /im/, stay put.
# Regional tags such as pt-br are recognized when the language half is in the set.
_LOCALE_CODES = frozenset("""
    aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs
    ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff
    fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id
    ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku
    kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my
    na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu
    rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv
    sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo
    wa wo xh yi yo za zh zu
    """.split())


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


def _is_locale(segment: str) -> bool:
    segment = segment.lower()
    if segment in _LOCALE_CODES:
        return True
    language, separator, region = segment.partition("-")
    return bool(
        separator
        and language in _LOCALE_CODES
        and len(region) == 2
        and region.isalpha()
    )


def strip_locale(url: str) -> str:
    parts = urlsplit(url)
    segments = parts.path.split("/")
    if len(segments) < 2 or not _is_locale(segments[1]):
        return url
    if len(segments) == 2:
        path = "/"
    else:
        del segments[1]
        path = "/".join(segments)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise ValueError(f"invalid URL pattern {pattern!r}: {exc}") from exc
    return compiled


def filter_urls(urls: Iterable[str], site: Site) -> set[str]:
    include = compile_patterns(site.include)
    exclude = compile_patterns(site.exclude)
    kept: set[str] = set()
    for raw in urls:
        url = normalize_url(raw)
        if site.strip_locales:
            url = normalize_url(strip_locale(url))
        if include and not any(pattern.search(url) for pattern in include):
            continue
        if any(pattern.search(url) for pattern in exclude):
            continue
        kept.add(url)
    return kept


def _matches_suffix(url: str, suffix: str) -> bool:
    if not suffix or not url.endswith(suffix) or len(url) <= len(suffix):
        return False
    if suffix.startswith("/"):
        return True
    return url[: -len(suffix)].endswith("/")


def group_urls(urls: list[str], suffixes: list[str]) -> list[tuple[str, list[str]]]:
    ordered_suffixes = sorted(suffixes, key=len, reverse=True)
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for url in urls:
        base = url
        matched = ""
        for suffix in ordered_suffixes:
            if suffix and _matches_suffix(url, suffix):
                base = url[: -len(suffix)] or url
                matched = suffix
                break
        if base not in grouped:
            grouped[base] = []
            order.append(base)
        if matched and matched not in grouped[base]:
            grouped[base].append(matched)
    return [(base, grouped[base]) for base in order]
