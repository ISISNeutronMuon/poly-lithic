import click
import asyncio
import json
import logging
import os
import sys
import time
import traceback


from poly_lithic._version import __version__
from poly_lithic.src.logging_utils import get_logger, make_logger

def import_poly_lithic_deps():
    from poly_lithic.src.config import ConfigParser
    from poly_lithic.src.utils.builder import Builder


# ============================================================================
# Helper Functions
# ============================================================================

def load_build_info():
    """Load build info from build-info.json if it exists."""
    if os.path.exists('build-info.json'):
        with open('build-info.json') as stream:
            data = json.load(stream)
        for key, value in data.items():
            os.environ[key] = value


def print_banner():
    """Print the startup banner."""
    width = 80
    border = click.style('=' * width, fg='green')
    version = click.style(f"🚀 Poly-Lithic Version: {__version__} 🚀", fg='yellow', bold=True)
    click.echo(border)
    click.echo(version.center(width))
    click.echo(border + "\n")


def setup_logging(debug):
    """Setup logging based on debug flag."""
    if debug:
        click.echo('Debug mode')
        logger = make_logger(level=logging.DEBUG)
        os.environ['DEBUG'] = 'True'
    else:
        click.echo('Info mode')
        logger = make_logger(level=logging.INFO)
        os.environ['DEBUG'] = 'False'
    return logger


def load_env_config(env_path):
    """Load environment configuration from JSON file."""
    logger = get_logger()
    logger.debug(f'Setting environment variables from: {env_path}')
    try:
        with open(env_path) as stream:
            data = json.load(stream)
        for key, value in data.items():
            os.environ[key] = value
        logger.info(f'Loaded {len(data)} environment variables')
    except Exception as e:
        logger.error(f'Error setting environment variables: {e}')
        raise e


async def model_main(args, config, broker):
    """
    Main async function for running the model manager.
    
    Args:
        args: Parsed arguments namespace
        config: Configuration object
        broker: Broker instance
    """
    logger = get_logger()
    logger.info('Starting model manager')
    
    os.environ['PUBLISH'] = str(args.publish)
    
    try:
        if config.deployment.type == 'continuous':
            time_start = time.time()
            
            while True:
                if time.time() - time_start > config.deployment.rate:
                    time_start = time.time()
                    broker.get_all()
                else:
                    if len(broker.queue) > 0:
                        broker.parse_queue()
                
                if len(broker.queue) > 0:
                    broker.parse_queue()
                    
                    if args.one_shot:
                        logger.info('One shot mode, exiting')
                        break
                
                await asyncio.sleep(0.01)
        
        else:
            raise Exception(f'Deployment type "{config.deployment.type}" not supported')
            
    except Exception as e:
        logger.error(f'Error in model main loop: {traceback.format_exc()}')
        raise e
    finally:
        logger.info('Exiting')


# ============================================================================
# CLI Commands
# ============================================================================

@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version=__version__, prog_name='poly-lithic')
def cli(ctx):
    """
    Poly-Lithic - A modular ML model deployment framework with plugin support.
    
    Run without subcommands to start the model manager (default behavior).
    Use subcommands for additional functionality.
    
    Examples:

        poly-lithic --config config.yaml
        poly-lithic --config config.yaml --debug
        poly-lithic plugin init --name my-plugin
    """
    load_build_info()
    print_banner()
    
    if ctx.invoked_subcommand is None:
        ctx.invoke(run_model, **ctx.params)


@cli.command(name='run')
@click.option('--config', '-c', type=click.Path(exists=True),
              help='Path to the configuration file')
@click.option('--model-getter', '-g',
              type=click.Choice(['mlflow', 'local'], case_sensitive=False),
              default='mlflow',
              help='Method to obtain the model')
@click.option('--debug', '-d', is_flag=True,
              help='Enable debug mode')
@click.option('--env', '-e', type=click.Path(exists=True),
              help='Path to environment configuration file (JSON format)')
@click.option('--one-shot', '-o', is_flag=True,
              help='One shot mode - run once and exit (helpful for debugging)')
@click.option('--publish', '-p', is_flag=True,
              help='Publish data to system')
@click.option('--requirements', '-r', is_flag=True,
              help='Requirements install only - install requirements.txt from model and exit')
