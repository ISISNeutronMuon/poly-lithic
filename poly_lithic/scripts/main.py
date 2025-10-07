"""
Main entry point for poly_lithic CLI.

Provides backward compatibility while supporting new Click-based commands.
"""


def main():
    """
    Main entry point that supports both old and new CLI styles.

    Old style (still works):
        python -m poly_lithic.scripts.main --config config.yaml --debug

    New style (recommended):
        poly-lithic --config config.yaml --debug
        poly-lithic run --config config.yaml
        poly-lithic plugin init --name my-plugin
    """
    import sys
    from poly_lithic.src.cli import cli

    # If no arguments, show help
    if len(sys.argv) == 1:
        sys.argv.append('--help')

    # Run the Click CLI
    cli()


if __name__ == '__main__':
    main()
