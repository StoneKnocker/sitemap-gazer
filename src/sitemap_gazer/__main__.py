from pathlib import Path

import click

from sitemap_gazer.batch.readme import readme
from sitemap_gazer.core.init import create_config_file, load_config_file
from sitemap_gazer.core.run import run


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is not None:
        return

    config_path = Path.cwd() / "sitemap-gazer.json"
    try:
        config = load_config_file(config_path)
    except FileNotFoundError:
        click.echo(
            "Config file not found. Run 'sitemap-gazer init' and add sites to sitemap-gazer.json."
        )
        return

    results = run(config, cwd=Path.cwd())
    if results and not any(result.new_urls for result in results):
        click.echo("No new URLs.")


@cli.command()
def init():
    config_path = create_config_file(Path.cwd())
    config = load_config_file(config_path)
    click.echo(config.model_dump(mode="json"))
    click.echo(f"Created {config_path}")
    click.echo(f"Add sites to {config_path} to begin")


@cli.command(name="readme")
def update_readme():
    config = load_config_file(Path.cwd() / "sitemap-gazer.json")
    report = readme(config, cwd=Path.cwd())
    click.echo(f"Updating {report}")


if __name__ == "__main__":
    cli()
