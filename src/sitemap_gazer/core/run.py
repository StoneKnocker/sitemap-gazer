import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import click

from sitemap_gazer.core.crawl import FetchedSitemap, crawl_site, sitemap_targets
from sitemap_gazer.core.diff import assess_crawl
from sitemap_gazer.models import SitemapGazerConfig, Site
from sitemap_gazer.store import (
    SiteState,
    append_changes,
    changes_path,
    filter_signature,
    known_path,
    load_baseline,
    state_path,
    write_known,
    write_state,
)
from sitemap_gazer.urls import filter_urls

_PRINT_LOCK = threading.Lock()


@dataclass
class SiteResult:
    name: str
    status: str
    message: str
    new_urls: list[str] = field(default_factory=list)
    known_count: int = 0


def run(
    config: SitemapGazerConfig,
    cwd: Path | None = None,
    crawl_fn=crawl_site,
    timestamp: str | None = None,
) -> list[SiteResult]:
    cwd = cwd or Path.cwd()
    output_dir = config.output_dir
    if not output_dir.is_absolute():
        output_dir = cwd / output_dir
    config = config.model_copy(update={"output_dir": output_dir})
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")

    sites = list(config.sites)
    if not sites:
        click.echo("No sites configured.")
        return []

    with ThreadPoolExecutor(max_workers=max(1, len(sites))) as pool:
        futures = [
            pool.submit(_process_site, site, config, cwd, crawl_fn, timestamp)
            for site in sites
        ]
        results = [future.result() for future in futures]

    if config.genReadme:
        from sitemap_gazer.batch.readme import write_readme

        report = write_readme(config, results, timestamp)
        _log(f"Updating {_relative(report, cwd)}")
    return results


def _process_site(
    site: Site,
    config: SitemapGazerConfig,
    cwd: Path,
    crawl_fn,
    timestamp: str,
) -> SiteResult:
    site_dir = config.output_dir / site.name
    _log(f"Crawling {site.name} ({_targets_label(site)})")
    try:
        baseline = load_baseline(site, site_dir)
        if baseline.note:
            _log(f"{site.name}: {baseline.note}")

        fetched: FetchedSitemap = crawl_fn(site)
        current = filter_urls(fetched.urls, site)
        decision = assess_crawl(
            page_count=len(current),
            failures=fetched.failures,
            success_urls=fetched.sitemap_urls,
            state=baseline.state,
            ratio_reliable=baseline.ratio_reliable,
            min_page_ratio=config.min_page_ratio,
        )
        if not decision.accept:
            message = f"skipped, {decision.reason}"
            _log(f"{site.name}: {message}")
            return SiteResult(
                site.name, "skipped", message, known_count=len(baseline.known)
            )

        is_initial = len(baseline.known) == 0
        new_urls = [] if is_initial else sorted(current - baseline.known)
        known = baseline.known | current
        previous_count = baseline.state.last_good_count if baseline.state else 0
        pending_count = baseline.state.pending_count if baseline.state else 0
        adopted_count, next_pending, size_note = _baseline_count(
            previous_count, pending_count, len(current), config.min_page_ratio
        )
        state = SiteState(
            last_good_count=adopted_count,
            pending_count=next_pending,
            sitemap_urls=sorted(fetched.sitemap_urls),
            filter_signature=filter_signature(site),
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )
        site_dir.mkdir(parents=True, exist_ok=True)
        write_known(known_path(site_dir), known)
        write_state(state_path(site_dir), state)
        if new_urls:
            append_changes(changes_path(site_dir), timestamp, new_urls)

        notes = [note for note in (decision.reason, size_note) if note]
        warning = f" ({'; '.join(notes)})" if notes else ""
        if is_initial:
            status = "initial"
            message = f"initial crawl, {len(known)} URLs recorded{warning}"
        elif new_urls:
            status = "ok"
            relative = _relative(changes_path(site_dir), cwd)
            message = f"{len(new_urls)} new URLs, appended {relative}{warning}"
        else:
            status = "ok"
            message = f"0 new URLs (known {len(known)}){warning}"
        _log(f"{site.name}: {message}")
        return SiteResult(site.name, status, message, new_urls, len(known))
    except Exception as exc:
        message = f"failed: {exc}"
        _log(f"{site.name}: {message}")
        return SiteResult(site.name, "error", message)


def _baseline_count(
    previous: int, pending: int, current: int, min_page_ratio: float
) -> tuple[int, int, str]:
    if previous <= 0 or current <= previous * 3:
        return current, 0, ""
    if pending and current >= pending * min_page_ratio:
        return current, 0, ""
    return (
        previous,
        current,
        (
            f"crawl has {current} pages, more than 3x the baseline {previous}; "
            "baseline page count left unchanged"
        ),
    )


def _targets_label(site: Site) -> str:
    targets = sitemap_targets(site)
    if targets:
        return ", ".join(targets)
    return f"robots.txt at {site.url}"


def _relative(path: Path, cwd: Path) -> str:
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return str(path)


def _log(message: str) -> None:
    with _PRINT_LOCK:
        click.echo(message)