def run_model(config, model_getter, debug, env, one_shot, publish, requirements):
    """
    Run the model manager with the specified configuration.
    
    This is the default command when no subcommand is specified.
    
    Examples:
    
        poly-lithic run --config config.yaml
        poly-lithic run --config config.yaml --debug --publish
        poly-lithic run --config config.yaml --one-shot
    """
    try:
        logger = setup_logging(debug)
        logger.info('Model Manager CLI')
        
        if publish:
            logger.warning('Publishing data to system')
            os.environ['PUBLISH'] = 'True'
        else:
            logger.warning('Not publishing data to system. To publish, use --publish')
            os.environ['PUBLISH'] = 'False'
        
        if env:
            load_env_config(env)
        
        if not config:
            logger.info('No configuration file provided, getting config from model artifacts')
            if 'MODEL_CONFIG_FILE' not in os.environ:
                raise click.ClickException(
                    'No configuration file provided. Use --config or set MODEL_CONFIG_FILE environment variable'
                )
            config = os.environ['MODEL_CONFIG_FILE']
        else:
            logger.info(f'Configuration file provided: {config}')
        
        # Import heavy dependencies only when needed
        from poly_lithic.src.utils.builder import Builder
        
        click.echo('Building model manager...')
        builder = Builder(config)
        broker = builder.build()
        
        if requirements:
            click.echo('Requirements-only mode - exiting after installation')
            sys.exit(0)
        
        import argparse
        args = argparse.Namespace(
            config=config,
            model_getter=model_getter,
            debug=debug,
            env=env,
            one_shot=one_shot,
            publish=publish,
            requirements=requirements,
        )
        
        logger.info('Starting model manager main loop')
        asyncio.run(model_main(args, builder.config, broker))
        
    except KeyboardInterrupt:
        click.echo('\n\nInterrupted by user')
        sys.exit(0)
    except Exception as e:
        click.echo(click.style(f'\n✗ Error: {e}', fg='red'), err=True)
        if debug:
            traceback.print_exc()
        sys.exit(1)


# ============================================================================
# Plugin Commands
# ============================================================================

@cli.group()
def plugin():
    """
    Manage poly_lithic plugins.
    
    Commands for creating, listing, and managing plugins.
    """
    pass


@plugin.command()
@click.option('--name', '-n', prompt='Plugin name', 
              help='Name of the plugin package')
@click.option('--author', '-a', prompt='Author name', default='',
              help='Author name')
@click.option('--email', prompt='Author email', default='example@email.com',
              help='Author email')
@click.option('--description', '-d', prompt='Short description', default='',
              help='Plugin description')
@click.option('--output-dir', '--dir', '-o', type=click.Path(), default='.',
              help='Output directory for the plugin project (default: current directory)')
@click.option('--license', default='MIT',
              help='License type')
@click.option('--no-prompt', is_flag=True,
              help='Skip interactive prompts (use defaults or provided values)')
def init(name, author, email, description, output_dir, license, no_prompt):
    """
    Initialize a new plugin project from template.
    
    Creates a simple plugin project with examples of all plugin types.
    Comment out the types you don't need.
    
    Examples:
        poly-lithic plugin init --name my-plugin
        poly-lithic plugin init -n my-plugin --dir ./plugins
        poly-lithic plugin init --name my-plugin --no-prompt
    """
    try:
        from poly_lithic.src.utils.plugin_generator import PluginGenerator
        from pathlib import Path
        
        click.echo(click.style('\n🚀 Creating Plugin Project\n', fg='cyan', bold=True))
        
        output_path = Path(output_dir).expanduser().resolve()
        plugin_dir_name = PluginGenerator._normalize_package_name(name)
        
        if not output_path.exists():
            if no_prompt or click.confirm(f"Directory '{output_path}' doesn't exist. Create it?", default=True):
                output_path.mkdir(parents=True, exist_ok=True)
            else:
                click.echo("Aborted.")
                sys.exit(1)
        
        generator = PluginGenerator()
        project_path = generator.generate(
            name=name,
            author=author,
            email=email,
            description=description,
            output_dir=str(output_path),
            license=license,
        )
        
        click.echo(click.style(f"✓ Plugin project created: {project_path.name}", fg='green', bold=True))
        
        click.echo(click.style("\n📝 Next steps:", fg='yellow', bold=True))
        click.echo(f"  1. cd {project_path.name}")
        click.echo("  2. Edit the plugin files and comment out types you don't need")
        click.echo("  3. pip install -e .")
        click.echo("  4. Test the plugin: pl run --config test_deployment.yaml --debug --one-shot")
        click.echo("  5. Run tests: pytest")
        
        click.echo(click.style("\n💡 Tips:", fg='cyan'))
        click.echo("  • The template includes examples of all three plugin types")
        click.echo("  • Comment out types you don't need in:")
        click.echo(f"    - {plugin_dir_name}/__init__.py")
        click.echo(f"    - pyproject.toml (entry points section)")
        click.echo(f"    - test_deployment.yaml (module configurations)")
        click.echo()
        
    except FileExistsError as e:
        click.echo(click.style(f'✗ {e}', fg='red'), err=True)
        click.echo(click.style('  Tip: Choose a different name or remove the existing directory', fg='yellow'))
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f'✗ Error creating plugin: {e}', fg='red'), err=True)
        if os.environ.get('DEBUG') == 'True':
            traceback.print_exc()
        sys.exit(1)


