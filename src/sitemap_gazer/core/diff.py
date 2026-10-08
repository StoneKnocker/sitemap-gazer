from dataclasses import dataclass

from sitemap_gazer.store import SiteState


@dataclass(frozen=True)
class CrawlDecision:
    accept: bool
    reason: str = ""


def real_failures(
    failures: list[tuple[str, str]], success_urls: set[str]
) -> list[tuple[str, str]]:
    real = []
    for url, reason in failures:
        if url in success_urls:
            continue
        if "Recursion detected" in reason:
            continue
        real.append((url, reason))
    return real


def assess_crawl(
    *,
    page_count: int,
    failures: list[tuple[str, str]],
    success_urls: set[str],
    state: SiteState | None,
    ratio_reliable: bool,
    min_page_ratio: float,
) -> CrawlDecision:
    if page_count == 0:
        return CrawlDecision(False, "crawl returned no pages")

    real = real_failures(failures, success_urls)
    if (
        ratio_reliable
        and state is not None
        and state.last_good_count > 0
        and page_count < state.last_good_count * min_page_ratio
    ):
        return CrawlDecision(
            False,
            (
                f"{page_count} pages is below {min_page_ratio:.0%} of the baseline "
                f"({state.last_good_count})"
            ),
        )

    if real:
        shown = ", ".join(url for url, _reason in real[:5])
        extra = f" and {len(real) - 5} more" if len(real) > 5 else ""
        return CrawlDecision(True, f"failed sitemaps: {shown}{extra}")

    return CrawlDecision(True)
