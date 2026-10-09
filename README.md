# sitemap-gazer

[README 中文版](README.zh.md)

A tool that helps you easily monitor website changes.

It crawls sitemaps, remembers every URL it has seen, and writes new URLs to data/README.md. Each run rewrites that report: the new URLs from that run are listed at the top, and recent history for each site follows. One report can watch several sites. A crawl that fails, returns no pages, or is much smaller than the baseline is ignored, and one site failing does not stop the others.

It can also run in a GitHub Actions workflow: [hackerqed/sitemap-gazer-example](https://github.com/hackerqed/sitemap-gazer-example)

## Installation

```bash
pip install sitemap-gazer

mkdir sitemap-gazer-report
cd sitemap-gazer-report

sitemap-gazer init
# create sitemap-gazer.json

# edit sitemap-gazer.json
# for example, add a target site crazygames.com
# {
#   "sites": [
#     {
#       "name": "crazygames.com",
#       "url": "https://crazygames.com/",
#       "sitemap_url": "https://crazygames.com/sitemap.xml",
#       "include": [],
#       "exclude": [],
#       "strip_locales": false,
#       "group_suffixes": []
#     }
#   ],
#   "genReadme": true,
#   "output_dir": "data",
#   "readme_limit": 10,
#   "min_page_ratio": 0.8
# }

sitemap-gazer
# crawl data, save to ./data/<site>/
# new URLs are listed in ./data/README.md, not the project README.md
```

## Development

To run as developer:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
sitemap-gazer
```

To build and install locally:

```bash
pip install build
python -m build
pip install dist/sitemap_gazer-0.0.4-py3-none-any.whl
```
