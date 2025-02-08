import click
from .core import get_intersphinx_url


@click.command()
@click.argument("package_name")
def main(package_name: str):
    """
    CLI entry point to get the 'objects.inv' URL for PACKAGE_NAME, if any.
    """
    url = get_intersphinx_url(package_name)
    if url is None:
        click.echo("No objects.inv discovered or parse failed.")
    else:
        click.echo(url)
