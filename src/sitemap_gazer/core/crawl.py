import json
import re
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
from pydantic import HttpUrl
from usp.tree import sitemap_tree_for_homepage
from usp.objects.sitemap import AbstractSitemap, PagesXMLSitemap, PagesTextSitemap
from urllib.parse import urlparse
from decimal import Decimal

from sitemap_gazer.models import SitemapGazerConfig, Sitemap, Page, NewsStory


def should_skip_url(url: str) -> bool:
    """Check if URL should be skipped based on blog/archive patterns, old year patterns, and multilingual content."""
    url_lower = url.lower()
    
    # Skip URLs containing blog or archive
    skip_patterns = ['blog', 'archive']
    if any(pattern in url_lower for pattern in skip_patterns):
        return True
    
    # Skip multilingual content URLs
    multilingual_patterns = [
        '/ar/', '/az/', '/be/', '/bg/', '/ca/', '/cs/', '/de/', '/es/', '/fa/',
        '/fr/', '/he/', '/hi/', '/hu/', '/hy/', '/id/', '/it/', '/ja/', '/ka/',
        '/kk/', '/nl/', '/pl/', '/pt/', '/ro/', '/ru/', '/sk/', '/sr/', '/th/',
        '/tk/', '/tr/', '/uk/', '/uz/', '/vi/', '/zh/', '/dk/', '/jp/'
    ]
    if any(pattern in url_lower for pattern in multilingual_patterns):
        return True
    
    # Skip URLs with 4-digit years older than current year
    year_matches = re.findall(r'/\d{4}/', url)
    if year_matches:
        current_year = datetime.now().year
        for year_str in year_matches:
            try:
                year = int(year_str.strip('/'))
                if year < current_year:
                    return True
            except ValueError:
                continue
    
    return False

def sitemap_to_dict(sitemap: AbstractSitemap) -> Sitemap:
    result = Sitemap(url=sitemap.url, type=sitemap.__class__.__name__)
    
    # Skip entire sitemap if its URL matches skip patterns - AGGRESSIVE FILTERING
    if should_skip_url(sitemap.url):
        return result

    if isinstance(sitemap, (PagesXMLSitemap, PagesTextSitemap)):
        for page in sitemap.pages:
            # Skip URLs containing blog or archive
            if should_skip_url(page.url):
                continue
                
            page_dict = Page(
                url=page.url,
                priority=(
                    float(page.priority)
                    if isinstance(page.priority, Decimal)
                    else page.priority
                ),
                last_modified=(
                    page.last_modified.isoformat() if page.last_modified else None
                ),
                change_frequency=(
                    page.change_frequency.value if page.change_frequency else None
                ),
            )
            if page.news_story:
                page_dict.news_story = NewsStory(
                    title=page.news_story.title,
                    publish_date=page.news_story.publish_date,
                    publication_name=page.news_story.publication_name,
                    publication_language=page.news_story.publication_language,
                    access=page.news_story.access,
                    genres=page.news_story.genres,
                    keywords=page.news_story.keywords,
                    stock_tickers=page.news_story.stock_tickers,
                )
            result.pages.append(page_dict)
    elif hasattr(sitemap, "sub_sitemaps"):
        for sub_sitemap in sitemap.sub_sitemaps:
            # Skip sub-sitemap entirely if its URL matches skip patterns
            if not should_skip_url(sub_sitemap.url):
                result.sitemaps.append(sitemap_to_dict(sub_sitemap))

    return result


def crawl(
    url: HttpUrl,
    output_dir: Path,
) -> Path:
    tree: AbstractSitemap = sitemap_tree_for_homepage(url)
    tree_sitemap: Sitemap = sitemap_to_dict(tree)

    # Save sitemap as JSON
    sitemap_filepath = output_dir / "sitemap.json"
    with sitemap_filepath.open("w") as f:
        json.dump(tree_sitemap.model_dump(), f, indent=2, default=str)

    return sitemap_filepath
