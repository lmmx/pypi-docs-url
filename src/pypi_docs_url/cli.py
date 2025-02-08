import click

from .core import get_intersphinx_url


@click.command()
@click.argument("package_name")
@click.option("--debug", is_flag=True, default=False, help="Enable debug output")
def main(package_name: str, debug: bool):
    """
    CLI entry point to get the 'objects.inv' URL for PACKAGE_NAME, if any.
    """
    # Enable debug if flag is set
    url = get_intersphinx_url(package_name, debug=debug)
    if url is None:
        click.echo("No objects.inv discovered or parse failed.")
    else:
        click.echo(url)
