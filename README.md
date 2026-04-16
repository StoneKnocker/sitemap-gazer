# sitemap-gazer

[README 中文版](README.zh.md)

A tool that helps you easily monitor website changes.

It crawls sitemaps, saves them locally, compares with the previous crawl, and generates a README report for easy viewing. It supports monitoring multiple sitemaps in a single report.

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
#       "url": "https://crazygames.com/"
#     }
#   ],
#   "genReadme": true,
#   "output_dir": "data"
# }

sitemap-gazer
# crawl data, save to ./data/
# README.md will be generated automatically
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
pip install dist/sitemap_gazer-0.0.2-py3-none-any.whl
```
