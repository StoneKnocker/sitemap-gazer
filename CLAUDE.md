# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**sitemap-gazer** is a Python CLI tool that monitors website changes by crawling sitemaps, storing them locally, comparing with previous crawls, and generating README reports. It supports monitoring multiple sitemaps in a single report and can run in GitHub Actions workflows.

## Architecture

The codebase follows a modular structure:

### Core Components
- **CLI Interface**: `src/sitemap_gazer/__main__.py` - Main entry point with Click-based CLI
- **Models**: `src/sitemap_gazer/models.py` - Pydantic models for configuration and data structures
- **Crawling**: `src/sitemap_gazer/core/crawl.py` - Uses `ultimate-sitemap-parser` to fetch and parse sitemaps
- **Diffing**: `src/sitemap_gazer/core/diff.py` - Compares crawls to identify new/changed pages
- **Configuration**: `src/sitemap_gazer/core/init.py` - Handles config file creation and loading
- **Reporting**: `src/sitemap_gazer/batch/readme.py` - Generates README reports from crawl data
- **Utilities**: `src/sitemap_gazer/utils.py` - Helper functions for directory handling

### Data Flow
1. **Configuration**: JSON-based config (`sitemap-gazer.json`) defines sites to monitor
2. **Crawling**: Sitemaps are fetched and stored as JSON with timestamps (`data/{site_name}/{timestamp}/sitemap.json`)
3. **Diffing**: New crawls are compared against previous ones, with diffs saved as `diff.json`
4. **Reporting**: README.md is auto-generated showing recent changes across all monitored sites

## Development Commands

```bash
# Install dependencies
poetry install

# Run development version
poetry run sitemap-gazer

# Build package
poetry build

# Install locally built package
pip install dist/sitemap_gazer-0.1.0-py3-none-any.whl

# Code formatting
poetry run black src/
```

## Usage Patterns

### Configuration
Sites are configured in `sitemap-gazer.json`:
```json
{
  "sites": [
    {
      "name": "example.com",
      "url": "https://example.com/"
    }
  ],
  "genReadme": true,
  "output_dir": "data"
}
```

### Key Data Structures
- **Site**: Basic site configuration with name and URL
- **SitemapGazerConfig**: Main configuration including sites list and output settings
- **Page**: Individual page data from sitemaps (URL, priority, last modified, etc.)
- **NewsStory**: News-specific metadata when available
- **Sitemap**: Hierarchical sitemap structure with nested sitemaps and pages
- **Diff**: Contains new/changed pages between crawls

### Storage Pattern
- Timestamped directories: `data/{site_name}/YYYYMMDD_HHMMSS/`
- Each crawl contains: `sitemap.json` (full crawl) and optionally `diff.json` (changes)
- Latest 3 crawls per site are shown in README reports