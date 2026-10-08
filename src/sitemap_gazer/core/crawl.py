from dataclasses import dataclass, field

from usp.fetch_parse import SitemapFetcher
from usp.objects.sitemap import AbstractSitemap, InvalidSitemap
from usp.tree import sitemap_tree_for_homepage

from sitemap_gazer.models import Site


@dataclass
class FetchedSitemap:
    urls: set[str] = field(default_factory=set)
    failures: list[tuple[str, str]] = field(default_factory=list)
    sitemap_urls: set[str] = field(default_factory=set)


def _collect(
    node: AbstractSitemap,
    urls: set[str],
    failures: list[tuple[str, str]],
    success_urls: set[str],
) -> None:
    if isinstance(node, InvalidSitemap):
        failures.append((node.url, node.reason))
        return

    success_urls.add(node.url)
    for page in node.pages:
        urls.add(page.url)
    for child in node.sub_sitemaps:
        _collect(child, urls, failures, success_urls)


def sitemap_targets(site: Site) -> list[str]:
    targets: list[str] = []
    if site.sitemap_url:
        targets.append(site.sitemap_url)
    targets.extend(site.sitemap_urls)
    unique: list[str] = []
    seen: set[str] = set()
    for target in targets:
        if target and target not in seen:
            seen.add(target)
            unique.append(target)
    return unique


def crawl_site(site: Site) -> FetchedSitemap:
    targets = sitemap_targets(site)
    if targets:
        roots = [
            SitemapFetcher(url=target, recursion_level=0).sitemap()
            for target in targets
        ]
    else:
        roots = [
            sitemap_tree_for_homepage(site.url, use_known_paths=False, use_robots=True)
        ]

    fetched = FetchedSitemap()
    for root in roots:
        _collect(root, fetched.urls, fetched.failures, fetched.sitemap_urls)
    return fetched
