import gzip
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from sitemap_gazer.models import Site
from sitemap_gazer.urls import filter_urls
from sitemap_gazer.utils import get_timestamped_dirs

KNOWN_NAME = "known_urls.txt.gz"
STATE_NAME = "state.json"
CHANGES_NAME = "changes.jsonl"


class SiteState(BaseModel):
    last_good_count: int = 0
    pending_count: int = 0
    sitemap_urls: list[str] = Field(default_factory=list)
    filter_signature: str = ""
    updated_at: str = ""


class Baseline:
    def __init__(
        self,
        known: set[str],
        state: SiteState | None,
        ratio_reliable: bool,
        note: str = "",
    ):
        self.known = known
        self.state = state
        self.ratio_reliable = ratio_reliable
        self.note = note


def filter_signature(site: Site) -> str:
    payload = {
        "include": site.include,
        "exclude": site.exclude,
        "strip_locales": site.strip_locales,
    }
    encoded = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def known_path(site_dir: Path) -> Path:
    return site_dir / KNOWN_NAME


def state_path(site_dir: Path) -> Path:
    return site_dir / STATE_NAME


def changes_path(site_dir: Path) -> Path:
    return site_dir / CHANGES_NAME


def load_known(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return {line.strip() for line in handle if line.strip()}


def write_known(path: Path, urls: set[str]) -> None:
    text = "\n".join(sorted(urls))
    if text:
        text += "\n"
    _atomic_write_gzip(path, text)


def load_state(path: Path) -> SiteState | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return SiteState.model_validate_json(handle.read())


def write_state(path: Path, state: SiteState) -> None:
    _atomic_write_text(path, state.model_dump_json(indent=2) + "\n")


def append_changes(path: Path, timestamp: str, urls: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": timestamp, "urls": urls}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_changes(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    if limit > 0:
        records = records[-limit:]
    records.reverse()
    return records


def load_baseline(site: Site, site_dir: Path) -> Baseline:
    signature = filter_signature(site)
    state = load_state(state_path(site_dir))
    known_file = known_path(site_dir)
    snapshots = get_timestamped_dirs(site_dir)
    filters_match = state is not None and state.filter_signature == signature

    if filters_match and known_file.exists():
        return Baseline(load_known(known_file), state, ratio_reliable=True)

    if snapshots:
        known, count, sitemap_urls = _migrate_snapshots(site, snapshots)
        if known:
            migrated = SiteState(
                last_good_count=count,
                sitemap_urls=sitemap_urls,
                filter_signature=signature,
                updated_at=_now(),
            )
            site_dir.mkdir(parents=True, exist_ok=True)
            write_known(known_file, known)
            write_state(state_path(site_dir), migrated)
            return Baseline(
                known,
                migrated,
                ratio_reliable=True,
                note=f"loaded {len(known)} known URLs from {len(snapshots)} existing snapshots",
            )

    if state is not None and known_file.exists():
        rewritten = filter_urls(load_known(known_file), site)
        migrated = SiteState(
            last_good_count=len(rewritten),
            sitemap_urls=state.sitemap_urls,
            filter_signature=signature,
            updated_at=_now(),
        )
        write_known(known_file, rewritten)
        write_state(state_path(site_dir), migrated)
        return Baseline(
            rewritten,
            migrated,
            ratio_reliable=True,
            note=f"reapplied URL filters, {len(rewritten)} known URLs",
        )

    return Baseline(set(), None, ratio_reliable=True)


def _migrate_snapshots(
    site: Site, snapshots: list[Path]
) -> tuple[set[str], int, list[str]]:
    known: set[str] = set()
    latest_count = 0
    latest_sitemaps: list[str] = []
    saw_pages = False
    for snapshot in snapshots:
        sitemap_file = snapshot / "sitemap.json"
        if not sitemap_file.exists():
            continue
        raw_urls, sitemap_urls = _page_urls(sitemap_file)
        filtered = filter_urls(raw_urls, site)
        known |= filtered
        # Snapshots are newest first. One oversized historical crawl must not
        # become the baseline that later, smaller crawls are measured against.
        if filtered and not saw_pages:
            latest_count = len(filtered)
            latest_sitemaps = sorted(sitemap_urls)
            saw_pages = True
    return known, latest_count, latest_sitemaps


def _page_urls(sitemap_file: Path) -> tuple[set[str], set[str]]:
    with sitemap_file.open(encoding="utf-8") as handle:
        data = json.load(handle)
    urls: set[str] = set()
    sitemap_urls: set[str] = set()

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        pages = node.get("pages") or []
        url = node.get("url")
        if pages and isinstance(url, str):
            sitemap_urls.add(url)
        for page in pages:
            if isinstance(page, dict) and isinstance(page.get("url"), str):
                urls.add(page["url"])
        for child in node.get("sitemaps") or []:
            walk(child)

    walk(data)
    return urls, sitemap_urls


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_write_gzip(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temporary, path)
