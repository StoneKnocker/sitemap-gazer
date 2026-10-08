from datetime import datetime
from pathlib import Path

from sitemap_gazer.core.run import SiteResult
from sitemap_gazer.models import SitemapGazerConfig
from sitemap_gazer.store import changes_path, read_changes
from sitemap_gazer.urls import group_urls

REPORT_HEADING = "# Sitemap Gazer Report"


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
) -> Path:
    readme_path = report_path(config.output_dir)
    readme_path.parent.mkdir(parents=True, exist_ok=True)
    by_name = {result.name: result for result in results}
    sections = [
        REPORT_HEADING,
        "",
        _site_links(config),
        "",
        f"Last run: {timestamp}",
        "",
    ]
    if results:
        for result in results:
            sections.append(f"- {result.name}: {result.message}")
        sections.append("")

    for site in config.sites:
        anchor = _anchor(site.name)
        sections.append(f'<a id="{anchor}"></a>')
        sections.append(f"## {site.name}")
        sections.append("")
        records = read_changes(
            changes_path(config.output_dir / site.name), config.readme_limit
        )
        if not records:
            note = by_name.get(site.name)
            if note and note.status == "initial":
                sections.append(
                    "Initial crawl recorded. Later runs list only new URLs."
                )
            else:
                sections.append("No new URLs recorded yet.")
            sections.append("")
            continue
        for record in records:
            urls = record.get("urls") or []
            sections.append(f"### {record.get('timestamp', '')}")
            sections.append("")
            if not urls:
                sections.append("No new URLs.")
                sections.append("")
                continue
            for base, suffixes in group_urls(urls, site.group_suffixes):
                sections.append(f"- {base}")
                for suffix in suffixes:
                    sections.append(f"  - {suffix}")
            sections.append("")

    sections.append(
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
    return write_readme(config, [], timestamp)


def _site_links(config: SitemapGazerConfig) -> str:
    return "\n\n".join(f"[{site.name}](#{_anchor(site.name)})" for site in config.sites)


def _anchor(name: str) -> str:
    slug = "".join(character.lower() for character in name if character.isalnum())
    return f"site-{slug or 'site'}"