@plugin.command()
@click.option('--type', '-t', 'plugin_type',
              type=click.Choice(['interface', 'transformer', 'model_getter', 'all'], case_sensitive=False),
              help='Filter by plugin type')
def list(plugin_type):
    """
    List all available plugins.
    
    Shows all plugins discovered via entry points in the current environment.
    
    Examples:
        poly-lithic plugin list
        poly-lithic plugin list --type interface
    """
    from poly_lithic.src.utils.plugin_registry import (
        interface_plugin_registry,
        transformer_plugin_registry,
        model_getter_plugin_registry,
    )
    
    try:
        from yaspin import yaspin
        from yaspin.spinners import Spinners
        use_spinner = True
    except ImportError:
        use_spinner = False
    
    registries = []
    if not plugin_type or plugin_type in ['interface', 'all']:
        registries.append(('Interfaces', interface_plugin_registry))
    if not plugin_type or plugin_type in ['transformer', 'all']:
        registries.append(('Transformers', transformer_plugin_registry))
    if not plugin_type or plugin_type in ['model_getter', 'all']:
        registries.append(('Model Getters', model_getter_plugin_registry))
    
    if use_spinner:
        with yaspin(Spinners.dots12, text="Discovering plugins...", color="green") as spinner:
            for name, registry in registries:
                spinner.text = f"Scanning {name.lower()}..."
                registry.discover_plugins()
            spinner.text = "Scanning complete!"
            spinner.ok("✓")
    else:
        with click.progressbar(registries, label='Scanning for plugins',
                              bar_template='%(label)s  [%(bar)s]  %(info)s',
                              show_percent=False, show_pos=True) as bar:
            for name, registry in bar:
                registry.discover_plugins()
    
    click.echo(click.style("\n📦 Available Plugins\n", fg='cyan', bold=True))
    
    for name, registry in registries:
        plugins = registry.list_plugins()
        
        if plugins:
            click.echo(click.style(f"{name}:", fg='yellow', bold=True))
            for plugin_name in sorted(plugins):
                click.echo(f"  • {plugin_name}")
            click.echo()
        else:
            click.echo(click.style(f"{name}: None found", fg='yellow'))
            click.echo()
    
    if not any(reg[1].list_plugins() for reg in registries):
        click.echo(click.style("No plugins found", fg='yellow'))


@plugin.command()
@click.argument('plugin_name')
@click.option('--type', '-t', 'plugin_type',
              type=click.Choice(['interface', 'transformer', 'model_getter'], case_sensitive=False),
              help='Plugin type (optional, will search all if not specified)')
