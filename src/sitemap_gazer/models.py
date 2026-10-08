from pathlib import Path

from pydantic import BaseModel, Field


class Site(BaseModel):
    name: str
    url: str
    sitemap_url: str | None = None
    sitemap_urls: list[str] = Field(default_factory=list)
    include: list[str] = Field(
        default_factory=list,
        description="If set, a URL must match at least one of these regular expressions",
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="Drop URLs that match any of these regular expressions",
    )
    strip_locales: bool = Field(
        default=False,
        description="Collapse a leading language path segment so locale copies count once",
    )
    group_suffixes: list[str] = Field(
        default_factory=list,
        description="Report suffixes such as /api and /examples under their parent URL",
    )


class SitemapGazerConfig(BaseModel):
    sites: list[Site] = Field(default_factory=list)
    genReadme: bool = True
    output_dir: Path = Path("./data")
    readme_limit: int = Field(
        default=10, description="How many change records to show per site"
    )
    min_page_ratio: float = Field(
        default=0.8,
        description="Reject a crawl smaller than this fraction of the baseline",
    )
