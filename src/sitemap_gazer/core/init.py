import json
from pathlib import Path

import click

from sitemap_gazer.models import SitemapGazerConfig


def create_config_file(output_dir: Path | str) -> Path:
    config = SitemapGazerConfig()
    file_path = Path(output_dir) / "sitemap-gazer.json"
    if file_path.exists():
        raise click.ClickException(f"Config file already exists: {file_path}")

    file_path.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return file_path


def load_config_file(file_path: Path | str) -> SitemapGazerConfig:
    path = Path(file_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {path}") from None
    return SitemapGazerConfig.model_validate_json(raw)
