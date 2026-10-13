from datetime import datetime
from pathlib import Path

from sitemap_gazer.core.run import SiteResult
from sitemap_gazer.models import SitemapGazerConfig
from sitemap_gazer.store import (
    changes_path,
    known_path,
    load_known,
    load_state,
    read_changes,
    state_path,
)
from sitemap_gazer.urls import group_urls

REPORT_HEADING = "# Sitemap Gazer Report"
SITE_URLS_NAME = "new-urls.md"


def report_path(output_dir: Path) -> Path:
    """Put the report beside the crawl data, never over a project README."""
    preferred = output_dir / "README.md"
    if _is_foreign_file(preferred):
        return output_dir / "sitemap-report.md"
    return preferred


def _is_foreign_file(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    with path.open(encoding="utf-8", errors="replace") as handle:
        first = handle.readline()
    return not first.startswith(REPORT_HEADING)


def write_readme(
    config: SitemapGazerConfig,
    results: list[SiteResult],
    timestamp: str,
    last_run: str | None = None,
    cwd: Path | None = None,
) -> Path:
    """Write today's summary, and each site's new URLs to its own file.

    changes.jsonl already includes this run. Counting the whole day keeps an
    earlier find visible when a later run on the same day adds nothing.
    Site lines use a path from cwd, with no #anchor, so nvim gf can open them.
    """
    cwd = (cwd or Path.cwd()).resolve()
    readme_path = report_path(config.output_dir)
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    by_name = {result.name: result for result in results}
    report_day = _day(timestamp)
    last_run = last_run or timestamp
    output_rel = _relative_to_cwd(config.output_dir, cwd)
    active: list[str] = []
    quiet: list[str] = []
    today_total = 0

    for site in config.sites:
        site_dir = config.output_dir / site.name
        records = read_changes(changes_path(site_dir), config.readme_limit)
        _write_site_urls(
            site_dir / SITE_URLS_NAME, site.name, records, site.group_suffixes
        )
        today_records = [
            record
            for record in records
            if _day(str(record.get("timestamp", ""))) == report_day
        ]
        today_count = _url_count(today_records)
        today_total += today_count
        line = _today_line(
            site.name,
            today_count,
            f"{output_rel}/{site.name}/{SITE_URLS_NAME}",
            by_name.get(site.name),
            _known_count(site_dir, by_name.get(site.name)),
        )
        if today_count:
            active.append(line)
        else:
            quiet.append(line)

    sections = [
        REPORT_HEADING,
        "",
        f"Date: {report_day}",
        f"Last run: {last_run}",
        "",
        f"## Today ({today_total} new)",
        "",
    ]
    if today_total == 0:
        sections.append("No new URLs.")
        sections.append("")
    sections.extend(active)
    sections.extend(quiet)
    if active or quiet:
        sections.append("")
    sections.append(
        "Paths above are relative to the working directory. "
        "Crawls that find nothing new are omitted. "
        "A crawl that returns no pages, or fewer than "
        f"{config.min_page_ratio:.0%} of the baseline, does not update the known URL set."
    )
    sections.append("")
    readme_path.write_text("\n".join(sections), encoding="utf-8")
    return readme_path


def readme(config: SitemapGazerConfig, cwd: Path | None = None) -> Path:
    cwd = cwd or Path.cwd()
    output_dir = config.output_dir
    if not output_dir.is_absolute():
        output_dir = cwd / output_dir
    config = config.model_copy(update={"output_dir": output_dir})
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return write_readme(
        config,
        [],
        timestamp,
        last_run=_latest_crawl_stamp(config) or timestamp,
        cwd=cwd,
    )


def _write_site_urls(
    path: Path,
    site_name: str,
    records: list[dict],
    suffixes: list[str],
) -> None:
    if not records:
        return
    days = _records_by_day(records)
    sections = [f"# {site_name}", ""]
    if len(days) > 1:
        for day, _bucket in days:
            sections.append(f"- [{day}](#{day})")
        sections.append("")
    for day, bucket in days:
        sections.append(f'<a id="{day}"></a>')
        sections.append(f"## {day}")
        sections.append("")
        for record in bucket:
            urls = record.get("urls") or []
            sections.append(f"### {record.get('timestamp', '')}")
            sections.append("")
            if not urls:
                sections.append("No new URLs.")
                sections.append("")
                continue
            _append_urls(sections, urls, suffixes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sections), encoding="utf-8")


def _relative_to_cwd(path: Path, cwd: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(cwd).as_posix()
    except ValueError:
        return resolved.as_posix()


def _today_line(
    name: str,
    today_count: int,
    target: str,
    result: SiteResult | None,
    known: int,
) -> str:
    if today_count:
        text = f"{target}: {today_count} new URLs"
        if known:
            text += f" (known {known})"
        if result is not None and result.status in {"error", "skipped"}:
            text += f". This run {result.message}"
        return f"- {text}"
    if result is not None and result.message:
        return f"- {name}: {result.message}"
    if known:
        return f"- {name}: 0 new URLs (known {known})"
    return f"- {name}: no new URLs today"


def _known_count(site_dir: Path, result: SiteResult | None) -> int:
    if result is not None and result.known_count:
        return result.known_count
    count = len(load_known(known_path(site_dir)))
    if count:
        return count
    state = load_state(state_path(site_dir))
    if state is not None and state.last_good_count:
        return state.last_good_count
    return 0


def _latest_crawl_stamp(config: SitemapGazerConfig) -> str:
    latest = ""
    for site in config.sites:
        state = load_state(state_path(config.output_dir / site.name))
        if state is None:
            continue
        stamp = _stamp_from_iso(state.updated_at)
        if stamp > latest:
            latest = stamp
    return latest


def _stamp_from_iso(value: str) -> str:
    text = value.strip()
    if len(text) < 19 or text[4] != "-" or text[10] != "T":
        return ""
    return (
        text[0:4]
        + text[5:7]
        + text[8:10]
        + "_"
        + text[11:13]
        + text[14:16]
        + text[17:19]
    )


def _records_by_day(records: list[dict]) -> list[tuple[str, list[dict]]]:
    days: list[tuple[str, list[dict]]] = []
    index: dict[str, list[dict]] = {}
    for record in records:
        day = _day(str(record.get("timestamp", "")))
        bucket = index.get(day)
        if bucket is None:
            bucket = []
            index[day] = bucket
            days.append((day, bucket))
        bucket.append(record)
    return days


def _url_count(records: list[dict]) -> int:
    return sum(len(record.get("urls") or []) for record in records)


def _day(timestamp: str) -> str:
    digits = timestamp.split("_", 1)[0]
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return timestamp or "unknown"


def _append_urls(sections: list[str], urls: list[str], suffixes: list[str]) -> None:
    for base, matched in group_urls(urls, suffixes):
        sections.append(f"- {base}")
        for suffix in matched:
            sections.append(f"  - {suffix}")
    sections.append("")