def info(plugin_name, plugin_type):
    """
    Show detailed information about a specific plugin.
    
    Examples:
        poly-lithic plugin info my_interface
        poly-lithic plugin info my_interface --type interface
    """
    from poly_lithic.src.utils.plugin_registry import (
        interface_plugin_registry,
        transformer_plugin_registry,
        model_getter_plugin_registry,
    )
    
    registries = {}
    if not plugin_type or plugin_type == 'interface':
        registries['interface'] = interface_plugin_registry
    if not plugin_type or plugin_type == 'transformer':
        registries['transformer'] = transformer_plugin_registry
    if not plugin_type or plugin_type == 'model_getter':
        registries['model_getter'] = model_getter_plugin_registry
    
    found = False
    
    for reg_type, registry in registries.items():
        registry.discover_plugins()
        if registry.has_plugin(plugin_name):
            found = True
            plugin_class = registry.get(plugin_name)
            
            click.echo(click.style(f"\n📋 Plugin: {plugin_name}", fg='cyan', bold=True))
            click.echo(f"Type: {reg_type}")
            click.echo(f"Class: {plugin_class.__module__}.{plugin_class.__name__}")
            
            if plugin_class.__doc__:
                click.echo(f"\nDescription:")
                click.echo(f"  {plugin_class.__doc__.strip()}")
            
            methods = [m for m in dir(plugin_class) 
                      if not m.startswith('_') and callable(getattr(plugin_class, m))]
            if methods:
                click.echo(f"\nPublic Methods:")
                for method in sorted(methods):
                    click.echo(f"  • {method}()")
            
            click.echo()
    
    if not found:
        click.echo(click.style(f"✗ Plugin '{plugin_name}' not found", fg='red'), err=True)
        click.echo(click.style("\nTip: Run 'poly-lithic plugin list' to see available plugins", fg='yellow'))
        sys.exit(1)


# ============================================================================
# Utility Commands
# ============================================================================

@cli.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--env', '-e', type=click.Path(exists=True),
              help='Path to environment configuration file (JSON format)')
def validate(config_file, env):
    """
    Validate a configuration file without running the model.
    
    Examples:
        poly-lithic validate config.yaml
        poly-lithic validate config.yaml --env env.json
    """
    try:
        from poly_lithic.src.config import ConfigParser
        
        logger = make_logger(level=logging.INFO)
        
        if env:
            load_env_config(env)
        
        click.echo(f'Validating configuration file: {config_file}')
        
        config_parser = ConfigParser(config_file)
        config = config_parser.parse()
        
        click.echo(click.style('✓ Configuration is valid', fg='green', bold=True))
        
        click.echo('\nConfiguration Summary:')
        click.echo(f'  Deployment type: {config.deployment.type}')
        click.echo(f'  Deployment rate: {config.deployment.rate}')
        
        if hasattr(config, 'models'):
            click.echo(f'  Models: {len(config.models) if hasattr(config.models, "__len__") else "configured"}')
        
        if hasattr(config, 'variables'):
            click.echo(f'  Variables: {len(config.variables)}')
        
        if hasattr(config, 'transformers'):
            click.echo(f'  Transformers: {len(config.transformers) if hasattr(config.transformers, "__len__") else "configured"}')
        
        click.echo()
        
    except Exception as e:
        click.echo(click.style(f'✗ Configuration is invalid: {e}', fg='red'), err=True)
        if os.environ.get('DEBUG') == 'True':
            traceback.print_exc()
        sys.exit(1)


# ============================================================================
# Legacy Support Functions
# ============================================================================

def setup():
    """
    Legacy setup function for backward compatibility.
    
    This function is kept for existing code that imports and calls setup().
    New code should use the Click CLI directly.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Model Manager CLI')
    
    parser.add_argument('-d', '--debug', action='store_true', help='Debug mode')
    parser.add_argument('-c', '--config', help='Path to the configuration file')
    parser.add_argument('-g', '--model_getter', choices=['mlflow', 'local'], default='mlflow')
    parser.add_argument('-v', '--version', action='store_true', help='Print version and exit')
    parser.add_argument('-r', '--requirements', action='store_true')
    parser.add_argument('-e', '--env', help='Path to environment configuration file')
    parser.add_argument('-o', '--one_shot', action='store_true')
    parser.add_argument('-p', '--publish', action='store_true')
    
    args = parser.parse_args()
    
    if args.version:
        print(f'Poly-Lithic version: {__version__}')
        sys.exit(0)
    
    logger = setup_logging(args.debug)
    
    if args.publish:
        os.environ['PUBLISH'] = 'True'
    else:
        os.environ['PUBLISH'] = 'False'
    
    if args.env:
        load_env_config(args.env)
    
    if not args.config and 'MODEL_CONFIG_FILE' not in os.environ:
        raise Exception('No configuration file provided')
    
    from poly_lithic.src.utils.builder import Builder
    
    config = args.config or os.environ['MODEL_CONFIG_FILE']
    builder = Builder(config)
    broker = builder.build()
    
    return args, builder.config, broker


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    cli()
